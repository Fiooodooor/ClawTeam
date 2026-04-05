"""In-process company supervisor for local-first devteam runtime orchestration."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.models import DevCompanyState, DevCompanyStatus
from clawteam.devteam.runtime import DevTeamOperatingRuntime


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CompanySupervisor:
    """Runs the devteam runtime loop in a background thread and tracks company status."""

    def __init__(
        self,
        team_name: str,
        *,
        workspace_dir: str | None = None,
        runtime_factory: Callable[..., DevTeamOperatingRuntime] = DevTeamOperatingRuntime,
        poll_interval_seconds: float = 1.0,
    ):
        self.team_name = team_name
        self.workspace_dir = workspace_dir
        self.runtime_factory = runtime_factory
        self.poll_interval_seconds = poll_interval_seconds
        self.events = DevEventStore(team_name)
        self._runtime: DevTeamOperatingRuntime | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> DevCompanyState:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            state = self.events.get_company_state()
            state.status = DevCompanyStatus.starting
            state.runtime_status = "starting"
            state.scheduler_status = "online"
            state.ui_status = "online"
            state.started_at = state.started_at or _now_iso()
            state.last_heartbeat_at = _now_iso()
            self.events.save_company_state(state)
            self.events.append_event(
                event_type="company.started",
                actor="supervisor",
                occurred_at=state.last_heartbeat_at,
                payload=state.model_dump(mode="json"),
            )
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"clawteam-company-{self.team_name}",
                daemon=True,
            )
            self._thread.start()
            return self.status()

    def stop(self) -> DevCompanyState:
        with self._lock:
            state = self.events.get_company_state()
            state.status = DevCompanyStatus.stopping
            state.runtime_status = "stopping"
            state.last_heartbeat_at = _now_iso()
            self.events.save_company_state(state)
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(self.poll_interval_seconds * 4, 1.0))
        with self._lock:
            if self._runtime is not None:
                try:
                    self._runtime.close()
                except Exception:
                    pass
                self._runtime = None
            self._thread = None
            state = self.events.get_company_state()
            state.status = DevCompanyStatus.stopped
            state.runtime_status = "offline"
            state.scheduler_status = "idle"
            state.last_heartbeat_at = _now_iso()
            self.events.save_company_state(state)
            self.events.append_event(
                event_type="company.stopped",
                actor="supervisor",
                occurred_at=state.last_heartbeat_at,
                payload=state.model_dump(mode="json"),
            )
            return state

    def restart(self) -> DevCompanyState:
        self.stop()
        return self.start()

    def status(self) -> DevCompanyState:
        state = self.events.get_company_state()
        sessions = self.events.list_sessions(limit=200)
        state.active_sessions = len([session for session in sessions if session.ended_at == ""])
        return self.events.save_company_state(state)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        runtime_error: Exception | None = None
        try:
            self._runtime = self.runtime_factory(
                team_name=self.team_name,
                workspace_dir=self.workspace_dir,
            )
            while not self._stop_event.is_set():
                result = self._runtime.run_once()
                state = self.events.get_company_state()
                state.status = DevCompanyStatus.online
                state.runtime_status = str(result.get("mode") or "online")
                state.scheduler_status = "online"
                state.ui_status = "online"
                state.last_heartbeat_at = _now_iso()
                runtime_errors = list(self._runtime.state.metadata.get("runtime_errors", []))[-20:]
                state.errors = runtime_errors
                sessions = self.events.list_sessions(limit=200)
                state.active_sessions = len([session for session in sessions if session.ended_at == ""])
                self.events.save_company_state(state)
                self.events.append_event(
                    event_type="runtime.heartbeat",
                    actor="runtime",
                    occurred_at=state.last_heartbeat_at,
                    payload={"mode": state.runtime_status, "activeSessions": state.active_sessions},
                )
                time.sleep(self.poll_interval_seconds)
        except Exception as exc:
            runtime_error = exc
        finally:
            if self._runtime is not None:
                try:
                    self._runtime.close()
                except Exception:
                    pass
            state = self.events.get_company_state()
            state.last_heartbeat_at = _now_iso()
            if runtime_error is not None and not self._stop_event.is_set():
                state.status = DevCompanyStatus.degraded
                state.runtime_status = "error"
                state.errors = [*state.errors[-19:], {"at": state.last_heartbeat_at, "error": str(runtime_error)}]
                self.events.append_event(
                    event_type="runtime.error",
                    actor="supervisor",
                    occurred_at=state.last_heartbeat_at,
                    payload={"error": str(runtime_error)},
                )
            elif self._stop_event.is_set():
                state.status = DevCompanyStatus.stopped
                state.runtime_status = "offline"
            self.events.save_company_state(state)


_SUPERVISORS: dict[str, CompanySupervisor] = {}


def get_company_supervisor(team_name: str, *, workspace_dir: str | None = None) -> CompanySupervisor:
    supervisor = _SUPERVISORS.get(team_name)
    if supervisor is None:
        supervisor = CompanySupervisor(team_name, workspace_dir=workspace_dir)
        _SUPERVISORS[team_name] = supervisor
    return supervisor
