"""Bidirectional sync engine between ClawTeam file store and Plane."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from clawteam.plane.client import PlaneClient, _task_to_plane_payload
from clawteam.plane.config import PlaneConfig
from clawteam.plane.mapping import (
    plane_group_to_clawteam_status,
    resolve_state_id,
)
from clawteam.plane.models import PlaneState, PlaneWorkItem
from clawteam.team.models import TaskItem, TaskPriority, TaskStatus

if TYPE_CHECKING:
    from clawteam.store.base import BaseTaskStore

log = logging.getLogger(__name__)


class PlaneSyncEngine:
    """Syncs ClawTeam tasks with Plane work items."""

    def __init__(self, config: PlaneConfig, client: PlaneClient | None = None):
        self.config = config
        self._client = client or (
            PlaneClient(config.url, config.api_key, config.workspace_slug)
            if config.url and config.api_key
            else None
        )
        self._states: list[PlaneState] | None = None

    def _get_states(self) -> list[PlaneState]:
        if self._states is None:
            self._states = self._client.list_states(self.config.project_id)
        return self._states

    def _resolve_state(self, status: TaskStatus) -> str:
        return resolve_state_id(self._get_states(), status)

    def push_task(self, team_name: str, task: TaskItem) -> None:
        """Push a single task to Plane. Creates or updates based on metadata."""
        if not self.config.sync_enabled or not self._client:
            return

        state_id = self._resolve_state(task.status)
        payload = _task_to_plane_payload(task, state_id)
        plane_id = task.metadata.get("plane_issue_id", "")

        if plane_id:
            self._client.update_work_item(self.config.project_id, plane_id, payload)
            log.info("Updated Plane work item %s for task %s", plane_id, task.id)
        else:
            item = self._client.create_work_item(self.config.project_id, payload)
            from clawteam.store.file import FileTaskStore
            store = FileTaskStore(team_name)
            store.update(task.id, metadata={"plane_issue_id": item.id})
            log.info("Created Plane work item %s for task %s", item.id, task.id)

    def push_all(self, team_name: str) -> int:
        """Push all tasks in a team to Plane. Returns count of items synced."""
        if not self.config.sync_enabled or not self._client:
            return 0

        from clawteam.store.file import FileTaskStore
        store = FileTaskStore(team_name)
        tasks = store.list_tasks()
        count = 0
        for task in tasks:
            try:
                self.push_task(team_name, task)
                count += 1
            except Exception as exc:
                log.warning("Failed to push task %s: %s", task.id, exc)
        return count

    def pull_all(self, team_name: str) -> int:
        """Pull work items from Plane and sync to file store. Returns count synced."""
        if not self.config.sync_enabled or not self._client:
            return 0

        from clawteam.store.file import FileTaskStore
        store = FileTaskStore(team_name)
        existing = store.list_tasks()
        plane_to_task: dict[str, TaskItem] = {}
        for task in existing:
            pid = task.metadata.get("plane_issue_id", "")
            if pid:
                plane_to_task[pid] = task

        items = self._client.list_work_items(self.config.project_id)
        states = self._get_states()
        state_map = {s.id: s for s in states}
        count = 0

        for item in items:
            try:
                state = state_map.get(item.state)
                clawteam_status = (
                    plane_group_to_clawteam_status(state.group)
                    if state
                    else TaskStatus.pending
                )

                if item.id in plane_to_task:
                    task = plane_to_task[item.id]
                    if task.status != clawteam_status or task.subject != item.name:
                        store.update(
                            task.id,
                            status=clawteam_status,
                            subject=item.name,
                            force=True,
                        )
                        count += 1
                else:
                    priority_str = item.priority if item.priority != "none" else "medium"
                    try:
                        priority = TaskPriority(priority_str)
                    except ValueError:
                        priority = TaskPriority.medium
                    store.create(
                        subject=item.name,
                        description=item.description_html,
                        metadata={"plane_issue_id": item.id},
                        priority=priority,
                    )
                    count += 1
            except Exception as exc:
                log.warning("Failed to pull item %s: %s", item.id, exc)

        return count
