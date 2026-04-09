from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawteam.plane.client import PlaneClient
from clawteam.plane.models import PlaneState, PlaneWorkItem


@pytest.fixture
def client():
    return PlaneClient(
        base_url="http://localhost:8082",
        api_key="pl_test_key",
        workspace_slug="test-ws",
    )


def test_client_init(client: PlaneClient):
    assert client.base_url == "http://localhost:8082"
    assert client.workspace_slug == "test-ws"


def test_client_headers(client: PlaneClient):
    headers = client._headers()
    assert headers["X-API-Key"] == "pl_test_key"
    assert headers["Content-Type"] == "application/json"


def test_client_build_url(client: PlaneClient):
    url = client._url("projects", "proj1", "work-items")
    assert url == "http://localhost:8082/api/v1/workspaces/test-ws/projects/proj1/work-items/"


def test_work_item_to_plane_payload():
    from clawteam.plane.client import _task_to_plane_payload
    from clawteam.team.models import TaskItem, TaskPriority, TaskStatus

    task = TaskItem(
        id="abc123",
        subject="Fix the bug",
        description="Detailed description",
        status=TaskStatus.in_progress,
        priority=TaskPriority.high,
        owner="worker1",
    )
    payload = _task_to_plane_payload(task, state_id="state-uuid-started")
    assert payload["name"] == "Fix the bug"
    assert payload["description_html"] == "<p>Detailed description</p>"
    assert payload["state"] == "state-uuid-started"
    assert payload["priority"] == "high"
