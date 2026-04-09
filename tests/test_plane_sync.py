from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from clawteam.plane.config import PlaneConfig
from clawteam.plane.models import PlaneState, PlaneWorkItem
from clawteam.plane.sync import PlaneSyncEngine
from clawteam.team.manager import TeamManager
from clawteam.team.models import TaskItem, TaskPriority, TaskStatus


@pytest.fixture
def setup_team(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo", leader_name="leader", leader_id="leader001",
    )
    return "demo"


@pytest.fixture
def plane_config():
    return PlaneConfig(
        url="http://localhost:8082",
        api_key="test-key",
        workspace_slug="test-ws",
        project_id="proj-1",
        sync_enabled=True,
    )


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.list_states.return_value = [
        PlaneState(id="s-pending", name="Pending", group="unstarted"),
        PlaneState(id="s-progress", name="In Progress", group="started"),
        PlaneState(id="s-done", name="Done", group="completed"),
        PlaneState(id="s-blocked", name="Blocked", group="backlog"),
    ]
    return client


def test_push_new_task_creates_plane_work_item(setup_team, plane_config, mock_client):
    mock_client.create_work_item.return_value = PlaneWorkItem(
        id="plane-issue-1", name="Build feature", state="s-pending",
    )

    engine = PlaneSyncEngine(plane_config, client=mock_client)
    from clawteam.store.file import FileTaskStore
    store = FileTaskStore(setup_team)
    task = store.create(subject="Build feature", description="Details")

    engine.push_task(setup_team, task)

    mock_client.create_work_item.assert_called_once()
    updated = store.get(task.id)
    assert updated is not None
    assert updated.metadata["plane_issue_id"] == "plane-issue-1"


def test_push_existing_task_updates_plane_work_item(setup_team, plane_config, mock_client):
    mock_client.update_work_item.return_value = PlaneWorkItem(
        id="plane-issue-1", name="Build feature v2", state="s-progress",
    )

    engine = PlaneSyncEngine(plane_config, client=mock_client)
    from clawteam.store.file import FileTaskStore
    store = FileTaskStore(setup_team)
    task = store.create(
        subject="Build feature",
        metadata={"plane_issue_id": "plane-issue-1"},
    )
    store.update(task.id, subject="Build feature v2", status=TaskStatus.in_progress, caller="test")

    updated_task = store.get(task.id)
    engine.push_task(setup_team, updated_task)

    mock_client.update_work_item.assert_called_once()
    call_args = mock_client.update_work_item.call_args
    assert call_args[0][0] == "proj-1"
    assert call_args[0][1] == "plane-issue-1"


def test_push_skips_when_sync_disabled(setup_team, mock_client):
    config = PlaneConfig(sync_enabled=False)
    engine = PlaneSyncEngine(config, client=mock_client)
    task = TaskItem(subject="test")

    engine.push_task(setup_team, task)

    mock_client.create_work_item.assert_not_called()
    mock_client.update_work_item.assert_not_called()


def test_event_hook_pushes_on_task_update(setup_team, plane_config, mock_client):
    """AfterTaskUpdate event should trigger a push to Plane."""
    mock_client.create_work_item.return_value = PlaneWorkItem(
        id="plane-auto-1", name="Auto task", state="s-pending",
    )
    mock_client.update_work_item.return_value = PlaneWorkItem(
        id="plane-auto-1", name="Auto task", state="s-progress",
    )

    from clawteam.plane import register_sync_hooks
    from clawteam.events.bus import EventBus
    from clawteam.events.types import AfterTaskUpdate

    bus = EventBus()
    engine = PlaneSyncEngine(plane_config, client=mock_client)
    register_sync_hooks(bus, engine, setup_team)

    from clawteam.store.file import FileTaskStore
    store = FileTaskStore(setup_team)
    task = store.create(subject="Auto task")
    engine.push_task(setup_team, task)

    store.update(task.id, status=TaskStatus.in_progress, caller="worker1")
    bus.emit(AfterTaskUpdate(
        team_name=setup_team,
        task_id=task.id,
        old_status="pending",
        new_status="in_progress",
        owner="worker1",
    ))

    assert mock_client.update_work_item.called
