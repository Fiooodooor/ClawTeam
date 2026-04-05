"""SQLite-backed event journal and read/write stores for the devteam control plane."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from clawteam.devteam.bootstrap import devteam_dir
from clawteam.devteam.models import (
    DevCommand,
    DevCommandStatus,
    DevCompanyState,
    DevMeeting,
    DevMeetingMessage,
    DevWorkerSession,
    DevArtifact,
)


def _json_dump(value: Any) -> str:
    if value is None:
        value = {}
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class DevEventStore:
    """Persistent SQLite store for company state, events, commands, sessions, meetings, and artifacts."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.path = devteam_dir(team_name) / "controlplane.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # -- Database ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    meeting_id TEXT NOT NULL DEFAULT '',
                    command_id TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL DEFAULT '',
                    causation_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_events_team_time
                    ON events(team_name, occurred_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_project_time
                    ON events(project_id, occurred_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_meeting_time
                    ON events(meeting_id, occurred_at DESC);
                CREATE INDEX IF NOT EXISTS idx_events_session_time
                    ON events(session_id, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    command_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL DEFAULT '',
                    requested_at TEXT NOT NULL,
                    handled_at TEXT NOT NULL DEFAULT '',
                    target_project_id TEXT NOT NULL DEFAULT '',
                    target_session_id TEXT NOT NULL DEFAULT '',
                    target_meeting_id TEXT NOT NULL DEFAULT '',
                    target_agent_name TEXT NOT NULL DEFAULT '',
                    target_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_event_id TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT,
                    error TEXT NOT NULL DEFAULT ''
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_idempotency
                    ON commands(idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_commands_team_time
                    ON commands(team_name, requested_at DESC);

                CREATE TABLE IF NOT EXISTS company_state (
                    team_name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    runtime_status TEXT NOT NULL DEFAULT 'offline',
                    scheduler_status TEXT NOT NULL DEFAULT 'idle',
                    ui_status TEXT NOT NULL DEFAULT 'offline',
                    started_at TEXT NOT NULL DEFAULT '',
                    last_heartbeat_at TEXT NOT NULL DEFAULT '',
                    active_sessions INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    agent_type TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    stage TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    workspace_path TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    tmux_target TEXT NOT NULL DEFAULT '',
                    log_path TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL DEFAULT '',
                    exit_code INTEGER,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    snapshot_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_project
                    ON sessions(project_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_team
                    ON sessions(team_name, started_at DESC);

                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    agenda TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    participants_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    ended_at TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS meeting_messages (
                    message_id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL,
                    team_name TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    speaker TEXT NOT NULL,
                    speaker_type TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_messages_meeting_time
                    ON meeting_messages(meeting_id, created_at ASC);

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    meeting_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_project_time
                    ON artifacts(project_id, created_at DESC);
                """
            )
            conn.commit()

    # -- Events -----------------------------------------------------------

    def append_event(
        self,
        *,
        event_type: str,
        actor: str = "",
        project_id: str = "",
        session_id: str = "",
        meeting_id: str = "",
        command_id: str = "",
        occurred_at: str,
        correlation_id: str = "",
        causation_id: str = "",
        payload: dict[str, Any] | None = None,
        event_id: str = "",
    ) -> str:
        inserted_id = event_id or uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    event_id, team_name, event_type, actor, project_id, session_id,
                    meeting_id, command_id, occurred_at, correlation_id, causation_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inserted_id,
                    self.team_name,
                    event_type,
                    actor,
                    project_id,
                    session_id,
                    meeting_id,
                    command_id,
                    occurred_at,
                    correlation_id,
                    causation_id,
                    _json_dump(payload),
                ),
            )
            conn.commit()
        return inserted_id

    def list_events(
        self,
        *,
        limit: int = 200,
        project_id: str = "",
        session_id: str = "",
        meeting_id: str = "",
        event_type: str = "",
    ) -> list[dict[str, Any]]:
        clauses = ["team_name = ?"]
        params: list[Any] = [self.team_name]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if meeting_id:
            clauses.append("meeting_id = ?")
            params.append(meeting_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM events
                WHERE {' AND '.join(clauses)}
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    # -- Commands ---------------------------------------------------------

    def create_command(self, command: DevCommand) -> DevCommand:
        existing = self.get_command_by_idempotency(command.idempotency_key)
        if existing is not None:
            return existing
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO commands (
                    command_id, team_name, command_type, status, requested_by,
                    requested_at, handled_at, target_project_id, target_session_id,
                    target_meeting_id, target_agent_name, target_json, payload_json,
                    result_event_id, idempotency_key, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.command_id,
                    self.team_name,
                    command.command_type,
                    command.status.value,
                    command.requested_by,
                    command.requested_at,
                    command.handled_at,
                    command.target.project_id,
                    command.target.session_id,
                    command.target.meeting_id,
                    command.target.agent_name,
                    command.target.model_dump_json(),
                    _json_dump(command.payload),
                    command.result_event_id,
                    command.idempotency_key or None,
                    command.error,
                ),
            )
            conn.commit()
        return command

    def get_command(self, command_id: str) -> DevCommand | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        return self._row_to_command(row) if row else None

    def get_command_by_idempotency(self, idempotency_key: str) -> DevCommand | None:
        if not idempotency_key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM commands WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._row_to_command(row) if row else None

    def list_commands(
        self,
        *,
        limit: int = 200,
        status: str = "",
        project_id: str = "",
        meeting_id: str = "",
    ) -> list[DevCommand]:
        clauses = ["team_name = ?"]
        params: list[Any] = [self.team_name]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if project_id:
            clauses.append("target_project_id = ?")
            params.append(project_id)
        if meeting_id:
            clauses.append("target_meeting_id = ?")
            params.append(meeting_id)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM commands
                WHERE {' AND '.join(clauses)}
                ORDER BY requested_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_command(row) for row in rows]

    def update_command(
        self,
        command_id: str,
        *,
        status: DevCommandStatus,
        handled_at: str,
        result_event_id: str = "",
        error: str = "",
    ) -> DevCommand | None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE commands
                SET status = ?, handled_at = ?, result_event_id = ?, error = ?
                WHERE command_id = ?
                """,
                (status.value, handled_at, result_event_id, error, command_id),
            )
            conn.commit()
        return self.get_command(command_id)

    # -- Company state ----------------------------------------------------

    def get_company_state(self) -> DevCompanyState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM company_state WHERE team_name = ?",
                (self.team_name,),
            ).fetchone()
        if row is None:
            return DevCompanyState(team_name=self.team_name)
        return DevCompanyState(
            team_name=row["team_name"],
            status=row["status"],
            runtime_status=row["runtime_status"],
            scheduler_status=row["scheduler_status"],
            ui_status=row["ui_status"],
            started_at=row["started_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            active_sessions=row["active_sessions"],
            errors=_json_load(row["errors_json"], []),
            metadata=_json_load(row["metadata_json"], {}),
        )

    def save_company_state(self, state: DevCompanyState) -> DevCompanyState:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO company_state (
                    team_name, status, runtime_status, scheduler_status, ui_status,
                    started_at, last_heartbeat_at, active_sessions, errors_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    status=excluded.status,
                    runtime_status=excluded.runtime_status,
                    scheduler_status=excluded.scheduler_status,
                    ui_status=excluded.ui_status,
                    started_at=excluded.started_at,
                    last_heartbeat_at=excluded.last_heartbeat_at,
                    active_sessions=excluded.active_sessions,
                    errors_json=excluded.errors_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    state.team_name,
                    state.status.value,
                    state.runtime_status,
                    state.scheduler_status,
                    state.ui_status,
                    state.started_at,
                    state.last_heartbeat_at,
                    state.active_sessions,
                    _json_dump(state.errors),
                    _json_dump(state.metadata),
                ),
            )
            conn.commit()
        return state

    # -- Sessions ---------------------------------------------------------

    def upsert_session(self, session: DevWorkerSession) -> DevWorkerSession:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, team_name, agent_name, agent_id, agent_type,
                    project_id, stage, status, workspace_path, branch, tmux_target,
                    log_path, started_at, last_heartbeat_at, ended_at, exit_code,
                    details_json, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    agent_id=excluded.agent_id,
                    agent_type=excluded.agent_type,
                    project_id=excluded.project_id,
                    stage=excluded.stage,
                    status=excluded.status,
                    workspace_path=excluded.workspace_path,
                    branch=excluded.branch,
                    tmux_target=excluded.tmux_target,
                    log_path=excluded.log_path,
                    last_heartbeat_at=excluded.last_heartbeat_at,
                    ended_at=excluded.ended_at,
                    exit_code=excluded.exit_code,
                    details_json=excluded.details_json,
                    snapshot_json=excluded.snapshot_json
                """,
                (
                    session.session_id,
                    session.team_name,
                    session.agent_name,
                    session.agent_id,
                    session.agent_type,
                    session.project_id,
                    session.stage,
                    session.status.value,
                    session.workspace_path,
                    session.branch,
                    session.tmux_target,
                    session.log_path,
                    session.started_at,
                    session.last_heartbeat_at,
                    session.ended_at,
                    session.exit_code,
                    _json_dump(session.details),
                    _json_dump(session.snapshot),
                ),
            )
            conn.commit()
        return session

    def get_session(self, session_id: str) -> DevWorkerSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(
        self,
        *,
        project_id: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[DevWorkerSession]:
        clauses = ["team_name = ?"]
        params: list[Any] = [self.team_name]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM sessions
                WHERE {' AND '.join(clauses)}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    # -- Meetings ---------------------------------------------------------

    def create_meeting(self, meeting: DevMeeting) -> DevMeeting:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO meetings (
                    meeting_id, team_name, project_id, title, agenda, status,
                    participants_json, created_by, created_at, started_at, ended_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting.meeting_id,
                    meeting.team_name,
                    meeting.project_id,
                    meeting.title,
                    meeting.agenda,
                    meeting.status.value,
                    _json_dump(meeting.participants),
                    meeting.created_by,
                    meeting.created_at,
                    meeting.started_at,
                    meeting.ended_at,
                    _json_dump(meeting.metadata),
                ),
            )
            conn.commit()
        return meeting

    def save_meeting(self, meeting: DevMeeting) -> DevMeeting:
        return self.create_meeting(meeting)

    def get_meeting(self, meeting_id: str) -> DevMeeting | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meetings WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
        return self._row_to_meeting(row) if row else None

    def list_meetings(
        self,
        *,
        project_id: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[DevMeeting]:
        clauses = ["team_name = ?"]
        params: list[Any] = [self.team_name]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM meetings
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_meeting(row) for row in rows]

    def add_meeting_message(self, message: DevMeetingMessage) -> DevMeetingMessage:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO meeting_messages (
                    message_id, meeting_id, team_name, project_id, speaker,
                    speaker_type, body, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.meeting_id,
                    message.team_name,
                    message.project_id,
                    message.speaker,
                    message.speaker_type,
                    message.body,
                    message.created_at,
                    _json_dump(message.metadata),
                ),
            )
            conn.commit()
        return message

    def list_meeting_messages(self, meeting_id: str, *, limit: int = 200) -> list[DevMeetingMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_messages
                WHERE meeting_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (meeting_id, limit),
            ).fetchall()
        return [self._row_to_meeting_message(row) for row in rows]

    # -- Artifacts --------------------------------------------------------

    def add_artifact(self, artifact: DevArtifact) -> DevArtifact:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    artifact_id, team_name, project_id, session_id, meeting_id,
                    kind, title, path, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.team_name,
                    artifact.project_id,
                    artifact.session_id,
                    artifact.meeting_id,
                    artifact.kind,
                    artifact.title,
                    artifact.path,
                    artifact.created_at,
                    _json_dump(artifact.metadata),
                ),
            )
            conn.commit()
        return artifact

    def list_artifacts(
        self,
        *,
        project_id: str = "",
        session_id: str = "",
        meeting_id: str = "",
        limit: int = 100,
    ) -> list[DevArtifact]:
        clauses = ["team_name = ?"]
        params: list[Any] = [self.team_name]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if meeting_id:
            clauses.append("meeting_id = ?")
            params.append(meeting_id)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM artifacts
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    # -- Row conversion ---------------------------------------------------

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "eventId": row["event_id"],
            "teamName": row["team_name"],
            "eventType": row["event_type"],
            "actor": row["actor"],
            "projectId": row["project_id"],
            "sessionId": row["session_id"],
            "meetingId": row["meeting_id"],
            "commandId": row["command_id"],
            "occurredAt": row["occurred_at"],
            "correlationId": row["correlation_id"],
            "causationId": row["causation_id"],
            "payload": _json_load(row["payload_json"], {}),
        }

    def _row_to_command(self, row: sqlite3.Row) -> DevCommand:
        data = {
            "command_id": row["command_id"],
            "command_type": row["command_type"],
            "status": row["status"],
            "requested_by": row["requested_by"],
            "requested_at": row["requested_at"],
            "handled_at": row["handled_at"],
            "target": _json_load(row["target_json"], {}),
            "payload": _json_load(row["payload_json"], {}),
            "result_event_id": row["result_event_id"],
            "idempotency_key": row["idempotency_key"] or "",
            "error": row["error"],
        }
        return DevCommand.model_validate(data)

    def _row_to_session(self, row: sqlite3.Row) -> DevWorkerSession:
        return DevWorkerSession.model_validate(
            {
                "session_id": row["session_id"],
                "team_name": row["team_name"],
                "agent_name": row["agent_name"],
                "agent_id": row["agent_id"],
                "agent_type": row["agent_type"],
                "project_id": row["project_id"],
                "stage": row["stage"],
                "status": row["status"],
                "workspace_path": row["workspace_path"],
                "branch": row["branch"],
                "tmux_target": row["tmux_target"],
                "log_path": row["log_path"],
                "started_at": row["started_at"],
                "last_heartbeat_at": row["last_heartbeat_at"],
                "ended_at": row["ended_at"],
                "exit_code": row["exit_code"],
                "details": _json_load(row["details_json"], {}),
                "snapshot": _json_load(row["snapshot_json"], {}),
            }
        )

    def _row_to_meeting(self, row: sqlite3.Row) -> DevMeeting:
        return DevMeeting.model_validate(
            {
                "meeting_id": row["meeting_id"],
                "team_name": row["team_name"],
                "project_id": row["project_id"],
                "title": row["title"],
                "agenda": row["agenda"],
                "status": row["status"],
                "participants": _json_load(row["participants_json"], []),
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "metadata": _json_load(row["metadata_json"], {}),
            }
        )

    def _row_to_meeting_message(self, row: sqlite3.Row) -> DevMeetingMessage:
        return DevMeetingMessage.model_validate(
            {
                "message_id": row["message_id"],
                "meeting_id": row["meeting_id"],
                "team_name": row["team_name"],
                "project_id": row["project_id"],
                "speaker": row["speaker"],
                "speaker_type": row["speaker_type"],
                "body": row["body"],
                "created_at": row["created_at"],
                "metadata": _json_load(row["metadata_json"], {}),
            }
        )

    def _row_to_artifact(self, row: sqlite3.Row) -> DevArtifact:
        return DevArtifact.model_validate(
            {
                "artifact_id": row["artifact_id"],
                "team_name": row["team_name"],
                "project_id": row["project_id"],
                "session_id": row["session_id"],
                "meeting_id": row["meeting_id"],
                "kind": row["kind"],
                "title": row["title"],
                "path": row["path"],
                "created_at": row["created_at"],
                "metadata": _json_load(row["metadata_json"], {}),
            }
        )
