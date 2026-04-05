"""Lightweight HTTP server for the Web UI dashboard (stdlib only)."""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clawteam.board.collector import BoardCollector
from clawteam.devteam.control import DevTeamControlService
from clawteam.devteam.supervisor import get_company_supervisor

_STATIC_DIR = Path(__file__).parent / "static"


class BoardHandler(BaseHTTPRequestHandler):
    """HTTP handler for the board Web UI."""

    collector: BoardCollector
    default_team: str = ""
    interval: float = 2.0
    _MAX_BODY_SIZE: int = 1_000_000

    def handle(self):
        """Wrap base handle to suppress noisy connection-reset errors.

        Browsers frequently reset connections (page reload, tab close,
        SSE reconnect) and the default socketserver prints a full
        traceback for each one.
        """
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            self._serve_static("index.html", "text/html")
        elif path == "/favicon.ico":
            # Return empty 204 to suppress browser 404 noise
            self.send_response(204)
            self.end_headers()
        elif path == "/api/overview":
            self._serve_json(self.collector.collect_overview())
        elif path.startswith("/api/team/"):
            team_name = path[len("/api/team/"):].strip("/")
            if not team_name:
                self.send_error(400, "Team name required")
                return
            self._serve_team(team_name)
        elif path.startswith("/api/company/") and path.endswith("/status"):
            team_name = path[len("/api/company/"): -len("/status")].strip("/")
            if not team_name:
                self.send_error(400, "Team name required")
                return
            self._serve_company_status(team_name)
        elif path.startswith("/api/events/"):
            team_name = path[len("/api/events/"):].strip("/")
            if not team_name:
                self.send_error(400, "Team name required")
                return
            self._serve_sse(team_name)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/company/"):
            self._handle_company_post(path)
            return
        if path.startswith("/api/devteam/"):
            self._handle_devteam_post(path)
            return
        if path.startswith("/api/github/"):
            self._handle_github_post(path)
            return
        self.send_error(404)

    def _serve_static(self, filename: str, content_type: str):
        filepath = _STATIC_DIR / filename
        if not filepath.exists():
            self.send_error(404, f"Static file not found: {filename}")
            return
        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        accept_encoding = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_encoding:
            body = gzip.compress(body)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")

        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_error_json(self, status_code: int, message: str) -> None:
        """Send a JSON error response with the given status code and message."""
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if length > self._MAX_BODY_SIZE:
            body = json.dumps({"error": "Request body too large"}).encode("utf-8")
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _serve_team(self, team_name: str):
        try:
            data = self.collector.collect_team(team_name)
            self._serve_json(data)
        except ValueError as e:
            self._serve_error_json(404, str(e))

    def _serve_company_status(self, team_name: str):
        try:
            data = self.collector.collect_team(team_name)
            devteam = data.get("devteam") or {}
            self._serve_json({"team": team_name, "company": devteam.get("company") or {}})
        except ValueError as e:
            self._serve_error_json(404, str(e))

    def _serve_sse(self, team_name: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        last_hash = ""
        try:
            while True:
                try:
                    data = self.collector.collect_team(team_name)
                except ValueError as e:
                    data = {"error": str(e)}
                payload = json.dumps(data, ensure_ascii=False)
                current_hash = hashlib.md5(payload.encode()).hexdigest()

                if current_hash != last_hash:
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_hash = current_hash
                else:
                    # Send heartbeat to keep connection alive
                    self.wfile.write(": heartbeat\n\n".encode("utf-8"))
                    self.wfile.flush()

                time.sleep(self.interval)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _handle_devteam_post(self, path: str):
        prefix = "/api/devteam/"
        tail = path[len(prefix):].strip("/")
        parts = tail.split("/")
        if len(parts) < 2:
            self.send_error(400, "Devteam route requires team and action")
            return
        team_name = parts[0]
        payload = self._read_json_body()
        service = DevTeamControlService(team_name)

        try:
            if len(parts) == 2 and parts[1] == "request":
                result = service.submit_request(
                    title=str(payload.get("title") or "").strip() or "New request",
                    description=str(payload.get("description") or "").strip(),
                    project_type=str(payload.get("projectType") or "feature"),
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "pause":
                result = service.pause_project(
                    project_id=parts[2],
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "resume":
                result = service.resume_project(
                    project_id=parts[2],
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "approve":
                result = service.approve_stage(
                    project_id=parts[2],
                    approved_by=str(payload.get("approvedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "reroute":
                result = service.reroute_project(
                    project_id=parts[2],
                    stage=str(payload.get("stage") or "plan"),
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "reassign":
                result = service.reassign_project(
                    project_id=parts[2],
                    owner=str(payload.get("owner") or "chief-of-staff"),
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "project": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "inject":
                result = service.inject_instruction(
                    project_id=parts[2],
                    instruction=str(payload.get("instruction") or "").strip(),
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "activity": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "delete":
                result = service.delete_project(
                    project_id=parts[2],
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, **result})
                return
            if len(parts) == 2 and parts[1] == "jobs":
                channels = payload.get("channels") or ["dev-ops"]
                if isinstance(channels, str):
                    channels = [item.strip() for item in channels.split(",") if item.strip()]
                result = service.add_job(
                    title=str(payload.get("title") or "").strip() or "Recurring job",
                    cadence=str(payload.get("cadence") or "").strip(),
                    owner=str(payload.get("owner") or "chief-of-staff").strip(),
                    instruction=str(payload.get("instruction") or "").strip(),
                    channels=channels,
                    created_by=str(payload.get("createdBy") or "CEO"),
                )
                self._serve_json({"ok": True, "job": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "jobs" and parts[3] == "run":
                result = service.run_job_now(
                    job_key=parts[2],
                    requested_by=str(payload.get("requestedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "job": result.model_dump(mode="json")})
                return
            if len(parts) == 2 and parts[1] == "activities":
                participants = payload.get("participants") or []
                if isinstance(participants, str):
                    participants = [item.strip() for item in participants.split(",") if item.strip()]
                result = service.add_note(
                    title=str(payload.get("title") or "").strip() or "Meeting note",
                    body=str(payload.get("body") or "").strip(),
                    author=str(payload.get("author") or "CEO"),
                    project_id=str(payload.get("projectId") or "").strip(),
                    participants=participants,
                    kind=str(payload.get("kind") or "note"),
                )
                self._serve_json({"ok": True, "activity": result.model_dump(mode="json")})
                return
            if len(parts) == 3 and parts[1] == "invoke":
                agent_type = parts[2]
                result = service.invoke_specialist(
                    agent_type=agent_type,
                    task=str(payload.get("task") or "").strip(),
                    project_id=str(payload.get("projectId") or "").strip(),
                )
                self._serve_json({"ok": True, "specialist": result})
                return
            if len(parts) == 2 and parts[1] == "meetings":
                participants = payload.get("participants") or []
                if isinstance(participants, str):
                    participants = [item.strip() for item in participants.split(",") if item.strip()]
                result = service.start_meeting(
                    title=str(payload.get("title") or "Decision meeting"),
                    agenda=str(payload.get("agenda") or "").strip(),
                    participants=participants or ["chief-of-staff", "cto", "lead-engineer"],
                    project_id=str(payload.get("projectId") or "").strip(),
                    created_by=str(payload.get("createdBy") or "CEO"),
                )
                self._serve_json({"ok": True, "meeting": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "meetings" and parts[3] == "messages":
                result = service.post_meeting_message(
                    meeting_id=parts[2],
                    body=str(payload.get("body") or "").strip(),
                    author=str(payload.get("author") or "CEO"),
                )
                self._serve_json({"ok": True, "message": result.model_dump(mode="json")})
                return
            if len(parts) == 4 and parts[1] == "meetings" and parts[3] == "end":
                result = service.conclude_meeting(
                    meeting_id=parts[2],
                    concluded_by=str(payload.get("concludedBy") or "CEO"),
                )
                self._serve_json({"ok": True, "meeting": result.model_dump(mode="json")})
                return
            self.send_error(404)
        except FileNotFoundError as exc:
            self._serve_error_json(404, str(exc))

    def _handle_company_post(self, path: str):
        prefix = "/api/company/"
        tail = path[len(prefix):].strip("/")
        parts = tail.split("/")
        if len(parts) < 2:
            self.send_error(400, "Company route requires team and action")
            return
        try:
            team_name = parts[0]
            action = parts[1]
            supervisor = get_company_supervisor(team_name)

            if action == "start":
                self._serve_json({"ok": True, "company": supervisor.start().model_dump(mode="json")})
                return
            if action == "stop":
                self._serve_json({"ok": True, "company": supervisor.stop().model_dump(mode="json")})
                return
            if action == "restart":
                self._serve_json({"ok": True, "company": supervisor.restart().model_dump(mode="json")})
                return
            self.send_error(404)
        except Exception as exc:
            self._serve_error_json(400, str(exc))

    def _handle_github_post(self, path: str):
        """Handle GitHub-related API requests."""
        prefix = "/api/github/"
        tail = path[len(prefix):].strip("/")
        parts = tail.split("/")
        payload = self._read_json_body()

        try:
            from clawteam.devteam.github import (
                get_pr,
                get_pr_diff,
                get_pr_files,
                list_prs,
                list_runs,
                get_failed_run_logs,
                fetch_pr_context_for_project,
                is_gh_available,
                gh_auth_user,
            )

            if not is_gh_available():
                self._serve_json({"ok": False, "error": "GitHub CLI not available or not authenticated"})
                return

            # POST /api/github/status
            if len(parts) == 1 and parts[0] == "status":
                self._serve_json({
                    "ok": True,
                    "available": True,
                    "user": gh_auth_user(),
                })
                return

            # POST /api/github/pr — fetch PR details
            if len(parts) == 1 and parts[0] == "pr":
                repo = str(payload.get("repo", "")).strip()
                pr_number = int(payload.get("number", 0))
                if not repo or not pr_number:
                    self._serve_json({"ok": False, "error": "repo and number required"})
                    return
                ctx = fetch_pr_context_for_project(repo, pr_number, include_diff=True)
                self._serve_json({"ok": True, **ctx})
                return

            # POST /api/github/prs — list PRs
            if len(parts) == 1 and parts[0] == "prs":
                repo = str(payload.get("repo", "")).strip()
                state = str(payload.get("state", "open"))
                if not repo:
                    self._serve_json({"ok": False, "error": "repo required"})
                    return
                prs = list_prs(repo, state=state, limit=int(payload.get("limit", 10)))
                self._serve_json({"ok": True, "prs": prs})
                return

            # POST /api/github/actions — list Actions runs
            if len(parts) == 1 and parts[0] == "actions":
                repo = str(payload.get("repo", "")).strip()
                branch = str(payload.get("branch", ""))
                if not repo:
                    self._serve_json({"ok": False, "error": "repo required"})
                    return
                runs = list_runs(repo, branch=branch, limit=int(payload.get("limit", 10)))
                self._serve_json({
                    "ok": True,
                    "runs": [
                        {
                            "id": r.id, "name": r.name, "status": r.status,
                            "conclusion": r.conclusion, "branch": r.head_branch,
                            "event": r.event, "url": r.url,
                            "createdAt": r.created_at,
                        }
                        for r in runs
                    ],
                })
                return

            # POST /api/github/run-logs — get failed run logs
            if len(parts) == 1 and parts[0] == "run-logs":
                repo = str(payload.get("repo", "")).strip()
                run_id = int(payload.get("runId", 0))
                if not repo or not run_id:
                    self._serve_json({"ok": False, "error": "repo and runId required"})
                    return
                logs = get_failed_run_logs(repo, run_id)
                self._serve_json({"ok": True, "logs": logs})
                return

            self.send_error(404)
        except Exception as exc:
            self._serve_error_json(500, str(exc))

    def log_message(self, format, *args):
        # Suppress default stderr logging for SSE connections
        first = str(args[0]) if args else ""
        if "/api/events/" not in first:
            super().log_message(format, *args)


def serve(
    host: str = "127.0.0.1",
    port: int = 8080,
    default_team: str = "",
    interval: float = 2.0,
):
    """Start the Web UI server."""
    collector = BoardCollector()
    BoardHandler.collector = collector
    BoardHandler.default_team = default_team
    BoardHandler.interval = interval

    server = ThreadingHTTPServer((host, port), BoardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
