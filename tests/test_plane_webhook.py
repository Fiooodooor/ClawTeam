from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from clawteam.plane.config import PlaneConfig
from clawteam.plane.webhook import (
    _verify_signature,
    _handle_work_item_event,
    _handle_comment_event,
)
from clawteam.team.manager import TeamManager
from clawteam.team.models import TaskStatus


@pytest.fixture
def setup_team(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    TeamManager.create_team(
        name="demo", leader_name="leader", leader_id="leader001",
    )
    return "demo"


def test_verify_signature_valid():
    secret = "webhook-secret-123"
    body = b'{"event": "issue.updated"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_signature(body, sig, secret) is True


def test_verify_signature_invalid():
    assert _verify_signature(b"body", "bad-sig", "secret") is False


def test_handle_work_item_created_creates_task(setup_team):
    from clawteam.store.file import FileTaskStore

    config = PlaneConfig(
        url="http://localhost:8082",
        api_key="key",
        workspace_slug="ws",
        project_id="proj-1",
        sync_enabled=True,
    )
    payload = {
        "event": "issue",
        "action": "created",
        "data": {
            "id": "plane-new-1",
            "name": "Human-created task",
            "description_html": "<p>Do this</p>",
            "state": "state-1",
            "priority": "high",
        },
    }

    mock_states = {
        "state-1": MagicMock(group="unstarted"),
    }

    result = _handle_work_item_event(payload, config, setup_team, mock_states)

    assert result["action"] == "created"
    store = FileTaskStore(setup_team)
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].subject == "Human-created task"
    assert tasks[0].metadata["plane_issue_id"] == "plane-new-1"


def test_handle_work_item_updated_changes_status(setup_team):
    from clawteam.store.file import FileTaskStore

    store = FileTaskStore(setup_team)
    task = store.create(
        subject="Existing task",
        metadata={"plane_issue_id": "plane-exist-1"},
    )

    config = PlaneConfig(
        url="http://localhost:8082",
        api_key="key",
        workspace_slug="ws",
        project_id="proj-1",
        sync_enabled=True,
    )
    payload = {
        "event": "issue",
        "action": "updated",
        "data": {
            "id": "plane-exist-1",
            "name": "Existing task updated",
            "state": "state-started",
            "priority": "medium",
        },
    }
    mock_states = {
        "state-started": MagicMock(group="started"),
    }

    result = _handle_work_item_event(payload, config, setup_team, mock_states)

    assert result["action"] == "updated"
    updated = store.get(task.id)
    assert updated.status == TaskStatus.in_progress
    assert updated.subject == "Existing task updated"
