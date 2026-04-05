"""Always-on Slack runtime for the investment operating system."""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import suppress
from datetime import datetime
from typing import Any

import fcntl
from zoneinfo import ZoneInfo

from clawteam.investment.bootstrap import (
    investment_dir,
    load_runtime_blueprint,
    load_runtime_state,
    save_runtime_state,
)
from clawteam.investment.autonomy import AutonomousConversationEngine
from clawteam.investment.cases import CaseManager, InvestmentCase
from clawteam.investment.scheduler import DueSchedule, SchedulerStore
from clawteam.investment.slack import SlackSocketModeEventSource, SlackWebClient
from clawteam.team.mailbox import MailboxManager
from clawteam.team.tasks import TaskStore


class InvestmentRuntimeError(RuntimeError):
    """Raised when the always-on runtime cannot proceed."""


class InvestmentOperatingRuntime:
    """Coordinates startup, scheduling, Slack routing, and case persistence."""

    def __init__(
        self,
        team_name: str,
        slack_client: SlackWebClient | None = None,
        event_source=None,
        mailbox: MailboxManager | None = None,
        task_store: TaskStore | None = None,
        case_manager: CaseManager | None = None,
        scheduler: SchedulerStore | None = None,
        sleep_fn=time.sleep,
        now_fn=None,
        workspace_dir: str | None = None,
    ):
        self.team_name = team_name
        self.runtime = load_runtime_blueprint(team_name)
        self.state = load_runtime_state(team_name)
        self.workspace_dir = (
            workspace_dir or os.environ.get("CLAWTEAM_WORKSPACE_DIR", "") or os.getcwd()
        )
        self.slack = slack_client or SlackWebClient()
        self.event_source = event_source or SlackSocketModeEventSource(web_client=self.slack)
        self.mailbox = mailbox or MailboxManager(team_name)
        self.task_store = task_store or TaskStore(team_name)
        self.case_manager = case_manager or CaseManager(team_name, workspace_dir=self.workspace_dir)
        self.scheduler = scheduler or SchedulerStore(team_name)
        self.sleep_fn = sleep_fn
        self.now_fn = now_fn or self._build_now_fn()
        self.autonomy = AutonomousConversationEngine(
            self.runtime.blueprint.personas,
            now_fn=self.now_fn,
        )
        self.channel_cache: dict[str, dict[str, Any]] = {}
        self._started = False
        self._runtime_lock = None
        self.log_path = investment_dir(team_name) / "runtime.log"
        self.logger = self._build_logger()

    def startup(self) -> dict[str, Any]:
        self.logger.info("startup begin")
        self._acquire_runtime_lock()
        self._ensure_channels()
        self._refresh_cases_for_startup()
        bound_cases = self._ensure_case_threads()
        self.state = load_runtime_state(self.team_name)
        self.state.mode = "company_open"
        self._touch_heartbeat()
        self._run_startup_protocols()
        self._advance_case_conversations(bound_cases, trigger="startup")
        self.state = load_runtime_state(self.team_name)
        self.state.mode = "company_open"
        self._touch_heartbeat()
        self._started = True
        save_runtime_state(self.state)
        result = {
            "team": self.team_name,
            "channels": sorted(self.channel_cache),
            "bound_cases": [case.case_id for case in bound_cases],
            "mode": self.state.mode,
        }
        self.logger.info(
            "startup complete mode=%s channels=%s bound_cases=%s",
            result["mode"],
            len(result["channels"]),
            ",".join(result["bound_cases"]) or "none",
        )
        return result

    def run_once(self) -> dict[str, Any]:
        if not self._started:
            startup = self.startup()
        else:
            startup = {"team": self.team_name, "mode": self.state.mode}
        due_protocols = self._safe_run_due_schedules()
        events = self.event_source.read_events(limit=25, timeout_seconds=0.1)
        handled_events = 0
        for event in events:
            envelope_id = str(event.pop("__socket_envelope_id", ""))
            try:
                handled_events += 1
                self.handle_slack_event(event)
                if envelope_id and hasattr(self.event_source, "ack"):
                    self.event_source.ack(envelope_id)
            except Exception as exc:
                self._record_runtime_error(exc)
        self._advance_case_conversations(self.case_manager.list_cases(), trigger="loop")
        self._safe_run_always_on_once()
        save_runtime_state(self.state)
        result = {
            "startup": startup,
            "due_protocols": due_protocols,
            "handled_events": handled_events,
            "mode": self.state.mode,
        }
        self.logger.info(
            "loop tick mode=%s due_protocols=%s handled_events=%s",
            result["mode"],
            ",".join(result["due_protocols"]) or "none",
            result["handled_events"],
        )
        return result

    def run_forever(
        self, poll_interval_seconds: float = 5.0, max_iterations: int | None = None
    ) -> None:
        iteration = 0
        if not self._started:
            self.startup()
        self.logger.info(
            "run_forever start poll_interval=%s max_iterations=%s log=%s",
            poll_interval_seconds,
            max_iterations or "infinite",
            self.log_path,
        )
        while max_iterations is None or iteration < max_iterations:
            try:
                self.run_once()
            except Exception as exc:
                self._record_runtime_error(exc)
            iteration += 1
            self.sleep_fn(poll_interval_seconds)

    def handle_slack_event(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("event_id") or event.get("client_msg_id") or event.get("ts") or "")
        if event_id and self._has_seen_event(event_id):
            return
        event_type = str(event.get("type") or "")
        if event_type in {"message", "app_mention"}:
            self._handle_message_event(event, event_id=event_id)
            self.state = load_runtime_state(self.team_name)
        if event_id:
            self._mark_event_receipt_complete(event_id)
            self._remember_event(event_id)

    def _ensure_channels(self) -> None:
        for channel in self.runtime.blueprint.channels:
            self.channel_cache[channel.name] = self._ensure_channel_binding(
                channel.name,
                private=channel.private,
            )

    def _ensure_case_threads(self) -> list[InvestmentCase]:
        bound_cases: list[InvestmentCase] = []
        for case in self.case_manager.list_cases():
            if case.status != "open":
                continue
            binding = self.case_manager.ensure_case_thread(
                case.case_id,
                self.slack,
                channel_name=self.case_manager.resolve_channel_name(case),
                private=self._channel_private(case),
                channel_info=self.channel_cache.get(self.case_manager.resolve_channel_name(case)),
            )
            bound_cases.append(binding.case)
        return bound_cases

    def _run_startup_protocols(self) -> None:
        fired_company_open = False
        for due_schedule in self.scheduler.due_schedules(
            self.runtime.blueprint.schedules, self.now_fn()
        ):
            if due_schedule.key != "company_open":
                continue
            self.dispatch_protocol(
                "company_open",
                reason="startup",
                receipt_key=f"company_open:{due_schedule.slot_key}",
            )
            self.scheduler.mark_run(due_schedule)
            fired_company_open = True
            break
        ops_channel = self._channel_id("lbox-ops")
        self.slack.post_message(
            ops_channel,
            f"Investment runtime for `{self.team_name}` is online. Mode: {self.state.mode}.",
            metadata={
                "event_type": "clawteam_case_updated",
                "event_payload": {"team": self.team_name, "kind": "runtime_online"},
            },
        )
        if not fired_company_open:
            self._post_warm_start_summary()

    def _run_due_schedules(self) -> list[str]:
        due = self.scheduler.due_schedules(self.runtime.blueprint.schedules, self.now_fn())
        ran: list[str] = []
        for due_schedule in due:
            self.dispatch_protocol(
                due_schedule.key,
                reason="schedule",
                receipt_key=f"{due_schedule.key}:{due_schedule.slot_key}",
            )
            self.scheduler.mark_run(due_schedule)
            ran.append(due_schedule.key)
        return ran

    def _safe_run_due_schedules(self) -> list[str]:
        try:
            return self._run_due_schedules()
        except Exception as exc:
            self._record_runtime_error(exc)
            return []

    def _run_always_on_once(self) -> None:
        self._touch_heartbeat()
        self.task_store.release_stale_locks()
        protocol = self.runtime.blueprint.protocols.get("always_on")
        if protocol is None:
            return
        cadence = DueSchedule(
            key="always_on",
            slot_key=f"always-on:{int(self.now_fn().timestamp() // 300)}",
            schedule=self.runtime.blueprint.schedules[0]
            if self.runtime.blueprint.schedules
            else self._synthetic_schedule(),
        )
        state = self.scheduler.load()
        if state.get(cadence.key) == cadence.slot_key:
            return
        self.dispatch_protocol(
            "always_on",
            reason="loop",
            receipt_key=f"always_on:{cadence.slot_key}",
        )
        self.scheduler.mark_run(cadence)

    def _safe_run_always_on_once(self) -> None:
        try:
            self._run_always_on_once()
        except Exception as exc:
            self._record_runtime_error(exc)

    def dispatch_protocol(self, protocol_key: str, reason: str, receipt_key: str = "") -> None:
        protocol = self.runtime.blueprint.protocols.get(protocol_key)
        if protocol is None:
            return
        self.logger.info("dispatch protocol=%s reason=%s", protocol_key, reason)
        lines = [
            f"*{protocol.title}*",
            f"Owner: {protocol.owner}",
            f"When: {protocol.when}",
            f"Reason: {reason}",
            "Steps:",
        ]
        lines.extend(f"{idx}. {step}" for idx, step in enumerate(protocol.steps, start=1))
        text = "\n".join(lines)
        channels = protocol.channels or ["lbox-ops"]
        receipt = self._protocol_receipt(receipt_key)
        for channel_name in channels:
            posted_channels = set(receipt.get("posted_channels", []))
            if channel_name in posted_channels:
                continue
            self.slack.post_message(
                self._channel_id(channel_name),
                text,
                metadata={
                    "event_type": "clawteam_case_updated",
                    "event_payload": {
                        "team": self.team_name,
                        "protocol": protocol_key,
                        "reason": reason,
                    },
                },
            )
            if receipt_key:
                posted_channels.add(channel_name)
                self._update_protocol_receipt(
                    receipt_key,
                    protocol_key=protocol_key,
                    posted_channels=sorted(posted_channels),
                )
                receipt = self._protocol_receipt(receipt_key)
        request_id = f"protocol-{receipt_key}" if receipt_key else None
        if not receipt.get("mailbox_sent") and not self._mailbox_event_exists(request_id):
            self.mailbox.send(
                from_agent="investment-runtime",
                to=protocol.owner,
                content=f"Protocol '{protocol_key}' fired ({reason}). Review the Slack updates and triage follow-ups.",
                request_id=request_id,
            )
            if receipt_key:
                self._update_protocol_receipt(
                    receipt_key,
                    protocol_key=protocol_key,
                    mailbox_sent=True,
                )
        self.state.last_protocol_runs[protocol_key] = self.now_fn().isoformat()
        if receipt_key:
            self._update_protocol_receipt(receipt_key, protocol_key=protocol_key, completed=True)

    def _handle_message_event(self, event: dict[str, Any], event_id: str = "") -> None:
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return
        channel_id = str(event.get("channel") or "")
        if not channel_id:
            return
        thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
        text = str(event.get("text") or "").strip()
        if not text:
            return
        receipt = self._event_receipt(event_id)
        case = self.case_manager.find_case_by_thread(channel_id, thread_ts)
        if case is None:
            case = self._open_case_from_event(event, channel_id, thread_ts, text)
        else:
            self.case_manager.update_case_activity(
                case, message_ts=str(event.get("ts") or thread_ts)
            )
        if event_id:
            self._update_event_receipt(event_id, case_id=case.case_id)
        if not receipt.get("task_created") and not self._task_exists_for_event(event_id):
            self.task_store.create(
                subject=f"[{case.case_id}] Slack follow-up",
                description=text,
                owner="research-pm",
                metadata={
                    "case_id": case.case_id,
                    "channel": channel_id,
                    "thread_ts": thread_ts,
                    "event_id": event_id,
                },
            )
            if event_id:
                self._update_event_receipt(event_id, task_created=True)
        request_id = f"slack-{event_id}" if event_id else None
        if not receipt.get("mailbox_sent") and not self._mailbox_event_exists(request_id):
            self.mailbox.send(
                from_agent="slack-bridge",
                to="research-pm",
                content=f"Case {case.case_id}: {text}",
                request_id=request_id,
            )
            if event_id:
                self._update_event_receipt(event_id, mailbox_sent=True)
        if not receipt.get("reaction_added"):
            self.slack.add_reaction(channel_id, str(event.get("ts") or thread_ts), "eyes")
            if event_id:
                self._update_event_receipt(event_id, reaction_added=True)
        self.autonomy.note_human_message(case, text, str(event.get("ts") or thread_ts))
        self.case_manager.save_case(case)
        self._advance_case_conversations([case], trigger="human_message")

    def _open_case_from_event(
        self,
        event: dict[str, Any],
        channel_id: str,
        thread_ts: str,
        text: str,
    ) -> InvestmentCase:
        channel_name = self._channel_name_for_id(channel_id)
        case_type = self._default_case_type(channel_name)
        client_id = ""
        if channel_name.startswith("lbox-vip-") and channel_name.endswith("-ops"):
            client_id = channel_name.removeprefix("lbox-vip-").removesuffix("-ops")
        elif channel_name.startswith("lbox-portfolio-"):
            client_id = channel_name.removeprefix("lbox-portfolio-")
        title = self._title_from_event(text, case_type)
        case = self.case_manager.open_intake_case(
            title=title,
            case_type=case_type,
            assigned_agents=self._assigned_agents_for_channel(channel_name),
            source_channel=channel_name,
            source_thread_ts=thread_ts,
            client_id=client_id,
            metadata={"channel_name": channel_name},
        )
        bound_case = self.case_manager.bind_existing_thread(
            case.case_id,
            channel_id=channel_id,
            channel_name=channel_name,
            thread_ts=thread_ts,
            last_message_ts=str(event.get("ts") or thread_ts),
        )
        self.slack.post_message(
            channel_id,
            f"Registered new case `{bound_case.case_id}` for Research PM triage.",
            thread_ts=thread_ts,
            metadata={
                "event_type": "clawteam_case_updated",
                "event_payload": {"team": self.team_name, "case_id": bound_case.case_id},
            },
        )
        return bound_case

    def _channel_id(self, channel_name: str) -> str:
        info = self.channel_cache.get(channel_name)
        if info is None:
            spec = next(
                (item for item in self.runtime.blueprint.channels if item.name == channel_name),
                None,
            )
            info = self._ensure_channel_binding(channel_name, private=bool(spec and spec.private))
            self.channel_cache[channel_name] = info
        channel_id = str(info.get("id", ""))
        if not channel_id:
            raise InvestmentRuntimeError(f"Slack channel '{channel_name}' does not have an id")
        return channel_id

    def _channel_private(self, case: InvestmentCase) -> bool:
        channel_name = self.case_manager.resolve_channel_name(case)
        spec = next(
            (item for item in self.runtime.blueprint.channels if item.name == channel_name),
            None,
        )
        return bool(spec and spec.private)

    def _channel_name_for_id(self, channel_id: str) -> str:
        for name, channel in self.channel_cache.items():
            if str(channel.get("id", "")) == channel_id:
                return name
        for channel in self.runtime.blueprint.channels:
            info = self._ensure_channel_binding(channel.name, private=channel.private)
            self.channel_cache[channel.name] = info
            if str(info.get("id", "")) == channel_id:
                return channel.name
        return "lbox-intake"

    def _ensure_channel_binding(self, channel_name: str, private: bool) -> dict[str, Any]:
        try:
            info = self.slack.ensure_channel(channel_name, private=private)
        except Exception as exc:
            if not (private and self._is_hidden_private_channel_error(exc)):
                raise
            info = self._load_known_private_channel(channel_name)
            if info is None:
                self.logger.warning(
                    "skipping private channel '%s' — not visible to bot and no cached id",
                    channel_name,
                )
                return {"id": "", "name": channel_name, "is_private": True, "skipped": True}
        self._remember_channel_binding(channel_name, info)
        return info

    def _is_hidden_private_channel_error(self, exc: Exception) -> bool:
        return "already exists but is not visible to the bot" in str(exc)

    def _load_known_private_channel(self, channel_name: str) -> dict[str, Any] | None:
        self.state = load_runtime_state(self.team_name)
        known_channels = dict(self.state.metadata.get("known_channels", {}))
        channel_id = str(known_channels.get(channel_name, ""))
        if not channel_id:
            return None
        return {"id": channel_id, "name": channel_name, "is_private": True}

    def _remember_channel_binding(self, channel_name: str, info: dict[str, Any]) -> None:
        channel_id = str(info.get("id", ""))
        if not channel_id:
            return
        self.state = load_runtime_state(self.team_name)
        known_channels = dict(self.state.metadata.get("known_channels", {}))
        if known_channels.get(channel_name) == channel_id:
            return
        known_channels[channel_name] = channel_id
        self.state.metadata["known_channels"] = known_channels
        save_runtime_state(self.state)

    def _default_case_type(self, channel_name: str) -> str:
        spec = next(
            (item for item in self.runtime.blueprint.channels if item.name == channel_name),
            None,
        )
        if spec and spec.default_thread_case_type:
            return spec.default_thread_case_type
        return "intake"

    def _assigned_agents_for_channel(self, channel_name: str) -> list[str]:
        spec = next(
            (item for item in self.runtime.blueprint.channels if item.name == channel_name),
            None,
        )
        return list(spec.subscribers) if spec else ["research-pm"]

    def _title_from_event(self, text: str, case_type: str) -> str:
        title = text.replace("<@", "").replace(">", "").strip()
        if len(title) > 60:
            title = f"{title[:57].rstrip()}..."
        return title or f"{case_type.title()} intake"

    def _touch_heartbeat(self) -> None:
        self.state.last_heartbeat_at = self.now_fn().isoformat()

    def _refresh_cases_for_startup(self) -> None:
        for case in self.case_manager.list_cases():
            if case.status != "open":
                continue
            refreshed = self.autonomy.refresh_case_for_session(case)
            self.case_manager.save_case(refreshed)

    def _post_warm_start_summary(self) -> None:
        open_cases = [case for case in self.case_manager.list_cases() if case.status == "open"]
        lines = [
            "*Warm Start*",
            f"Mode: {self.state.mode}",
            f"Open cases: {len(open_cases)}",
        ]
        for case in open_cases[:5]:
            channel_name = self.case_manager.resolve_channel_name(case)
            lines.append(f"- `{case.case_id}` in #{channel_name}: {case.title}")
        self.slack.post_message(
            self._channel_id("lbox-ops"),
            "\n".join(lines),
            metadata={
                "event_type": "clawteam_case_updated",
                "event_payload": {"team": self.team_name, "kind": "warm_start"},
            },
        )

    def _advance_case_conversations(
        self,
        cases: list[InvestmentCase],
        trigger: str,
    ) -> None:
        for case in cases:
            if case.status != "open" or not case.thread:
                continue
            latest_case = self.case_manager.get_case(case.case_id) or case
            channel_name = self.case_manager.resolve_channel_name(latest_case)
            intents = self.autonomy.plan_turns(
                latest_case, channel_name=channel_name, trigger=trigger
            )
            if not intents:
                continue
            self.logger.info(
                "autonomy trigger=%s case=%s speakers=%s",
                trigger,
                latest_case.case_id,
                ",".join(intent.agent for intent in intents),
            )
            for intent in intents:
                persona = self.autonomy.registry.get(intent.agent)
                if persona is None or latest_case.thread is None:
                    continue
                response = self.slack.post_message(
                    latest_case.thread.channel,
                    intent.text,
                    thread_ts=latest_case.thread.thread_ts,
                    username=persona.display_name,
                    icon_emoji=persona.icon_emoji,
                    metadata={
                        "event_type": "clawteam_case_updated",
                        "event_payload": {
                            "team": self.team_name,
                            "case_id": latest_case.case_id,
                            "speaker": intent.agent,
                            "action": intent.action,
                        },
                    },
                )
                latest_case = self.autonomy.record_turn(
                    latest_case,
                    intent,
                    message_ts=str(response.get("ts", latest_case.thread.thread_ts)),
                )
                self.case_manager.save_case(latest_case)

    def _synthetic_schedule(self):
        from clawteam.investment.models import ScheduleSpec

        return ScheduleSpec(
            key="always_on",
            cadence="every 5m",
            owner="research-pm",
            description="Always-on runtime loop",
            channels=["lbox-ops"],
        )

    def _has_seen_event(self, event_id: str) -> bool:
        receipt = self._event_receipt(event_id)
        if receipt.get("completed"):
            return True
        seen = list(self.state.metadata.get("recent_event_ids", []))
        return event_id in seen

    def _remember_event(self, event_id: str) -> None:
        self.state = load_runtime_state(self.team_name)
        seen = list(self.state.metadata.get("recent_event_ids", []))
        seen.append(event_id)
        self.state.metadata["recent_event_ids"] = seen[-200:]

    def _event_receipt(self, event_id: str) -> dict[str, Any]:
        if not event_id:
            return {}
        self.state = load_runtime_state(self.team_name)
        receipts = self.state.metadata.setdefault("event_receipts", {})
        return dict(receipts.get(event_id, {}))

    def _update_event_receipt(self, event_id: str, **updates: Any) -> None:
        if not event_id:
            return
        self.state = load_runtime_state(self.team_name)
        receipts = dict(self.state.metadata.get("event_receipts", {}))
        receipt = dict(receipts.get(event_id, {}))
        receipt.update(updates)
        receipts[event_id] = receipt
        while len(receipts) > 200:
            receipts.pop(next(iter(receipts)), None)
        self.state.metadata["event_receipts"] = receipts
        save_runtime_state(self.state)

    def _mark_event_receipt_complete(self, event_id: str) -> None:
        self._update_event_receipt(event_id, completed=True)

    def _protocol_receipt(self, receipt_key: str) -> dict[str, Any]:
        if not receipt_key:
            return {}
        self.state = load_runtime_state(self.team_name)
        receipts = self.state.metadata.setdefault("protocol_receipts", {})
        return dict(receipts.get(receipt_key, {}))

    def _update_protocol_receipt(self, receipt_key: str, **updates: Any) -> None:
        if not receipt_key:
            return
        self.state = load_runtime_state(self.team_name)
        receipts = dict(self.state.metadata.get("protocol_receipts", {}))
        receipt = dict(receipts.get(receipt_key, {}))
        receipt.update(updates)
        receipts[receipt_key] = receipt
        while len(receipts) > 200:
            receipts.pop(next(iter(receipts)), None)
        self.state.metadata["protocol_receipts"] = receipts
        save_runtime_state(self.state)

    def _task_exists_for_event(self, event_id: str) -> bool:
        if not event_id:
            return False
        return any(
            task.metadata.get("event_id") == event_id for task in self.task_store.list_tasks()
        )

    def _mailbox_event_exists(self, request_id: str | None) -> bool:
        if not request_id:
            return False
        return any(
            message.request_id == request_id for message in self.mailbox.get_event_log(limit=200)
        )

    def _record_runtime_error(self, exc: Exception) -> None:
        self.logger.error("runtime error: %s", exc)
        self.state = load_runtime_state(self.team_name)
        errors = list(self.state.metadata.get("runtime_errors", []))
        errors.append({"at": self.now_fn().isoformat(), "error": str(exc)})
        self.state.metadata["runtime_errors"] = errors[-50:]
        save_runtime_state(self.state)

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"clawteam.investment.runtime.{self.team_name}")
        if logger.handlers:
            return logger
        logger.setLevel(logging.INFO)
        logger.propagate = False
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)
        return logger

    def _build_now_fn(self):
        tz_name = os.environ.get("CLAWTEAM_RUNTIME_TZ", "").strip()
        try:
            timezone = ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo
        except Exception as exc:
            raise InvestmentRuntimeError(
                f"Invalid CLAWTEAM_RUNTIME_TZ '{tz_name}'. Use an IANA timezone like 'America/New_York'."
            ) from exc
        return lambda: datetime.now(timezone)

    def _acquire_runtime_lock(self) -> None:
        if self._runtime_lock is not None:
            return
        lock_path = investment_dir(self.team_name) / ".runtime.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise InvestmentRuntimeError(
                f"Investment runtime for team '{self.team_name}' is already running"
            ) from exc
        self._runtime_lock = lock_file

    def close(self) -> None:
        if hasattr(self.event_source, "close"):
            with suppress(Exception):
                self.event_source.close()
        if self._runtime_lock is None:
            return
        try:
            fcntl.flock(self._runtime_lock.fileno(), fcntl.LOCK_UN)
        finally:
            self._runtime_lock.close()
            self._runtime_lock = None
