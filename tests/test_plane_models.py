from __future__ import annotations

from clawteam.plane.models import (
    PlaneProject,
    PlaneState,
    PlaneWorkItem,
    PlaneComment,
    PlaneWorkspace,
)


def test_work_item_from_api_response():
    data = {
        "id": "abc-123",
        "name": "Fix login bug",
        "description_html": "<p>Details here</p>",
        "state": "state-uuid-1",
        "priority": "high",
        "assignees": ["user-1"],
        "labels": ["label-1"],
        "created_at": "2026-04-09T10:00:00Z",
        "updated_at": "2026-04-09T11:00:00Z",
        "sequence_id": 42,
        "project": "proj-uuid",
    }
    item = PlaneWorkItem.model_validate(data)
    assert item.id == "abc-123"
    assert item.name == "Fix login bug"
    assert item.state == "state-uuid-1"
    assert item.priority == "high"
    assert item.assignees == ["user-1"]
    assert item.sequence_id == 42


def test_state_from_api_response():
    data = {
        "id": "state-uuid-1",
        "name": "In Progress",
        "group": "started",
        "color": "#f59e0b",
        "sequence": 2,
    }
    state = PlaneState.model_validate(data)
    assert state.id == "state-uuid-1"
    assert state.name == "In Progress"
    assert state.group == "started"


def test_comment_from_api_response():
    data = {
        "id": "comment-1",
        "comment_html": "<p>Approved</p>",
        "actor_detail": {"display_name": "Alice"},
        "created_at": "2026-04-09T12:00:00Z",
    }
    comment = PlaneComment.model_validate(data)
    assert comment.id == "comment-1"
    assert comment.actor_detail["display_name"] == "Alice"


def test_work_item_extra_fields_ignored():
    data = {
        "id": "abc-123",
        "name": "task",
        "state": "s1",
        "priority": "none",
        "unknown_future_field": True,
    }
    item = PlaneWorkItem.model_validate(data)
    assert item.id == "abc-123"
