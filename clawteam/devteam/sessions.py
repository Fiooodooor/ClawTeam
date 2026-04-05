"""Worker session tracking and live snapshot helpers."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.models import DevArtifact, DevSessionStatus, DevWorkerSession
from clawteam.spawn.registry import get_registry, is_agent_alive


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_output(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def capture_workspace_snapshot(workspace_path: str) -> dict[str, Any]:
    if not workspace_path or not Path(workspace_path).exists():
        return {}
    changed = _git_output(["status", "--short"], workspace_path)
    diff_stat = _git_output(["diff", "--stat"], workspace_path)
    last_commit = _git_output(["log", "-1", "--pretty=%h %s"], workspace_path)
    branch = _git_output(["branch", "--show-current"], workspace_path)
    files = [line.strip() for line in changed.splitlines() if line.strip()][:20]
    return {
        "branch": branch,
        "changedFiles": files,
        "diffStat": diff_stat,
        "lastCommit": last_commit,
        "clean": not files,
    }


def capture_tmux_output(tmux_target: str, *, limit_lines: int = 40) -> str:
    if not tmux_target:
        return ""
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-S", f"-{limit_lines}", "-t", tmux_target],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


class WorkerSessionStore:
    """Persists and refreshes worker session visibility for the board."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.events = DevEventStore(team_name)

    def start_session(
        self,
        *,
        agent_name: str,
        agent_id: str,
        agent_type: str,
        project_id: str,
        stage: str,
        workspace_path: str = "",
        log_path: str = "",
        details: dict[str, Any] | None = None,
    ) -> DevWorkerSession:
        snapshot = capture_workspace_snapshot(workspace_path)
        session = DevWorkerSession(
            team_name=self.team_name,
            agent_name=agent_name,
            agent_id=agent_id,
            agent_type=agent_type,
            project_id=project_id,
            stage=stage,
            status=DevSessionStatus.starting,
            workspace_path=workspace_path,
            branch=str(snapshot.get("branch", "")),
            log_path=log_path,
            details=details or {},
            snapshot=snapshot,
        )
        self.events.upsert_session(session)
        self.events.append_event(
            event_type="agent.session_started",
            actor=agent_name,
            project_id=project_id,
            session_id=session.session_id,
            occurred_at=session.started_at,
            payload=session.model_dump(mode="json"),
        )
        return session

    def update_session(self, session: DevWorkerSession) -> DevWorkerSession:
        self.events.upsert_session(session)
        return session

    def heartbeat(self, session_id: str, *, status: DevSessionStatus | None = None) -> DevWorkerSession | None:
        session = self.events.get_session(session_id)
        if session is None:
            return None
        snapshot = capture_workspace_snapshot(session.workspace_path)
        if snapshot:
            session.snapshot = snapshot
            session.branch = str(snapshot.get("branch", session.branch))
        if status is not None:
            session.status = status
        session.last_heartbeat_at = _now_iso()
        self.events.upsert_session(session)
        return session

    def complete(
        self,
        session_id: str,
        *,
        status: DevSessionStatus,
        exit_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> DevWorkerSession | None:
        session = self.events.get_session(session_id)
        if session is None:
            return None
        session.status = status
        session.exit_code = exit_code
        session.ended_at = _now_iso()
        session.last_heartbeat_at = session.ended_at
        if details:
            session.details.update(details)
        self.events.upsert_session(session)
        self.events.append_event(
            event_type="agent.session_finished",
            actor=session.agent_name,
            project_id=session.project_id,
            session_id=session.session_id,
            occurred_at=session.ended_at or session.last_heartbeat_at,
            payload={"status": session.status.value, "exitCode": exit_code, "details": details or {}},
        )
        return session

    def refresh_sessions(self) -> list[DevWorkerSession]:
        registry = get_registry(self.team_name)
        refreshed: list[DevWorkerSession] = []
        for session in self.events.list_sessions(limit=200):
            info = registry.get(session.agent_name, {})
            if info:
                session.tmux_target = str(info.get("tmux_target", ""))
            alive = is_agent_alive(self.team_name, session.agent_name)
            snapshot = capture_workspace_snapshot(session.workspace_path)
            if snapshot:
                session.snapshot = snapshot
                session.branch = str(snapshot.get("branch", session.branch))
            if alive is False and session.status in {DevSessionStatus.starting, DevSessionStatus.running, DevSessionStatus.blocked, DevSessionStatus.paused}:
                session.status = DevSessionStatus.completed if session.details.get("reported_done") else DevSessionStatus.failed
                if not session.ended_at:
                    session.ended_at = _now_iso()
            elif alive is True and session.status == DevSessionStatus.starting:
                session.status = DevSessionStatus.running
            session.last_heartbeat_at = _now_iso()
            self.events.upsert_session(session)
            refreshed.append(session)
        return refreshed

    def list_sessions(self, *, project_id: str = "") -> list[DevWorkerSession]:
        return self.events.list_sessions(project_id=project_id)

    def capture_live_log(self, session: DevWorkerSession, *, limit_lines: int = 40) -> str:
        output = capture_tmux_output(session.tmux_target, limit_lines=limit_lines)
        if output:
            return output
        if session.log_path and Path(session.log_path).exists():
            try:
                lines = Path(session.log_path).read_text(encoding="utf-8").splitlines()
                return "\n".join(lines[-limit_lines:])
            except Exception:
                return ""
        return ""

    def index_artifact(
        self,
        *,
        project_id: str,
        session_id: str,
        title: str,
        path: str,
        kind: str = "artifact",
        metadata: dict[str, Any] | None = None,
    ) -> DevArtifact:
        artifact = DevArtifact(
            team_name=self.team_name,
            project_id=project_id,
            session_id=session_id,
            title=title,
            path=path,
            kind=kind,
            metadata=metadata or {},
        )
        self.events.add_artifact(artifact)
        self.events.append_event(
            event_type="artifact.created",
            actor="runtime",
            project_id=project_id,
            session_id=session_id,
            occurred_at=artifact.created_at,
            payload=artifact.model_dump(mode="json"),
        )
        return artifact
