"""Bidirectional mapping between ClawTeam task statuses and Plane workflow states."""

from __future__ import annotations

from clawteam.plane.models import PlaneState
from clawteam.team.models import TaskStatus


_STATUS_TO_GROUP: dict[TaskStatus, str] = {
    TaskStatus.pending: "unstarted",
    TaskStatus.in_progress: "started",
    TaskStatus.completed: "completed",
    TaskStatus.blocked: "backlog",
}

_GROUP_TO_STATUS: dict[str, TaskStatus] = {
    "unstarted": TaskStatus.pending,
    "started": TaskStatus.in_progress,
    "completed": TaskStatus.completed,
    "backlog": TaskStatus.blocked,
    "cancelled": TaskStatus.completed,
}


def clawteam_status_to_plane_group(status: TaskStatus) -> str:
    return _STATUS_TO_GROUP[status]


def plane_group_to_clawteam_status(group: str) -> TaskStatus:
    return _GROUP_TO_STATUS.get(group, TaskStatus.pending)


DEFAULT_STATE_NAMES: dict[str, tuple[str, str]] = {
    "pending": ("Pending", "unstarted"),
    "in_progress": ("In Progress", "started"),
    "completed": ("Done", "completed"),
    "blocked": ("Blocked", "backlog"),
    "awaiting_approval": ("Awaiting Approval", "unstarted"),
}


_STATUS_TO_PREFERRED_NAME: dict[TaskStatus, list[str]] = {
    TaskStatus.pending: ["Pending", "Todo", "To Do"],
    TaskStatus.in_progress: ["In Progress", "Working", "Active"],
    TaskStatus.completed: ["Done", "Completed", "Closed"],
    TaskStatus.blocked: ["Blocked", "On Hold"],
}


def resolve_state_id(states: list[PlaneState], status: TaskStatus) -> str:
    """Find the best Plane state ID for a ClawTeam status.

    1. Try matching by preferred display name (case-insensitive).
    2. Fall back to first state in the matching group.
    3. Return empty string if nothing matches.
    """
    preferred = _STATUS_TO_PREFERRED_NAME.get(status, [])
    for name in preferred:
        for s in states:
            if s.name.lower() == name.lower():
                return s.id

    target_group = _STATUS_TO_GROUP.get(status, "")
    for s in states:
        if s.group == target_group:
            return s.id

    return ""
