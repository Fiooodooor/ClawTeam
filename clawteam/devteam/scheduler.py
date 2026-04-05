"""Cadence parsing and persistent scheduler state for dev team runtime."""

from __future__ import annotations

import fcntl
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from clawteam.devteam.models import ScheduleSpec
from clawteam.team.models import get_data_dir


def _devteam_dir(team_name: str) -> Path:
    path = get_data_dir() / "teams" / team_name / "devteam"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class DueSchedule:
    key: str
    slot_key: str
    schedule: ScheduleSpec


class SchedulerStore:
    """Persistent schedule slot tracking for dev team runtime."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.path = _devteam_dir(team_name) / "scheduler.json"

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            with lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
                try:
                    return json.loads(self.path.read_text(encoding="utf-8"))
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            return {}

    def save(self, data: dict[str, str]) -> None:
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def due_schedules(
        self, schedules: list[ScheduleSpec], now: datetime
    ) -> list[DueSchedule]:
        state = self.load()
        due: list[DueSchedule] = []
        for schedule in schedules:
            slot = slot_key_for_cadence(schedule.cadence, now)
            if slot is None:
                continue
            if state.get(schedule.key) != slot:
                due.append(
                    DueSchedule(key=schedule.key, slot_key=slot, schedule=schedule)
                )
        return due

    def mark_run(self, due_schedule: DueSchedule) -> None:
        state = self.load()
        state[due_schedule.key] = due_schedule.slot_key
        self.save(state)


def slot_key_for_cadence(cadence: str, now: datetime) -> str | None:
    cadence = cadence.strip().lower()

    every_match = re.fullmatch(r"every\s+(\d+)([mh])", cadence)
    if every_match:
        amount = int(every_match.group(1))
        unit = every_match.group(2)
        seconds = amount * 60 if unit == "m" else amount * 3600
        slot = int(now.timestamp()) // seconds
        return f"every:{amount}{unit}:{slot}"

    # "weekdays HH:MM TZ" pattern
    weekday_match = re.fullmatch(r"weekdays\s+(\d{2}):(\d{2})\s+\S+", cadence)
    if weekday_match:
        if now.weekday() >= 5:  # Saturday or Sunday
            return None
        scheduled = now.replace(
            hour=int(weekday_match.group(1)),
            minute=int(weekday_match.group(2)),
            second=0,
            microsecond=0,
        )
        if now < scheduled:
            return None
        return f"weekdays:{scheduled.date().isoformat()}:{weekday_match.group(1)}:{weekday_match.group(2)}"

    # "friday HH:MM TZ" or "monday HH:MM TZ" etc.
    day_match = re.fullmatch(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{2}):(\d{2})\s+\S+",
        cadence,
    )
    if day_match:
        weekday = _weekday_index(day_match.group(1))
        if now.weekday() != weekday:
            return None
        scheduled = now.replace(
            hour=int(day_match.group(2)),
            minute=int(day_match.group(3)),
            second=0,
            microsecond=0,
        )
        if now < scheduled:
            return None
        week_start = (scheduled - timedelta(days=scheduled.weekday())).date().isoformat()
        return f"weekly:{week_start}:{day_match.group(1)}:{day_match.group(2)}:{day_match.group(3)}"

    # Fallback: daily HH:MM local
    daily_match = re.fullmatch(r"daily\s+(\d{2}):(\d{2})\s+local", cadence)
    if daily_match:
        scheduled = now.replace(
            hour=int(daily_match.group(1)),
            minute=int(daily_match.group(2)),
            second=0,
            microsecond=0,
        )
        if now < scheduled:
            return None
        return f"daily:{scheduled.date().isoformat()}:{daily_match.group(1)}:{daily_match.group(2)}"

    return None  # Unknown cadence format, skip gracefully


def _weekday_index(name: str) -> int:
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    return weekdays.get(name, 0)
