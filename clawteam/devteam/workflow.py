"""Sprint workflow state machine for dev team projects."""

from __future__ import annotations

import functools

from clawteam.devteam.models import DevProject, SprintStage, StageConfig


# ---------------------------------------------------------------------------
# Default stage configuration
# ---------------------------------------------------------------------------

DEFAULT_STAGE_CONFIGS: list[StageConfig] = [
    StageConfig(
        stage=SprintStage.intake,
        primary_owner="chief-of-staff",
        spawn_agent=True,
        auto_advance=True,
    ),
    StageConfig(
        stage=SprintStage.think,
        primary_owner="cto",
        supporting_agents=["lead-engineer"],
        spawn_agent=True,
        requires_human_approval=False,
        auto_advance=True,
    ),
    StageConfig(
        stage=SprintStage.plan,
        primary_owner="cto",
        supporting_agents=["designer"],
        spawn_agent=True,
        requires_human_approval=True,
        auto_advance=False,
    ),
    StageConfig(
        stage=SprintStage.build,
        primary_owner="lead-engineer",
        spawn_agent=True,
        auto_advance=True,
    ),
    StageConfig(
        stage=SprintStage.review,
        primary_owner="cto",
        supporting_agents=["security-officer", "lead-engineer"],
        spawn_agent=True,
        requires_human_approval=True,
        auto_advance=False,
    ),
    StageConfig(
        stage=SprintStage.test,
        primary_owner="qa-lead",
        supporting_agents=["lead-engineer"],
        spawn_agent=True,
        auto_advance=True,
    ),
    StageConfig(
        stage=SprintStage.security,
        primary_owner="security-officer",
        supporting_agents=["cto"],
        requires_human_approval=True,
        spawn_agent=True,
        auto_advance=False,
    ),
    StageConfig(
        stage=SprintStage.ship,
        primary_owner="devops",
        supporting_agents=["tech-writer"],
        auto_advance=True,
    ),
    StageConfig(
        stage=SprintStage.reflect,
        primary_owner="chief-of-staff",
        auto_advance=True,
    ),
]

# ---------------------------------------------------------------------------
# Per-ProjectType pipeline configurations
# ---------------------------------------------------------------------------

PIPELINE_CONFIGS: dict[str, list[StageConfig]] = {
    "feature": DEFAULT_STAGE_CONFIGS,   # full 9-stage
    "bugfix": DEFAULT_STAGE_CONFIGS,    # full 9-stage
    "refactor": DEFAULT_STAGE_CONFIGS,  # full 9-stage
    "spike": [
        StageConfig(stage=SprintStage.intake, primary_owner="chief-of-staff", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.think, primary_owner="cto", supporting_agents=["lead-engineer"], spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.reflect, primary_owner="chief-of-staff", auto_advance=True),
    ],
    "code_review": [
        StageConfig(stage=SprintStage.intake, primary_owner="chief-of-staff", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.review, primary_owner="cto", supporting_agents=["security-officer", "lead-engineer"], spawn_agent=True, requires_human_approval=False, auto_advance=True),
        StageConfig(stage=SprintStage.reflect, primary_owner="chief-of-staff", auto_advance=True),
    ],
    "log_analysis": [
        StageConfig(stage=SprintStage.intake, primary_owner="chief-of-staff", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.think, primary_owner="cto", supporting_agents=["lead-engineer"], spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.reflect, primary_owner="chief-of-staff", auto_advance=True),
    ],
    "e2e_test": [
        StageConfig(stage=SprintStage.intake, primary_owner="chief-of-staff", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.build, primary_owner="lead-engineer", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.test, primary_owner="qa-lead", supporting_agents=["lead-engineer"], spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.reflect, primary_owner="chief-of-staff", auto_advance=True),
    ],
    "quick_task": [
        StageConfig(stage=SprintStage.intake, primary_owner="chief-of-staff", spawn_agent=True, auto_advance=True),
        StageConfig(stage=SprintStage.reflect, primary_owner="chief-of-staff", auto_advance=True),
    ],
}


class SprintWorkflow:
    """Sprint lifecycle state machine with per-project-type pipeline support."""

    def __init__(self, stage_configs: list[StageConfig] | None = None):
        configs = stage_configs or DEFAULT_STAGE_CONFIGS
        self._configs: dict[SprintStage, StageConfig] = {cfg.stage: cfg for cfg in configs}
        self._stage_order: list[str] = [cfg.stage.value for cfg in configs]

    @classmethod
    def for_project_type(cls, project_type: str) -> "SprintWorkflow":
        """Return a (cached) workflow instance matching the given project type."""
        return _cached_workflow_for_type(project_type)

    def stage_config(self, stage: SprintStage) -> StageConfig:
        return self._configs.get(stage, StageConfig(stage=stage, primary_owner="chief-of-staff"))

    def stage_owner(self, stage: SprintStage) -> str:
        return self.stage_config(stage).primary_owner

    def stage_participants(self, stage: SprintStage) -> list[str]:
        cfg = self.stage_config(stage)
        participants = [cfg.primary_owner]
        participants.extend(cfg.supporting_agents)
        return participants

    def should_spawn(self, stage: SprintStage) -> bool:
        return self.stage_config(stage).spawn_agent

    def next_stage(self, stage: SprintStage) -> SprintStage | None:
        """Return the next stage in this workflow's pipeline."""
        try:
            idx = self._stage_order.index(stage.value)
        except ValueError:
            return None
        if idx + 1 >= len(self._stage_order):
            return None
        return SprintStage(self._stage_order[idx + 1])

    def is_terminal_stage(self, stage: SprintStage) -> bool:
        """Return True if *stage* is the last stage in this pipeline."""
        return self.next_stage(stage) is None

    def can_advance(self, project: DevProject, human_approved: bool = False) -> bool:
        cfg = self.stage_config(project.stage)
        if cfg.requires_human_approval and not human_approved:
            return False
        if self.next_stage(project.stage) is None:
            return False
        return True

    def advance(self, project: DevProject, human_approved: bool = False) -> DevProject:
        if not self.can_advance(project, human_approved=human_approved):
            return project
        next_s = self.next_stage(project.stage)
        if next_s is None:
            return project
        old_stage = project.stage
        project.stage = next_s
        # Track stage history in metadata
        history = list(project.metadata.get("stage_history", []))
        history.append({"from": old_stage.value, "to": next_s.value})
        project.metadata["stage_history"] = history[-20:]
        return project


@functools.lru_cache(maxsize=16)
def _cached_workflow_for_type(project_type: str) -> SprintWorkflow:
    """Module-level cached factory — avoids creating new instances every tick."""
    configs = PIPELINE_CONFIGS.get(project_type, DEFAULT_STAGE_CONFIGS)
    return SprintWorkflow(stage_configs=configs)
