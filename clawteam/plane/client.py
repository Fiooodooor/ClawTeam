"""Low-level Plane REST API client using httpx."""

from __future__ import annotations

from typing import Any

import httpx

from clawteam.plane.models import (
    PlaneComment,
    PlaneProject,
    PlaneState,
    PlaneWorkItem,
    PlaneWorkspace,
)
from clawteam.team.models import TaskItem


_CLAWTEAM_TO_PLANE_PRIORITY = {
    "urgent": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_PLANE_TO_CLAWTEAM_PRIORITY = {v: k for k, v in _CLAWTEAM_TO_PLANE_PRIORITY.items()}
_PLANE_TO_CLAWTEAM_PRIORITY["none"] = "medium"


def _task_to_plane_payload(task: TaskItem, state_id: str) -> dict[str, Any]:
    """Convert a ClawTeam TaskItem to a Plane work item creation/update payload."""
    desc_html = f"<p>{task.description}</p>" if task.description else ""
    return {
        "name": task.subject,
        "description_html": desc_html,
        "state": state_id,
        "priority": _CLAWTEAM_TO_PLANE_PRIORITY.get(task.priority.value, "medium"),
    }


class PlaneClient:
    """Synchronous HTTP client for the Plane REST API."""

    def __init__(self, base_url: str, api_key: str, workspace_slug: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.workspace_slug = workspace_slug
        self._http = httpx.Client(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, *parts: str) -> str:
        path = "/".join(parts)
        return f"{self.base_url}/api/v1/workspaces/{self.workspace_slug}/{path}/"

    def _get(self, *parts: str, params: dict | None = None) -> Any:
        resp = self._http.get(self._url(*parts), headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, *parts: str, json_data: dict | None = None) -> Any:
        resp = self._http.post(self._url(*parts), headers=self._headers(), json=json_data)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, *parts: str, json_data: dict | None = None) -> Any:
        resp = self._http.patch(self._url(*parts), headers=self._headers(), json=json_data)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()

    def list_projects(self) -> list[PlaneProject]:
        data = self._get("projects")
        results = data.get("results", data) if isinstance(data, dict) else data
        return [PlaneProject.model_validate(p) for p in results]

    def get_project(self, project_id: str) -> PlaneProject:
        data = self._get("projects", project_id)
        return PlaneProject.model_validate(data)

    def list_states(self, project_id: str) -> list[PlaneState]:
        data = self._get("projects", project_id, "states")
        results = data.get("results", data) if isinstance(data, dict) else data
        return [PlaneState.model_validate(s) for s in results]

    def create_state(self, project_id: str, name: str, group: str, color: str = "#6b7280") -> PlaneState:
        data = self._post("projects", project_id, "states", json_data={
            "name": name, "group": group, "color": color,
        })
        return PlaneState.model_validate(data)

    def list_work_items(self, project_id: str) -> list[PlaneWorkItem]:
        data = self._get("projects", project_id, "work-items")
        results = data.get("results", data) if isinstance(data, dict) else data
        return [PlaneWorkItem.model_validate(i) for i in results]

    def get_work_item(self, project_id: str, item_id: str) -> PlaneWorkItem:
        data = self._get("projects", project_id, "work-items", item_id)
        return PlaneWorkItem.model_validate(data)

    def create_work_item(self, project_id: str, payload: dict) -> PlaneWorkItem:
        data = self._post("projects", project_id, "work-items", json_data=payload)
        return PlaneWorkItem.model_validate(data)

    def update_work_item(self, project_id: str, item_id: str, payload: dict) -> PlaneWorkItem:
        data = self._patch("projects", project_id, "work-items", item_id, json_data=payload)
        return PlaneWorkItem.model_validate(data)

    def list_comments(self, project_id: str, item_id: str) -> list[PlaneComment]:
        data = self._get("projects", project_id, "work-items", item_id, "comments")
        results = data.get("results", data) if isinstance(data, dict) else data
        return [PlaneComment.model_validate(c) for c in results]

    def create_comment(self, project_id: str, item_id: str, html: str) -> PlaneComment:
        data = self._post(
            "projects", project_id, "work-items", item_id, "comments",
            json_data={"comment_html": html},
        )
        return PlaneComment.model_validate(data)
