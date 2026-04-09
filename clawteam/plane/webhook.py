"""Webhook receiver for Plane -> ClawTeam sync and HITL triggers."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from clawteam.plane.config import PlaneConfig
from clawteam.plane.mapping import plane_group_to_clawteam_status
from clawteam.team.models import MessageType, TaskPriority, TaskStatus

log = logging.getLogger(__name__)


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _handle_work_item_event(
    payload: dict,
    config: PlaneConfig,
    team_name: str,
    state_lookup: dict[str, Any],
) -> dict[str, str]:
    from clawteam.store.file import FileTaskStore

    action = payload.get("action", "")
    data = payload.get("data", {})
    plane_id = data.get("id", "")
    name = data.get("name", "")
    state_uuid = data.get("state", "")
    priority_str = data.get("priority", "medium")

    state_obj = state_lookup.get(state_uuid)
    clawteam_status = (
        plane_group_to_clawteam_status(state_obj.group)
        if state_obj
        else TaskStatus.pending
    )

    store = FileTaskStore(team_name)

    if action == "created":
        for task in store.list_tasks():
            if task.metadata.get("plane_issue_id") == plane_id:
                return {"action": "skipped", "reason": "already exists"}

        try:
            priority = TaskPriority(priority_str)
        except ValueError:
            priority = TaskPriority.medium

        store.create(
            subject=name,
            description=data.get("description_html", ""),
            priority=priority,
            metadata={"plane_issue_id": plane_id},
        )
        return {"action": "created", "plane_id": plane_id}

    elif action == "updated":
        for task in store.list_tasks():
            if task.metadata.get("plane_issue_id") == plane_id:
                store.update(
                    task.id,
                    subject=name,
                    status=clawteam_status,
                    force=True,
                )
                if state_obj and state_obj.group == "unstarted" and "approv" in (getattr(state_obj, "name", "") or "").lower():
                    _send_approval_request(team_name, task.id, name)
                return {"action": "updated", "task_id": task.id}

        return {"action": "skipped", "reason": "no matching task"}

    return {"action": "ignored", "event_action": action}


def _handle_comment_event(
    payload: dict,
    config: PlaneConfig,
    team_name: str,
) -> dict[str, str]:
    from clawteam.store.file import FileTaskStore

    data = payload.get("data", {})
    comment_html = data.get("comment_html", "")
    issue_id = data.get("issue", "") or data.get("work_item", "")
    actor = data.get("actor_detail", {}).get("display_name", "human")

    comment_lower = comment_html.lower()
    is_approve = "approved" in comment_lower or "approve" in comment_lower or "lgtm" in comment_lower
    is_reject = "rejected" in comment_lower or "reject" in comment_lower

    if not is_approve and not is_reject:
        return {"action": "ignored", "reason": "not an approval comment"}

    store = FileTaskStore(team_name)
    for task in store.list_tasks():
        if task.metadata.get("plane_issue_id") == issue_id:
            if is_approve:
                store.update(task.id, status=TaskStatus.in_progress, force=True)
                _send_hitl_message(team_name, task, "plan_approved", actor, comment_html)
                return {"action": "approved", "task_id": task.id}
            elif is_reject:
                store.update(task.id, status=TaskStatus.blocked, force=True)
                _send_hitl_message(team_name, task, "plan_rejected", actor, comment_html)
                return {"action": "rejected", "task_id": task.id}

    return {"action": "skipped", "reason": "no matching task"}


def _send_approval_request(team_name: str, task_id: str, subject: str) -> None:
    try:
        from clawteam.team.mailbox import MailboxManager
        from clawteam.team.manager import TeamManager

        leader_inbox = TeamManager.get_leader_inbox(team_name)
        if leader_inbox:
            mailbox = MailboxManager(team_name)
            mailbox.send(
                from_agent="plane-webhook",
                to=leader_inbox,
                msg_type=MessageType.plan_approval_request,
                content=f"Task '{subject}' (id={task_id}) requires approval in Plane.",
                summary=subject,
            )
    except Exception as exc:
        log.warning("Failed to send approval request: %s", exc)


def _send_hitl_message(
    team_name: str,
    task: Any,
    msg_type_str: str,
    actor: str,
    comment: str,
) -> None:
    try:
        from clawteam.team.mailbox import MailboxManager
        from clawteam.team.manager import TeamManager

        msg_type = MessageType(msg_type_str)
        target = task.owner or TeamManager.get_leader_inbox(team_name) or ""
        if not target:
            return
        mailbox = MailboxManager(team_name)
        mailbox.send(
            from_agent="plane-webhook",
            to=target,
            msg_type=msg_type,
            content=f"{actor}: {comment}",
            summary=task.subject,
            feedback=comment,
        )
    except Exception as exc:
        log.warning("Failed to send HITL message: %s", exc)


class PlaneWebhookHandler(BaseHTTPRequestHandler):
    config: PlaneConfig
    team_name: str
    state_lookup: dict[str, Any]

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.config.webhook_secret:
            sig = self.headers.get("X-Plane-Signature", "")
            if not _verify_signature(body, sig, self.config.webhook_secret):
                self.send_error(401, "Invalid signature")
                return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        event = payload.get("event", "")
        if event == "issue":
            result = _handle_work_item_event(payload, self.config, self.team_name, self.state_lookup)
        elif event == "issue_comment":
            result = _handle_comment_event(payload, self.config, self.team_name)
        else:
            result = {"action": "ignored", "event": event}

        response = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        log.debug(format, *args)


def serve_webhook(
    config: PlaneConfig,
    team_name: str,
    state_lookup: dict[str, Any] | None = None,
    host: str = "0.0.0.0",
) -> None:
    PlaneWebhookHandler.config = config
    PlaneWebhookHandler.team_name = team_name
    PlaneWebhookHandler.state_lookup = state_lookup or {}

    server = ThreadingHTTPServer((host, config.webhook_port), PlaneWebhookHandler)
    log.info("Plane webhook receiver listening on %s:%d", host, config.webhook_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
