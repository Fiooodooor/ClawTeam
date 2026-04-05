"""Web/UI control-plane operations for the dev team runtime."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

from clawteam.devteam.autonomy import DevConversationEngine
from clawteam.devteam.bootstrap import load_runtime_blueprint
from clawteam.devteam.controlplane import ControlPlaneStore
from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.meetings import MeetingManager
from clawteam.devteam.models import (
    DevActivityKind,
    DevArtifact,
    DevCommand,
    DevCommandStatus,
    DevCommandTarget,
    DevMeetingStatus,
    DevSessionStatus,
    ProjectStatus,
    ProjectType,
    SprintStage,
)
from clawteam.devteam.projects import ProjectManager
from clawteam.devteam.sessions import WorkerSessionStore
from clawteam.devteam.workflow import SprintWorkflow
from clawteam.spawn.subprocess_backend import SubprocessBackend
from clawteam.spawn.tmux_backend import TmuxBackend
from clawteam.team.mailbox import MailboxManager
from clawteam.team.tasks import TaskStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DevTeamControlService:
    """Mutates devteam state on behalf of the custom UI."""

    def __init__(self, team_name: str, workspace_dir: str | None = None):
        self.team_name = team_name
        self.workspace_dir = workspace_dir or os.environ.get("CLAWTEAM_WORKSPACE_DIR", "") or os.getcwd()
        self.runtime = load_runtime_blueprint(team_name)
        self.workflow = SprintWorkflow(self.runtime.blueprint.workflow_stages or None)
        self.projects = ProjectManager(
            team_name,
            workspace_dir=workspace_dir,
            workflow=self.workflow,
        )
        self.control = ControlPlaneStore(team_name)
        self.events = DevEventStore(team_name)
        self.meetings = MeetingManager(team_name)
        self.mailbox = MailboxManager(team_name)
        self.tasks = TaskStore(team_name)
        self.sessions = WorkerSessionStore(team_name)
        self._spawn_backend = TmuxBackend() if shutil.which("tmux") else SubprocessBackend()
        self.autonomy = DevConversationEngine(
            self.runtime.blueprint.personas,
            workflow=self.workflow,
            now_fn=lambda: datetime.now().astimezone(),
        )

    def submit_request(
        self,
        *,
        title: str,
        description: str,
        project_type: str = "feature",
        requested_by: str = "CEO",
    ):
        command = self._record_command(
            command_type="project.submit_request",
            requested_by=requested_by,
            payload={"title": title, "description": description, "projectType": project_type},
        )
        normalized_type = ProjectType(project_type)
        project = self.projects.open_project(
            title=title,
            project_type=normalized_type,
            description=description,
            assigned_agents=self._intake_agents(),
            metadata={"source": "web-ui", "channel_name": "dev-intake"},
        )
        project = self.autonomy.note_human_message(
            project,
            description or title,
            message_ts=_now_iso(),
        )
        self.projects.save_project(project)

        self.control.record_activity(
            kind=DevActivityKind.ceo_request,
            title=title,
            body=description,
            author=requested_by,
            project_id=project.project_id,
            stage=project.stage.value,
            participants=self._intake_agents(),
            metadata={"source": "web-ui", "project_type": normalized_type.value},
        )
        self.tasks.create(
            subject=f"[{project.project_id}] {title}",
            description=description,
            owner=self.workflow.stage_owner(project.stage),
            metadata={"project_id": project.project_id, "source": "web-ui"},
        )
        self.mailbox.send(
            from_agent=requested_by.lower().replace(" ", "-") or "ceo",
            to=self.workflow.stage_owner(project.stage),
            content=f"Project {project.project_id}: {description or title}",
            request_id=f"web-{project.project_id}",
        )
        self._mark_command_applied(
            command,
            event_type="project.created",
            actor=requested_by,
            project_id=project.project_id,
            payload=project.model_dump(mode="json"),
        )
        return project

    def approve_stage(
        self,
        *,
        project_id: str,
        approved_by: str = "CEO",
    ):
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        command = self._record_command(
            command_type="project.approve_stage",
            requested_by=approved_by,
            target=DevCommandTarget(project_id=project_id),
            payload={"stage": project.stage.value},
        )
        old_stage = project.stage
        project = self.projects.advance_stage(project, human_approved=True)
        state = dict(project.metadata.get("autonomy", {}))
        state["human_approved"] = False
        state["posted_agents"] = []
        project.metadata["autonomy"] = state
        self.projects.save_project(project)
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"Stage approval: {old_stage.value} -> {project.stage.value}",
            body=f"{approved_by} approved stage transition.",
            author=approved_by,
            project_id=project.project_id,
            stage=project.stage.value,
            metadata={"from_stage": old_stage.value, "to_stage": project.stage.value},
        )
        self._mark_command_applied(
            command,
            event_type="project.stage_changed",
            actor=approved_by,
            project_id=project.project_id,
            payload={"fromStage": old_stage.value, "toStage": project.stage.value},
        )
        return project

    def delete_project(
        self,
        *,
        project_id: str,
        requested_by: str = "CEO",
    ):
        """Permanently delete a project and record the action."""
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        command = self._record_command(
            command_type="project.delete",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id),
            payload={"title": project.title},
        )
        title = project.title
        self.projects.delete_project(project_id)
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"Project deleted: {title}",
            body=f"{requested_by} deleted project {project_id}.",
            author=requested_by,
            project_id=project_id,
        )
        self._mark_command_applied(
            command,
            event_type="project.deleted",
            actor=requested_by,
            project_id=project_id,
            payload={"project_id": project_id, "title": title},
        )
        return {"project_id": project_id, "title": title, "deleted": True}

    def add_note(
        self,
        *,
        title: str,
        body: str,
        author: str = "CEO",
        project_id: str = "",
        participants: list[str] | None = None,
        kind: str = "note",
    ):
        command = self._record_command(
            command_type=f"activity.{kind}",
            requested_by=author,
            target=DevCommandTarget(project_id=project_id),
            payload={"title": title, "body": body, "participants": participants or []},
        )
        activity = self.control.record_activity(
            kind=DevActivityKind(kind),
            title=title,
            body=body,
            author=author,
            project_id=project_id,
            participants=participants or [],
        )
        if project_id:
            project = self.projects.get_project(project_id)
            if project is not None:
                project = self.autonomy.note_human_message(
                    project,
                    body or title,
                    message_ts=activity.created_at,
                )
                project.metadata["last_operator_instruction"] = body or title
                self.projects.save_project(project)
        self._mark_command_applied(
            command,
            event_type=f"activity.{kind}",
            actor=author,
            project_id=project_id,
            payload=activity.model_dump(mode="json"),
            emit_event=False,
        )
        return activity

    def add_job(
        self,
        *,
        title: str,
        cadence: str,
        owner: str,
        instruction: str,
        channels: list[str] | None = None,
        created_by: str = "CEO",
    ):
        command = self._record_command(
            command_type="job.register",
            requested_by=created_by,
            target=DevCommandTarget(agent_name=owner),
            payload={"title": title, "cadence": cadence, "channels": channels or ["dev-ops"]},
        )
        job = self.control.create_job(
            title=title,
            cadence=cadence,
            owner=owner,
            instruction=instruction,
            channels=channels or ["dev-ops"],
            created_by=created_by,
        )
        self.control.record_activity(
            kind=DevActivityKind.schedule,
            title=f"Recurring job registered: {job.title}",
            body=job.instruction,
            author=created_by,
            participants=[job.owner],
            metadata={"job_key": job.key, "cadence": job.cadence},
        )
        self._mark_command_applied(
            command,
            event_type="job.registered",
            actor=created_by,
            payload=job.model_dump(mode="json"),
        )
        return job

    def pause_project(self, *, project_id: str, requested_by: str = "CEO"):
        project = self._require_project(project_id)
        command = self._record_command(
            command_type="project.pause",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id),
        )
        project.status = ProjectStatus.paused
        self._bump_project_version(project)
        self.projects.save_project(project)
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"Project paused: {project.title}",
            body=f"{requested_by} paused the project.",
            author=requested_by,
            project_id=project.project_id,
            stage=project.stage.value,
        )
        self._mark_command_applied(command, event_type="project.paused", actor=requested_by, project_id=project.project_id, payload=project.model_dump(mode="json"))
        return project

    def resume_project(self, *, project_id: str, requested_by: str = "CEO"):
        project = self._require_project(project_id)
        command = self._record_command(
            command_type="project.resume",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id),
        )
        project.status = ProjectStatus.open
        self._bump_project_version(project)
        self.projects.save_project(project)
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"Project resumed: {project.title}",
            body=f"{requested_by} resumed the project.",
            author=requested_by,
            project_id=project.project_id,
            stage=project.stage.value,
        )
        self._mark_command_applied(command, event_type="project.resumed", actor=requested_by, project_id=project.project_id, payload=project.model_dump(mode="json"))
        return project

    def reroute_project(
        self,
        *,
        project_id: str,
        stage: str,
        requested_by: str = "CEO",
    ):
        project = self._require_project(project_id)
        new_stage = SprintStage(stage)
        command = self._record_command(
            command_type="project.reroute_stage",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id),
            payload={"toStage": new_stage.value},
        )
        old_stage = project.stage
        project.stage = new_stage
        state = dict(project.metadata.get("autonomy", {}))
        state["posted_agents"] = []
        state["human_approved"] = False
        project.metadata["autonomy"] = state
        self._bump_project_version(project)
        self.projects.save_project(project)
        self.control.record_activity(
            kind=DevActivityKind.stage_transition,
            title=f"Manual reroute: {old_stage.value} -> {new_stage.value}",
            body=f"{requested_by} rerouted the project.",
            author=requested_by,
            project_id=project.project_id,
            stage=new_stage.value,
            metadata={"from_stage": old_stage.value, "to_stage": new_stage.value, "manual": True},
        )
        self._mark_command_applied(command, event_type="project.rerouted", actor=requested_by, project_id=project.project_id, payload={"fromStage": old_stage.value, "toStage": new_stage.value})
        return project

    def reassign_project(
        self,
        *,
        project_id: str,
        owner: str,
        requested_by: str = "CEO",
    ):
        project = self._require_project(project_id)
        command = self._record_command(
            command_type="project.reassign_owner",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id, agent_name=owner),
            payload={"owner": owner},
        )
        assigned = list(dict.fromkeys([owner, *project.assigned_agents]))
        project.assigned_agents = assigned
        project.metadata["manual_owner"] = owner
        self._bump_project_version(project)
        self.projects.save_project(project)
        self.tasks.create(
            subject=f"[{project.project_id}] Manual reassignment",
            description=f"{requested_by} assigned {owner} as operator-selected owner",
            owner=owner,
            metadata={"project_id": project.project_id, "source": "operator"},
        )
        self._mark_command_applied(command, event_type="project.reassigned", actor=requested_by, project_id=project.project_id, payload={"owner": owner})
        return project

    def inject_instruction(
        self,
        *,
        project_id: str,
        instruction: str,
        requested_by: str = "CEO",
    ):
        project = self._require_project(project_id)
        command = self._record_command(
            command_type="agent.inject_instruction",
            requested_by=requested_by,
            target=DevCommandTarget(project_id=project_id),
            payload={"instruction": instruction},
        )
        activity = self.add_note(
            title=f"Operator instruction: {project.title}",
            body=instruction,
            author=requested_by,
            project_id=project_id,
            participants=project.assigned_agents,
            kind="human_message",
        )
        self._mark_command_applied(command, event_type="operator.instruction_injected", actor=requested_by, project_id=project_id, payload=activity.model_dump(mode="json"))
        return activity

    def run_job_now(self, *, job_key: str, requested_by: str = "CEO"):
        job = self.control.get_job(job_key)
        if job is None:
            raise FileNotFoundError(f"Job '{job_key}' not found")
        command = self._record_command(
            command_type="job.run_now",
            requested_by=requested_by,
            target=DevCommandTarget(agent_name=job.owner),
            payload={"jobKey": job.key},
        )
        self.mailbox.send(
            from_agent=requested_by.lower().replace(" ", "-") or "ceo",
            to=job.owner,
            content=job.instruction,
            request_id=f"run-now-{job.key}",
        )
        self.control.mark_job_run(job.key, _now_iso())
        self.control.record_activity(
            kind=DevActivityKind.schedule,
            title=f"Run now: {job.title}",
            body=job.instruction,
            author=requested_by,
            participants=[job.owner],
            metadata={"job_key": job.key, "manual": True},
        )
        self._mark_command_applied(command, event_type="job.run_requested", actor=requested_by, payload=job.model_dump(mode="json"))
        return job

    def start_meeting(
        self,
        *,
        title: str,
        agenda: str,
        participants: list[str],
        project_id: str = "",
        created_by: str = "CEO",
    ):
        command = self._record_command(
            command_type="meeting.start",
            requested_by=created_by,
            target=DevCommandTarget(project_id=project_id),
            payload={"title": title, "agenda": agenda, "participants": participants},
        )
        meeting = self.meetings.start_meeting(
            title=title,
            agenda=agenda,
            participants=participants,
            project_id=project_id,
            created_by=created_by,
        )
        self.control.record_activity(
            kind=DevActivityKind.meeting,
            title=title,
            body=agenda,
            author=created_by,
            project_id=project_id,
            participants=participants,
            metadata={"meeting_id": meeting.meeting_id, "status": meeting.status.value},
        )
        self._mark_command_applied(command, event_type="meeting.started", actor=created_by, project_id=project_id, meeting_id=meeting.meeting_id, payload=meeting.model_dump(mode="json"), emit_event=False)
        return meeting

    def post_meeting_message(
        self,
        *,
        meeting_id: str,
        body: str,
        author: str = "CEO",
    ):
        meeting = self.meetings.events.get_meeting(meeting_id)
        if meeting is None:
            raise FileNotFoundError(f"Meeting '{meeting_id}' not found")
        command = self._record_command(
            command_type="meeting.inject_message",
            requested_by=author,
            target=DevCommandTarget(project_id=meeting.project_id, meeting_id=meeting_id),
            payload={"body": body},
        )
        message = self.meetings.add_message(
            meeting_id=meeting_id,
            speaker=author,
            speaker_type="human",
            body=body,
        )
        self.control.record_activity(
            kind=DevActivityKind.meeting,
            title=meeting.title,
            body=body,
            author=author,
            project_id=meeting.project_id,
            participants=meeting.participants,
            metadata={"meeting_id": meeting_id, "message_id": message.message_id},
        )
        self._mark_command_applied(command, event_type="meeting.message_posted", actor=author, project_id=meeting.project_id, meeting_id=meeting_id, payload=message.model_dump(mode="json"), emit_event=False)
        return message

    def conclude_meeting(self, *, meeting_id: str, concluded_by: str = "CEO"):
        meeting = self.meetings.events.get_meeting(meeting_id)
        if meeting is None:
            raise FileNotFoundError(f"Meeting '{meeting_id}' not found")
        command = self._record_command(
            command_type="meeting.end",
            requested_by=concluded_by,
            target=DevCommandTarget(project_id=meeting.project_id, meeting_id=meeting_id),
        )
        meeting = self.meetings.conclude_meeting(meeting_id, concluded_by=concluded_by)
        transcript = "\n".join(
            f"{msg.speaker}: {msg.body}"
            for msg in self.meetings.list_messages(meeting_id)
        )
        self.events.add_artifact(
            DevArtifact(
                team_name=self.team_name,
                project_id=meeting.project_id,
                meeting_id=meeting_id,
                kind="meeting_transcript",
                title=f"Transcript: {meeting.title}",
                metadata={"transcript": transcript},
            )
        )
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"Meeting concluded: {meeting.title}",
            body="Action items captured in meeting transcript.",
            author=concluded_by,
            project_id=meeting.project_id,
            participants=meeting.participants,
            metadata={"meeting_id": meeting_id, "status": DevMeetingStatus.concluded.value, "transcript": transcript[:2000]},
        )
        self._mark_command_applied(command, event_type="meeting.concluded", actor=concluded_by, project_id=meeting.project_id, meeting_id=meeting_id, payload=meeting.model_dump(mode="json"), emit_event=False)
        return meeting

    def invoke_specialist(
        self,
        agent_type: str,
        task: str,
        project_id: str = "",
    ) -> dict:
        """Invoke a specialist agent (code-reviewer or qa-engineer) with a task.

        Creates a session, spawns the agent, and returns session info.
        """
        # Find the persona for this agent type
        persona = next(
            (p for p in self.runtime.blueprint.personas if p.agent == agent_type),
            None,
        )
        if persona is None:
            raise ValueError(f"Unknown specialist agent type: {agent_type}")

        command = self._record_command(
            command_type="specialist.invoke",
            requested_by="CEO",
            target=DevCommandTarget(agent_name=agent_type, project_id=project_id),
            payload={"task": task, "agent_type": agent_type},
        )

        # Build prompt with persona context
        prompt = (
            f"## Your Role\n\n"
            f"- Name: {persona.display_name}\n"
            f"- Title: {persona.role}\n"
            f"- Style: {persona.style}\n"
            f"- Responsibilities: {', '.join(persona.responsibilities)}\n\n"
        )
        if project_id:
            project = self.projects.get_project(project_id)
            if project:
                prompt += (
                    f"## Project Context\n\n"
                    f"- Title: {project.title}\n"
                    f"- Stage: {project.stage.value}\n"
                    f"- Description: {project.description or '(none)'}\n\n"
                )
        prompt += f"## Task\n\n{task}\n\n"
        prompt += (
            f"When done, report via "
            f"`clawteam inbox send {self.team_name} chief-of-staff 'Task complete: {agent_type}'`."
        )

        agent_name = f"{agent_type}-specialist-{command.command_id}"
        session = self.sessions.start_session(
            agent_name=agent_name,
            agent_id=agent_name,
            agent_type=agent_type,
            project_id=project_id,
            stage="specialist",
            workspace_path=self.workspace_dir,
            details={"prompt": prompt[:1200], "task": task},
        )
        try:
            result = self._spawn_backend.spawn(
                command=["claude"],
                agent_name=agent_name,
                agent_id=agent_name,
                agent_type=agent_type,
                team_name=self.team_name,
                prompt=prompt,
                cwd=self.workspace_dir,
                env={},
            )
            session.status = DevSessionStatus.running
            session.details["spawn_result"] = result
            self.sessions.update_session(session)
        except Exception as exc:
            session.status = DevSessionStatus.failed
            session.ended_at = _now_iso()
            session.details["error"] = str(exc)
            self.sessions.update_session(session)
            raise

        self.control.record_activity(
            kind=DevActivityKind.worklog,
            title=f"Specialist invoked: {persona.display_name}",
            body=task,
            author="CEO",
            project_id=project_id,
            metadata={
                "agent_type": agent_type,
                "agent_name": agent_name,
                "session_id": session.session_id,
            },
        )
        self._mark_command_applied(
            command,
            event_type="specialist.invoked",
            actor="CEO",
            project_id=project_id,
            payload={
                "agent_type": agent_type,
                "session_id": session.session_id,
                "agent_name": agent_name,
            },
        )
        return {
            "agent_type": agent_type,
            "agent_name": agent_name,
            "session_id": session.session_id,
            "display_name": persona.display_name,
            "task": task,
        }

    def list_commands(self, *, limit: int = 100, project_id: str = ""):
        return self.events.list_commands(limit=limit, project_id=project_id)

    def _record_command(
        self,
        *,
        command_type: str,
        requested_by: str,
        target: DevCommandTarget | None = None,
        payload: dict | None = None,
        idempotency_key: str = "",
    ) -> DevCommand:
        command = DevCommand(
            command_type=command_type,
            requested_by=requested_by,
            target=target or DevCommandTarget(),
            payload=payload or {},
            idempotency_key=idempotency_key,
        )
        return self.events.create_command(command)

    def _mark_command_applied(
        self,
        command: DevCommand,
        *,
        event_type: str,
        actor: str,
        project_id: str = "",
        meeting_id: str = "",
        payload: dict | None = None,
        emit_event: bool = True,
    ) -> None:
        event_id = ""
        if emit_event:
            event_id = self.events.append_event(
                event_type=event_type,
                actor=actor,
                project_id=project_id,
                meeting_id=meeting_id,
                command_id=command.command_id,
                occurred_at=_now_iso(),
                payload=payload or {},
            )
        self.events.update_command(
            command.command_id,
            status=DevCommandStatus.applied,
            handled_at=_now_iso(),
            result_event_id=event_id,
        )

    def _require_project(self, project_id: str):
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        return project

    def _bump_project_version(self, project) -> None:
        version = int(project.metadata.get("version", 0))
        project.metadata["version"] = version + 1

    def _intake_agents(self) -> list[str]:
        intake = next(
            (channel for channel in self.runtime.blueprint.channels if channel.name == "dev-intake"),
            None,
        )
        if intake and intake.subscribers:
            return list(intake.subscribers)
        return ["chief-of-staff"]
