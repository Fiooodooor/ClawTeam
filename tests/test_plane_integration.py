"""End-to-end integration test for the full Plane sync + HITL cycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from clawteam.plane.config import PlaneConfig
from clawteam.plane.models import PlaneState, PlaneWorkItem
from clawteam.plane.sync import PlaneSyncEngine
from clawteam.plane.webhook import _handle_work_item_event, _handle_comment_event
from clawteam.store.file import FileTaskStore
from clawteam.team.manager import TeamManager
from clawteam.team.models import TaskStatus


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="integration", leader_name="leader", leader_id="leader001",
    )
    TeamManager.add_member("integration", "worker1", "worker001")
    return "integration"


@pytest.fixture
def config():
    return PlaneConfig(
        url="http://localhost:8082",
        api_key="test-key",
        workspace_slug="test-ws",
        project_id="proj-1",
        sync_enabled=True,
    )


@pytest.fixture
def states():
    return [
        PlaneState(id="s-pending", name="Pending", group="unstarted"),
        PlaneState(id="s-progress", name="In Progress", group="started"),
        PlaneState(id="s-done", name="Done", group="completed"),
        PlaneState(id="s-blocked", name="Blocked", group="backlog"),
        PlaneState(id="s-approval", name="Awaiting Approval", group="unstarted"),
    ]


def test_full_round_trip(env, config, states):
    """
    1. Agent creates task in file store
    2. Push to Plane (mocked)
    3. Human changes state in Plane -> webhook fires
    4. File store updates
    """
    team = env
    store = FileTaskStore(team)

    task = store.create(subject="Implement login", owner="worker1")
    assert task.status == TaskStatus.pending

    mock_client = MagicMock()
    mock_client.list_states.return_value = states
    mock_client.create_work_item.return_value = PlaneWorkItem(
        id="plane-rt-1", name="Implement login", state="s-pending",
    )
    engine = PlaneSyncEngine(config, client=mock_client)
    engine.push_task(team, task)

    updated_task = store.get(task.id)
    assert updated_task.metadata["plane_issue_id"] == "plane-rt-1"

    state_lookup = {s.id: s for s in states}
    result = _handle_work_item_event(
        {
            "event": "issue",
            "action": "updated",
            "data": {
                "id": "plane-rt-1",
                "name": "Implement login",
                "state": "s-progress",
                "priority": "medium",
            },
        },
        config, team, state_lookup,
    )
    assert result["action"] == "updated"

    final = store.get(task.id)
    assert final.status == TaskStatus.in_progress


def test_hitl_approval_via_comment(env, config, states):
    """
    1. Task exists with plane_issue_id
    2. Human comments "APPROVED" on Plane issue
    3. Webhook triggers -> task moves to in_progress + HITL message sent
    """
    team = env
    store = FileTaskStore(team)
    task = store.create(
        subject="Deploy to staging",
        owner="worker1",
        metadata={"plane_issue_id": "plane-hitl-1"},
    )

    result = _handle_comment_event(
        {
            "event": "issue_comment",
            "action": "created",
            "data": {
                "comment_html": "<p>APPROVED - looks good!</p>",
                "issue": "plane-hitl-1",
                "actor_detail": {"display_name": "Alice"},
                "created_at": "2026-04-09T12:00:00Z",
            },
        },
        config, team,
    )

    assert result["action"] == "approved"
    updated = store.get(task.id)
    assert updated.status == TaskStatus.in_progress


def test_human_creates_task_in_plane_syncs_to_file(env, config, states):
    """Human creates a task directly in Plane -> webhook -> appears in file store."""
    team = env
    state_lookup = {s.id: s for s in states}

    result = _handle_work_item_event(
        {
            "event": "issue",
            "action": "created",
            "data": {
                "id": "plane-human-1",
                "name": "Review architecture doc",
                "description_html": "<p>Please review</p>",
                "state": "s-pending",
                "priority": "high",
            },
        },
        config, team, state_lookup,
    )

    assert result["action"] == "created"
    store = FileTaskStore(team)
    tasks = store.list_tasks()
    human_task = next(t for t in tasks if t.metadata.get("plane_issue_id") == "plane-human-1")
    assert human_task.subject == "Review architecture doc"
    assert human_task.priority.value == "high"
