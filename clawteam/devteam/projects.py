"""Project persistence and Slack thread binding for the dev team runtime."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from clawteam.devteam.models import (
    DevProject,
    DevTeamRuntimeState,
    ProjectStatus,
    ProjectThreadRef,
    ProjectType,
    SprintStage,
)
from clawteam.devteam.workflow import SprintWorkflow


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "project"


class ProjectManager:
    """Loads, saves, and binds dev projects to Slack threads."""

    def __init__(
        self,
        team_name: str,
        workspace_dir: str | None = None,
        workflow: SprintWorkflow | None = None,
    ):
        self.team_name = team_name
        self.workspace_dir = (
            Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        )
        self.shared_projects_dir = self.workspace_dir / "shared" / "projects"
        self.workflow = workflow or SprintWorkflow()

    # -- CRUD ---------------------------------------------------------------

    def list_projects(self) -> list[DevProject]:
        if not self.shared_projects_dir.exists():
            return []
        projects: list[DevProject] = []
        for path in sorted(self.shared_projects_dir.glob("**/*.json")):
            try:
                projects.append(self._load_project_path(path))
            except Exception:
                continue
        return projects

    def get_project(self, project_id: str) -> DevProject | None:
        path = self._find_project_path(project_id)
        if path is None:
            return None
        return self._load_project_path(path)

    def save_project(self, project: DevProject) -> DevProject:
        path = self._find_project_path(project.project_id)
        if path is None:
            path = self._new_project_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        return project

    def open_project(
        self,
        title: str,
        project_type: ProjectType = ProjectType.feature,
        description: str = "",
        assigned_agents: list[str] | None = None,
        repository: str = "",
        source_channel: str = "",
        source_thread_ts: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DevProject:
        project_id = self._build_project_id(project_type.value, title, source_thread_ts)
        project = DevProject(
            project_id=project_id,
            project_type=project_type,
            title=title,
            description=description,
            assigned_agents=assigned_agents or [],
            repository=repository,
            metadata={
                "source_channel": source_channel,
                "source_thread_ts": source_thread_ts,
                **(metadata or {}),
            },
        )
        return self.save_project(project)

    # -- Thread binding -----------------------------------------------------

    def find_project_by_thread(
        self, channel_id: str, thread_ts: str
    ) -> DevProject | None:
        for project in self.list_projects():
            if (
                project.thread
                and project.thread.channel == channel_id
                and project.thread.thread_ts == thread_ts
            ):
                return project
        return None

    def ensure_project_thread(
        self,
        project_id: str,
        slack_client: Any,
        channel_name: str,
        private: bool = False,
        channel_info: dict[str, Any] | None = None,
    ) -> tuple[DevProject, bool]:
        """Bind project to Slack thread. Returns (project, created_thread)."""
        project = self.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        channel_info = channel_info or slack_client.ensure_channel(
            channel_name, private=private
        )
        channel_id = channel_info["id"]

        if project.thread and project.thread.thread_ts:
            project.thread = project.thread.model_copy(
                update={"channel": channel_id, "channel_name": channel_name}
            )
            self.save_project(project)
            return project, False

        response = slack_client.post_message(
            channel_id,
            self._project_summary(project),
            metadata={
                "event_type": "clawteam_project_opened",
                "event_payload": {
                    "team": self.team_name,
                    "project_id": project.project_id,
                    "project_type": project.project_type.value,
                },
            },
        )
        ts = response.get("ts", "")
        project.thread = ProjectThreadRef(
            channel=channel_id,
            channel_name=channel_name,
            thread_ts=ts,
            root_ts=ts,
            last_message_ts=ts,
        )
        self.save_project(project)
        return project, True

    def bind_existing_thread(
        self,
        project_id: str,
        channel_id: str,
        channel_name: str,
        thread_ts: str,
        last_message_ts: str = "",
    ) -> DevProject:
        project = self.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        project.thread = ProjectThreadRef(
            channel=channel_id,
            channel_name=channel_name,
            thread_ts=thread_ts,
            root_ts=thread_ts,
            last_message_ts=last_message_ts or thread_ts,
        )
        return self.save_project(project)

    def update_project_activity(
        self, project: DevProject, message_ts: str
    ) -> DevProject:
        if project.thread:
            project.thread.last_message_ts = message_ts
        project.metadata["last_activity_ts"] = message_ts
        return self.save_project(project)

    def advance_stage(
        self, project: DevProject, human_approved: bool = False
    ) -> DevProject:
        workflow = SprintWorkflow.for_project_type(project.project_type.value)
        project = workflow.advance(project, human_approved=human_approved)
        return self.save_project(project)

    # -- Channel resolution -------------------------------------------------

    def resolve_channel_name(self, project: DevProject) -> str:
        if project.thread and project.thread.channel_name:
            return project.thread.channel_name
        channel_name = str(project.metadata.get("channel_name", "")).strip()
        if channel_name:
            return channel_name
        mapping = {
            SprintStage.intake: "dev-intake",
            SprintStage.think: "dev-architecture",
            SprintStage.plan: "dev-architecture",
            SprintStage.build: "dev-implementation",
            SprintStage.review: "dev-review",
            SprintStage.test: "dev-testing",
            SprintStage.security: "dev-review",
            SprintStage.ship: "dev-ops",
            SprintStage.reflect: "dev-standup",
        }
        return mapping.get(project.stage, "dev-intake")

    def delete_project(self, project_id: str) -> bool:
        """Delete a project file. Returns True if deleted, False if not found."""
        path = self._find_project_path(project_id)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        return True

    # -- Internal -----------------------------------------------------------

    def _find_project_path(self, project_id: str) -> Path | None:
        if not self.shared_projects_dir.exists():
            return None
        for path in self.shared_projects_dir.glob("**/*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("project_id") == project_id:
                return path
        return None

    def _new_project_path(self, project: DevProject) -> Path:
        return (
            self.shared_projects_dir
            / project.project_type.value
            / f"{_slugify(project.title)}.json"
        )

    def _load_project_path(self, path: Path) -> DevProject:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DevProject.model_validate(data)

    def _project_summary(self, project: DevProject) -> str:
        lines = [
            f"*{project.title}*",
            f"Project: `{project.project_id}`",
            f"Type: {project.project_type.value}",
            f"Stage: {project.stage.value}",
        ]
        if project.description:
            lines.append(f"Description: {project.description[:200]}")
        if project.assigned_agents:
            lines.append(f"Team: {', '.join(project.assigned_agents)}")
        return "\n".join(lines)

    def _build_project_id(
        self, project_type: str, title: str, source_thread_ts: str
    ) -> str:
        base = f"{project_type}-{_slugify(title)}"
        if source_thread_ts:
            suffix = source_thread_ts.replace(".", "-")
            return f"{base}-{suffix}"
        return base
