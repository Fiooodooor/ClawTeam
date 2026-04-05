"""Cadence parsing and persistent scheduler state for investment runtime."""

from __future__ import annotations

import fcntl
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from clawteam.investment.bootstrap import investment_dir
from clawteam.investment.models import ScheduleSpec


class CadenceParseError(ValueError):
    """Raised when a schedule cadence cannot be parsed."""


@dataclass(frozen=True)
class DueSchedule:
    key: str
    slot_key: str
    schedule: ScheduleSpec


class SchedulerStore:
    """Persistent schedule slot tracking."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self.path = investment_dir(team_name) / "scheduler.json"

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

    def due_schedules(self, schedules: list[ScheduleSpec], now: datetime) -> list[DueSchedule]:
        state = self.load()
        due: list[DueSchedule] = []
        for schedule in schedules:
            slot = slot_key_for_cadence(schedule.cadence, now)
            if slot is None:
                continue
            if state.get(schedule.key) != slot:
                due.append(DueSchedule(key=schedule.key, slot_key=slot, schedule=schedule))
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
        epoch = int(now.timestamp())
        slot = epoch // seconds
        return f"every:{amount}{unit}:{slot}"

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

    weekly_match = re.fullmatch(
        r"weekly\s+(mon|tue|wed|thu|fri|sat|sun)\s+(\d{2}):(\d{2})\s+local", cadence
    )
    if weekly_match:
        weekday = _weekday_index(weekly_match.group(1))
        scheduled = now.replace(
            hour=int(weekly_match.group(2)),
            minute=int(weekly_match.group(3)),
            second=0,
            microsecond=0,
        )
        if now.weekday() != weekday or now < scheduled:
            return None
        week_start = (scheduled - timedelta(days=scheduled.weekday())).date().isoformat()
        return f"weekly:{week_start}:{weekly_match.group(1)}:{weekly_match.group(2)}:{weekly_match.group(3)}"

    raise CadenceParseError(f"Unsupported cadence: {cadence}")


def _weekday_index(name: str) -> int:
    weekdays = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }
    return weekdays[name]
