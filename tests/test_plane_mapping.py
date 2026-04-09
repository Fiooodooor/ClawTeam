from __future__ import annotations

from clawteam.plane.mapping import (
    clawteam_status_to_plane_group,
    plane_group_to_clawteam_status,
    DEFAULT_STATE_NAMES,
    resolve_state_id,
)
from clawteam.plane.models import PlaneState
from clawteam.team.models import TaskStatus


def test_clawteam_to_plane_group():
    assert clawteam_status_to_plane_group(TaskStatus.pending) == "unstarted"
    assert clawteam_status_to_plane_group(TaskStatus.in_progress) == "started"
    assert clawteam_status_to_plane_group(TaskStatus.completed) == "completed"
    assert clawteam_status_to_plane_group(TaskStatus.blocked) == "backlog"


def test_plane_group_to_clawteam():
    assert plane_group_to_clawteam_status("unstarted") == TaskStatus.pending
    assert plane_group_to_clawteam_status("started") == TaskStatus.in_progress
    assert plane_group_to_clawteam_status("completed") == TaskStatus.completed
    assert plane_group_to_clawteam_status("backlog") == TaskStatus.blocked
    assert plane_group_to_clawteam_status("cancelled") == TaskStatus.completed


def test_default_state_names():
    assert "pending" in DEFAULT_STATE_NAMES
    assert "in_progress" in DEFAULT_STATE_NAMES
    assert "completed" in DEFAULT_STATE_NAMES
    assert "blocked" in DEFAULT_STATE_NAMES
    assert "awaiting_approval" in DEFAULT_STATE_NAMES


def test_resolve_state_id():
    states = [
        PlaneState(id="s1", name="Pending", group="unstarted"),
        PlaneState(id="s2", name="In Progress", group="started"),
        PlaneState(id="s3", name="Done", group="completed"),
        PlaneState(id="s4", name="Blocked", group="backlog"),
    ]
    assert resolve_state_id(states, TaskStatus.pending) == "s1"
    assert resolve_state_id(states, TaskStatus.in_progress) == "s2"
    assert resolve_state_id(states, TaskStatus.completed) == "s3"
    assert resolve_state_id(states, TaskStatus.blocked) == "s4"


def test_resolve_state_id_fallback_by_group():
    states = [
        PlaneState(id="s1", name="Todo", group="unstarted"),
        PlaneState(id="s2", name="Working", group="started"),
    ]
    assert resolve_state_id(states, TaskStatus.pending) == "s1"
    assert resolve_state_id(states, TaskStatus.in_progress) == "s2"
