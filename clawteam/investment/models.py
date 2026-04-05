"""Structured models for a Slack-first investment operating system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SlackChannelKind(str, Enum):
    executive = "executive"
    desk = "desk"
    operations = "operations"
    client = "client"
    execution = "execution"
    archive = "archive"


class StrategyLifecycle(str, Enum):
    draft = "draft"
    sandbox = "sandbox"
    paper = "paper"
    restricted_live = "restricted_live"
    full_live = "full_live"
    degraded = "degraded"
    retired = "retired"


class ExecutionMode(str, Enum):
    observe_only = "observe_only"
    paper = "paper"
    preview = "preview"
    live = "live"


class SlackChannelSpec(BaseModel):
    name: str
    purpose: str
    kind: SlackChannelKind = SlackChannelKind.desk
    private: bool = False
    escalation: bool = False
    default_thread_case_type: str = ""
    subscribers: list[str] = Field(default_factory=list)


class PersonaSpec(BaseModel):
    agent: str
    display_name: str
    role: str
    style: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    decision_rights: list[str] = Field(default_factory=list)
    slack_channels: list[str] = Field(default_factory=list)


class DataSourceSpec(BaseModel):
    key: str
    category: str
    status: str = "planned"
    cadence: str = "on_demand"
    source: str = ""
    notes: str = ""
    triggers: list[str] = Field(default_factory=list)


class IndicatorSpec(BaseModel):
    key: str
    family: str
    timeframe: list[str] = Field(default_factory=list)
    purpose: str = ""


class StrategySpec(BaseModel):
    model_config = {"populate_by_name": True}

    strategy_id: str = Field(alias="id")
    name: str
    thesis: str
    lifecycle: StrategyLifecycle = StrategyLifecycle.draft
    owner: str
    universe: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    risk_constraints: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    notes: str = ""


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


class ExecutionAdapterSpec(BaseModel):
    broker: str
    mode: ExecutionMode = ExecutionMode.preview
    markets: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    notes: str = ""


class ExecutionPolicySpec(BaseModel):
    default_mode: ExecutionMode = ExecutionMode.paper
    require_human_approval: bool = True
    allow_ceo_bypass: bool = False
    allowed_tiers: list[str] = Field(default_factory=list)
    broker_adapters: list[ExecutionAdapterSpec] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)


class InvestmentBlueprint(BaseModel):
    firm_name: str = ""
    operating_model: str = "slack-first"
    ceo_mode: str = "hybrid"
    summary: str = ""
    channels: list[SlackChannelSpec] = Field(default_factory=list)
    personas: list[PersonaSpec] = Field(default_factory=list)
    data_sources: list[DataSourceSpec] = Field(default_factory=list)
    indicators: list[IndicatorSpec] = Field(default_factory=list)
    strategies: list[StrategySpec] = Field(default_factory=list)
    schedules: list[ScheduleSpec] = Field(default_factory=list)
    protocols: dict[str, ProtocolSpec] = Field(default_factory=dict)
    execution: ExecutionPolicySpec = Field(default_factory=ExecutionPolicySpec)
    ceo_intervention_rules: list[str] = Field(default_factory=list)
    autonomous_rules: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class InvestmentRuntimeBlueprint(BaseModel):
    template: str
    team_name: str
    goal: str
    created_at: str = Field(default_factory=_now_iso)
    leader: str
    members: list[str] = Field(default_factory=list)
    blueprint: InvestmentBlueprint


class InvestmentRuntimeState(BaseModel):
    team_name: str
    mode: str = "company_closed"
    active_case_threads: dict[str, str] = Field(default_factory=dict)
    watchlists: dict[str, list[str]] = Field(default_factory=dict)
    strategy_states: dict[str, StrategyLifecycle] = Field(default_factory=dict)
    last_protocol_runs: dict[str, str] = Field(default_factory=dict)
    last_heartbeat_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
