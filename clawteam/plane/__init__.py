"""Plane integration for ClawTeam — bidirectional sync with Plane project management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawteam.events.bus import EventBus
    from clawteam.plane.sync import PlaneSyncEngine

log = logging.getLogger(__name__)


def register_sync_hooks(bus: EventBus, engine: PlaneSyncEngine, team_name: str) -> None:
    """Subscribe to task events and auto-push changes to Plane."""
    from clawteam.events.types import AfterTaskUpdate
    from clawteam.store.file import FileTaskStore

    def _on_task_update(event: AfterTaskUpdate) -> None:
        if event.team_name != team_name:
            return
        try:
            store = FileTaskStore(event.team_name)
            task = store.get(event.task_id)
            if task:
                engine.push_task(event.team_name, task)
        except Exception as exc:
            log.warning("Plane sync failed for task %s: %s", event.task_id, exc)

    bus.subscribe(AfterTaskUpdate, _on_task_update)


__all__ = ["register_sync_hooks"]
