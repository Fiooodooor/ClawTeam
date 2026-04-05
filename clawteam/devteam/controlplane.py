"""Persistent control-plane assets for the dev team runtime."""

from __future__ import annotations

import fcntl
import json
import re
from pathlib import Path

from clawteam.devteam.bootstrap import devteam_dir
from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.models import DevActivity, DevRecurringJob


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "job"


class ControlPlaneStore:
    """Stores activities, recurring jobs, and long-lived devteam assets."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.root = devteam_dir(team_name) / "controlplane"
        self.root.mkdir(parents=True, exist_ok=True)
        self.events = DevEventStore(team_name)

    def list_activities(
        self,
        *,
        limit: int = 200,
        project_id: str = "",
    ) -> list[DevActivity]:
        event_rows = self.events.list_events(limit=limit, project_id=project_id)
        items = []
        for row in event_rows:
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if not str(row.get("eventType", "")).startswith("activity."):
                continue
            try:
                items.append(DevActivity.model_validate(payload))
            except Exception:
                continue
        if not items:
            items = [
                DevActivity.model_validate(raw)
                for raw in self._read_list(self.root / "activities.json")
            ]
        if project_id:
            items = [item for item in items if item.project_id == project_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]

    def append_activity(self, activity: DevActivity) -> DevActivity:
        path = self.root / "activities.json"
        items = self._read_list(path)
        items.append(activity.model_dump(mode="json"))
        self._write_list(path, items[-1000:])
        self.events.append_event(
            event_type=f"activity.{activity.kind.value}",
            actor=activity.author,
            project_id=activity.project_id,
            meeting_id=str(activity.metadata.get("meeting_id", "")),
            session_id=str(activity.metadata.get("session_id", "")),
            occurred_at=activity.created_at,
            payload=activity.model_dump(mode="json"),
        )
        return activity

    def record_activity(self, **kwargs) -> DevActivity:
        return self.append_activity(DevActivity(**kwargs))

    def list_jobs(self, *, include_disabled: bool = False) -> list[DevRecurringJob]:
        jobs = [
            DevRecurringJob.model_validate(raw)
            for raw in self._read_list(self.root / "jobs.json")
        ]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        if include_disabled:
            return jobs
        return [job for job in jobs if job.enabled]

    def get_job(self, key: str) -> DevRecurringJob | None:
        for job in self.list_jobs(include_disabled=True):
            if job.key == key:
                return job
        return None

    def create_job(
        self,
        *,
        title: str,
        cadence: str,
        owner: str,
        instruction: str,
        channels: list[str] | None = None,
        created_by: str = "",
        key: str = "",
        metadata: dict | None = None,
    ) -> DevRecurringJob:
        job = DevRecurringJob(
            key=key or _slugify(title),
            title=title,
            cadence=cadence,
            owner=owner,
            instruction=instruction,
            channels=channels or [],
            created_by=created_by,
            metadata=metadata or {},
        )
        return self.save_job(job)

    def save_job(self, job: DevRecurringJob) -> DevRecurringJob:
        path = self.root / "jobs.json"
        items = [
            DevRecurringJob.model_validate(raw)
            for raw in self._read_list(path)
        ]
        remaining = [item for item in items if item.key != job.key]
        remaining.append(job)
        remaining.sort(key=lambda item: item.created_at, reverse=True)
        self._write_list(
            path,
            [item.model_dump(mode="json") for item in remaining],
        )
        self.events.append_event(
            event_type="job.saved",
            actor=job.created_by or job.owner,
            occurred_at=job.created_at,
            payload=job.model_dump(mode="json"),
        )
        return job

    def mark_job_run(self, key: str, run_at: str) -> DevRecurringJob | None:
        job = self.get_job(key)
        if job is None:
            return None
        job.last_run_at = run_at
        saved = self.save_job(job)
        self.events.append_event(
            event_type="job.ran",
            actor=job.owner,
            occurred_at=run_at,
            payload=saved.model_dump(mode="json"),
        )
        return saved

    def _read_list(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        return []

    def _write_list(self, path: Path, payload: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp.replace(path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
