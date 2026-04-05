"""Domain models for the dev team operating runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared types (self-contained, no dependency on clawteam.investment)
# ---------------------------------------------------------------------------


class ChannelKind(str, Enum):
    executive = "executive"
    desk = "desk"
    operations = "operations"
    archive = "archive"


class ChannelSpec(BaseModel):
    name: str
    purpose: str
    kind: ChannelKind = ChannelKind.desk
    private: bool = False
    default_thread_case_type: str = ""
    subscribers: list[str] = Field(default_factory=list)


# Backwards-compatible aliases
SlackChannelKind = ChannelKind
SlackChannelSpec = ChannelSpec


class PersonaSpec(BaseModel):
    agent: str
    display_name: str
    role: str
    style: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    decision_rights: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list, alias="slack_channels")

    model_config = {"populate_by_name": True}


class ScheduleSpec(BaseModel):
    key: str
    cadence: str
    owner: str
    description: str
    channels: list[str] = Field(default_factory=list)


class ProtocolSpec(BaseModel):
    title: str
    owner: str
    when: str
    steps: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SprintStage(str, Enum):
    intake = "intake"
    think = "think"
    plan = "plan"
    build = "build"
    review = "review"
    test = "test"
    security = "security"
    ship = "ship"
    reflect = "reflect"


class ProjectType(str, Enum):
    feature = "feature"
    bugfix = "bugfix"
    refactor = "refactor"
    spike = "spike"
    code_review = "code_review"
    log_analysis = "log_analysis"
    e2e_test = "e2e_test"
    quick_task = "quick_task"


class ProjectStatus(str, Enum):
    open = "open"
    paused = "paused"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Thread binding (mirrors CaseThreadRef)
# ---------------------------------------------------------------------------


class ProjectThreadRef(BaseModel):
    channel: str
    channel_name: str = ""
    thread_ts: str
    root_ts: str = ""
    last_message_ts: str = ""


# ---------------------------------------------------------------------------
# Stage configuration
# ---------------------------------------------------------------------------


class StageConfig(BaseModel):
    """Per-stage workflow configuration."""

    stage: SprintStage
    primary_owner: str
    supporting_agents: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    auto_advance: bool = True
    spawn_agent: bool = False  # True for build/test/security stages


# ---------------------------------------------------------------------------
# Dev project (analogous to InvestmentCase)
# ---------------------------------------------------------------------------


class DevProject(BaseModel):
    project_id: str
    project_type: ProjectType = ProjectType.feature
    title: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.open
    stage: SprintStage = SprintStage.intake
    thread: ProjectThreadRef | None = None
    assigned_agents: list[str] = Field(default_factory=list)
    repository: str = ""
    branch: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevActivityKind(str, Enum):
    ceo_request = "ceo_request"
    human_message = "human_message"
    agent_message = "agent_message"
    meeting = "meeting"
    note = "note"
    decision = "decision"
    worklog = "worklog"
    schedule = "schedule"
    stage_transition = "stage_transition"
    system = "system"
    error = "error"


class DevActivity(BaseModel):
    activity_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    kind: DevActivityKind = DevActivityKind.note
    title: str = ""
    body: str = ""
    author: str = ""
    project_id: str = ""
    stage: str = ""
    participants: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevRecurringJob(BaseModel):
    key: str
    title: str
    cadence: str
    owner: str
    instruction: str
    channels: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_by: str = ""
    created_at: str = Field(default_factory=_now_iso)
    last_run_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevCompanyStatus(str, Enum):
    stopped = "stopped"
    starting = "starting"
    online = "online"
    degraded = "degraded"
    stopping = "stopping"


class DevCompanyState(BaseModel):
    team_name: str
    status: DevCompanyStatus = DevCompanyStatus.stopped
    runtime_status: str = "offline"
    scheduler_status: str = "idle"
    ui_status: str = "offline"
    started_at: str = ""
    last_heartbeat_at: str = ""
    active_sessions: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevCommandStatus(str, Enum):
    pending = "pending"
    acknowledged = "acknowledged"
    applied = "applied"
    rejected = "rejected"
    failed = "failed"
    expired = "expired"


class DevCommandTarget(BaseModel):
    project_id: str = ""
    session_id: str = ""
    meeting_id: str = ""
    agent_name: str = ""


class DevCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    command_type: str
    status: DevCommandStatus = DevCommandStatus.pending
    requested_by: str = ""
    requested_at: str = Field(default_factory=_now_iso)
    handled_at: str = ""
    target: DevCommandTarget = Field(default_factory=DevCommandTarget)
    payload: dict[str, Any] = Field(default_factory=dict)
    result_event_id: str = ""
    idempotency_key: str = ""
    error: str = ""


class DevSessionStatus(str, Enum):
    starting = "starting"
    running = "running"
    blocked = "blocked"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class DevWorkerSession(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    team_name: str
    agent_name: str
    agent_id: str = ""
    agent_type: str = ""
    project_id: str = ""
    stage: str = ""
    status: DevSessionStatus = DevSessionStatus.starting
    workspace_path: str = ""
    branch: str = ""
    tmux_target: str = ""
    log_path: str = ""
    started_at: str = Field(default_factory=_now_iso)
    last_heartbeat_at: str = Field(default_factory=_now_iso)
    ended_at: str = ""
    exit_code: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class DevArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    team_name: str
    project_id: str = ""
    session_id: str = ""
    meeting_id: str = ""
    kind: str = "note"
    title: str = ""
    path: str = ""
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevMeetingStatus(str, Enum):
    scheduled = "scheduled"
    live = "live"
    paused = "paused"
    concluded = "concluded"


class DevMeeting(BaseModel):
    meeting_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    team_name: str
    project_id: str = ""
    title: str
    agenda: str = ""
    status: DevMeetingStatus = DevMeetingStatus.scheduled
    participants: list[str] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = Field(default_factory=_now_iso)
    started_at: str = ""
    ended_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevMeetingMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    meeting_id: str
    team_name: str
    project_id: str = ""
    speaker: str
    speaker_type: str = "agent"
    body: str
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Blueprint (analogous to InvestmentBlueprint)
# ---------------------------------------------------------------------------


class DeveloperPersona(BaseModel):
    """A persona template for dynamically spawned developers."""

    name: str
    style: str = ""
    specialty: str = ""


class DeveloperPoolSpec(BaseModel):
    """Configuration for the dynamic developer pool."""

    min_developers: int = 1
    max_developers: int = 5
    personas: list[DeveloperPersona] = Field(default_factory=list)


class DevTeamBlueprint(BaseModel):
    team_label: str = ""
    operating_model: str = "web-first"
    summary: str = ""
    channels: list[ChannelSpec] = Field(default_factory=list)
    personas: list[PersonaSpec] = Field(default_factory=list)
    workflow_stages: list[StageConfig] = Field(default_factory=list)
    schedules: list[ScheduleSpec] = Field(default_factory=list)
    protocols: dict[str, ProtocolSpec] = Field(default_factory=dict)
    developer_pool: DeveloperPoolSpec = Field(default_factory=DeveloperPoolSpec)


class DevTeamRuntimeBlueprint(BaseModel):
    template: str
    team_name: str
    goal: str
    created_at: str = Field(default_factory=_now_iso)
    leader: str
    members: list[str] = Field(default_factory=list)
    blueprint: DevTeamBlueprint


class DevTeamRuntimeState(BaseModel):
    team_name: str
    mode: str = "team_offline"
    active_project_threads: dict[str, str] = Field(default_factory=dict)
    last_protocol_runs: dict[str, str] = Field(default_factory=dict)
    last_heartbeat_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
