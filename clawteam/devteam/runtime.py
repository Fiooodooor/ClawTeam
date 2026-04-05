"""Web-first dev team operating runtime."""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import suppress
from datetime import datetime
from typing import Any

import fcntl
from zoneinfo import ZoneInfo

from clawteam.devteam.autonomy import DevConversationEngine
from clawteam.devteam.bootstrap import (
    devteam_dir,
    load_runtime_blueprint,
    load_runtime_state,
    save_runtime_state,
)
from clawteam.devteam.controlplane import ControlPlaneStore
from clawteam.devteam.eventstore import DevEventStore
from clawteam.devteam.integrations import (
    discover_opencode_profile,
    load_opencode_env,
)
from clawteam.devteam.meetings import MeetingManager
from clawteam.devteam.models import (
    DevActivityKind,
    DevCompanyStatus,
    DevProject,
    DevSessionStatus,
    ProjectStatus,
    ProjectType,
    ScheduleSpec,
    SprintStage,
)
from clawteam.devteam.projects import ProjectManager
from clawteam.devteam.sessions import WorkerSessionStore
from clawteam.devteam.workflow import SprintWorkflow
from clawteam.devteam.scheduler import DueSchedule, SchedulerStore
from clawteam.spawn.subprocess_backend import SubprocessBackend
from clawteam.spawn.tmux_backend import TmuxBackend
from clawteam.team.mailbox import MailboxManager
from clawteam.team.tasks import TaskStore
from clawteam.workspace import get_workspace_manager


class DevTeamRuntimeError(RuntimeError):
    """Raised when the dev team runtime cannot proceed."""


class DevTeamOperatingRuntime:
    """Coordinates startup, sprint workflow, and agent spawning."""

    def __init__(
        self,
        team_name: str,
        mailbox: MailboxManager | None = None,
        task_store: TaskStore | None = None,
        project_manager: ProjectManager | None = None,
        scheduler: SchedulerStore | None = None,
        spawn_backend: Any = None,
        sleep_fn: Any = time.sleep,
        now_fn: Any = None,
        workspace_dir: str | None = None,
    ):
        self.team_name = team_name
        self.runtime = load_runtime_blueprint(team_name)
        self.state = load_runtime_state(team_name)
        self.workspace_dir = (
            workspace_dir
            or os.environ.get("CLAWTEAM_WORKSPACE_DIR", "")
            or os.getcwd()
        )

        self.mailbox = mailbox or MailboxManager(team_name)
        self.task_store = task_store or TaskStore(team_name)

        self.workflow = SprintWorkflow(self.runtime.blueprint.workflow_stages or None)
        self.project_manager = project_manager or ProjectManager(
            team_name,
            workspace_dir=self.workspace_dir,
            workflow=self.workflow,
        )
        self.scheduler = scheduler or SchedulerStore(team_name)
        self.control = ControlPlaneStore(team_name)
        self.events = DevEventStore(team_name)
        self.sessions = WorkerSessionStore(team_name)
        self.meetings = MeetingManager(team_name)
        self.sleep_fn = sleep_fn
        self.now_fn = now_fn or self._build_now_fn()
        self.autonomy = DevConversationEngine(
            self.runtime.blueprint.personas,
            workflow=self.workflow,
            now_fn=self.now_fn,
        )
        self._started = False
        self._runtime_lock: Any = None
        self._spawn_backend = spawn_backend or self._default_spawn_backend()
        self.workspace_manager = get_workspace_manager(self.workspace_dir)
        self.integrations: dict[str, bool] = {}
        self._load_integrations()
        self.opencode_profile = discover_opencode_profile(self.workspace_dir)
        self.log_path = devteam_dir(team_name) / "runtime.log"
        self.logger = self._build_logger()

    @staticmethod
    def _default_spawn_backend():
        """Use tmux if available, otherwise fall back to subprocess."""
        import shutil

        if shutil.which("tmux"):
            return TmuxBackend()
        return SubprocessBackend()

    # Sentinel: keys mapped to this value should be REMOVED from the
    # spawn environment rather than set to empty string.  Claude Code CLI
    # may treat an empty-string env var differently from an absent one.
    _ENV_UNSET = "__CLAWTEAM_UNSET__"

    # Plugin-related env vars to propagate from parent to spawned agents
    _PLUGIN_ENV_KEYS = [
        "OMLC_SKILLS_PATH",
        "CLAUDE_CODE_PROMPT_CACHING",
    ]

    @staticmethod
    def _build_claude_spawn_env(*, force_bedrock: bool = False) -> dict[str, str]:
        """Build environment variables for spawned Claude Code agents.

        **Primary**: Team Plan -- no special env vars needed.  The spawned
        ``claude`` process inherits the Team Plan subscription from the
        user's CLI config (``"lbox"`` org with API Usage Billing).  We
        mark Bedrock vars for *deletion* (not empty string) so the process
        does NOT try to use Bedrock when the Team Plan is active.

        **Fallback**: AWS Bedrock -- activated when
        ``CLAWTEAM_USE_BEDROCK=1`` is set, or dynamically via
        *force_bedrock* when Team Plan quota is exhausted.
        """
        env: dict[str, str] = {}

        use_bedrock = force_bedrock or os.environ.get("CLAWTEAM_USE_BEDROCK", "") == "1"

        if use_bedrock:
            env["CLAUDE_CODE_USE_BEDROCK"] = "1"
            env["AWS_PROFILE"] = os.environ.get("AWS_PROFILE", "bedrock")
            env["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

            env["ANTHROPIC_MODEL"] = os.environ.get(
                "ANTHROPIC_MODEL",
                "arn:aws:bedrock:us-east-1:048245882214:application-inference-profile/pvmv1nj8qnl7",
            )
            env["ANTHROPIC_SMALL_FAST_MODEL"] = os.environ.get(
                "ANTHROPIC_SMALL_FAST_MODEL",
                "arn:aws:bedrock:us-east-1:048245882214:application-inference-profile/bz9jbye2jcz3",
            )
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = os.environ.get(
                "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "16384",
            )
            env["MAX_THINKING_TOKENS"] = os.environ.get(
                "MAX_THINKING_TOKENS", "10240",
            )
        else:
            # Team Plan -- mark Bedrock vars for DELETION (not empty string)
            env["CLAUDE_CODE_USE_BEDROCK"] = DevTeamOperatingRuntime._ENV_UNSET
            env["ANTHROPIC_MODEL"] = DevTeamOperatingRuntime._ENV_UNSET
            env["ANTHROPIC_SMALL_FAST_MODEL"] = DevTeamOperatingRuntime._ENV_UNSET

        # Propagate plugin env vars from parent process
        for key in DevTeamOperatingRuntime._PLUGIN_ENV_KEYS:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # Enable P2P transport for inter-agent real-time communication
        env.setdefault("CLAWTEAM_TRANSPORT", os.environ.get("CLAWTEAM_TRANSPORT", "p2p"))

        return env

    @staticmethod
    def _should_fallback_to_bedrock(spawn_result: str) -> bool:
        """Detect Team Plan quota exhaustion from spawn error messages."""
        indicators = [
            "credit balance too low",
            "rate limit",
            "quota exceeded",
            "usage limit",
            "billing",
        ]
        lower = spawn_result.lower()
        return any(ind in lower for ind in indicators)

    def _load_integrations(self) -> None:
        """Load env files and detect which integrations are available.

        Called from ``__init__`` so environment variables are populated
        **before** any agents are spawned.  The integration status is
        stored in ``self.integrations`` for quick lookup.
        """
        # 1. Load all discovered env files into os.environ
        self.env_load_report = load_opencode_env(self.workspace_dir)

        # 2. Check which integrations are configured
        # GitHub detection via gh CLI
        try:
            from clawteam.devteam.github import is_gh_available
            gh_ok = is_gh_available()
        except Exception:
            gh_ok = False

        integration_checks: dict[str, bool] = {
            "github": gh_ok,
            "jira": self._check_jira_available(),
            "datadog": self._check_datadog_available(),
            "langfuse": bool(
                os.environ.get("LANGFUSE_BASE_URL")
                and (
                    (
                        os.environ.get("LANGFUSE_DEV_PUBLIC_KEY")
                        and os.environ.get("LANGFUSE_DEV_SECRET_KEY")
                    )
                    or (
                        os.environ.get("LANGFUSE_PRD_PUBLIC_KEY")
                        and os.environ.get("LANGFUSE_PRD_SECRET_KEY")
                    )
                )
            ),
            "slack_bot": bool(os.environ.get("SLACK_BOT_TOKEN")),
            "slack_mcp": bool(
                os.environ.get("SLACK_MCP_CLIENT_ID")
                and os.environ.get("SLACK_MCP_CLIENT_SECRET")
            ),
            "obsidian": bool(
                os.environ.get("OBSIDIAN_VAULT_PATH")
                or os.environ.get("OBSIDIAN_BASE_PATH")
            ),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
        }

        self.integrations = integration_checks

    @staticmethod
    def _check_jira_available() -> bool:
        try:
            from clawteam.devteam.jira import is_jira_available
            return is_jira_available()
        except Exception:
            return bool(os.environ.get("JIRA_API_TOKEN"))

    @staticmethod
    def _check_datadog_available() -> bool:
        try:
            from clawteam.devteam.datadog import is_datadog_available
            return is_datadog_available()
        except Exception:
            return bool(
                os.environ.get("DD_API_KEY") and os.environ.get("DD_APP_KEY")
            )

    # -- Lifecycle ----------------------------------------------------------

    def startup(self) -> dict[str, Any]:
        self.logger.info("startup begin")
        self._acquire_runtime_lock()
        self._refresh_projects_for_startup()

        self.state = load_runtime_state(self.team_name)
        self.state.mode = "ui_only_online"
        self._touch_heartbeat()
        self.state.metadata["opencode"] = {
            **self.opencode_profile,
            **self.env_load_report,
        }
        company = self.events.get_company_state()
        company.started_at = company.started_at or self.now_fn().isoformat()
        company.status = DevCompanyStatus.online
        company.runtime_status = self.state.mode
        company.scheduler_status = "online"
        company.ui_status = "online"
        company.last_heartbeat_at = self.state.last_heartbeat_at
        self.events.save_company_state(company)

        self.control.record_activity(
            kind=DevActivityKind.system,
            title="Runtime online",
            body=f"Mode: {self.state.mode}",
            author="runtime",
            metadata={"team": self.team_name},
        )

        open_projects = self.project_manager.list_projects()
        self._advance_project_conversations(open_projects, trigger="startup")
        self.state = load_runtime_state(self.team_name)
        self.state.mode = "ui_only_online"
        self._touch_heartbeat()
        # Re-apply opencode metadata (reloading state from disk clears it)
        self.state.metadata["opencode"] = {
            **self.opencode_profile,
            **self.env_load_report,
        }
        self._started = True
        save_runtime_state(self.state)

        result = {
            "team": self.team_name,
            "mode": self.state.mode,
        }
        self.logger.info("startup complete mode=%s", result["mode"])
        return result

    def run_once(self) -> dict[str, Any]:
        if not self._started:
            startup = self.startup()
        else:
            startup = {"team": self.team_name, "mode": self.state.mode}

        due_protocols = self._safe_run_due_schedules()
        self._ensure_stage_spawns()
        live_meeting_messages = self._tick_live_meetings()

        # Advance all open projects on loop trigger
        open_projects = self.project_manager.list_projects()
        self._advance_project_conversations(open_projects, trigger="loop")

        # Auto-advance stages where conversation is done
        self._auto_advance_stages(open_projects)

        # Check spawned agent results
        self._check_all_agent_results()
        self.sessions.refresh_sessions()

        # Auto-recover dead agents: re-spawn if process died without reporting done
        self._recover_dead_agents(open_projects)

        self._touch_heartbeat()
        self.task_store.release_stale_locks()
        save_runtime_state(self.state)

        return {
            "startup": startup,
            "due_protocols": due_protocols,
            "live_meeting_messages": len(live_meeting_messages),
            "mode": self.state.mode,
        }

    def run_forever(
        self,
        poll_interval_seconds: float = 5.0,
        max_iterations: int | None = None,
    ) -> None:
        iteration = 0
        if not self._started:
            self.startup()
        self.logger.info(
            "run_forever start poll_interval=%s max_iterations=%s log=%s",
            poll_interval_seconds,
            max_iterations or "infinite",
            self.log_path,
        )
        while max_iterations is None or iteration < max_iterations:
            try:
                self.run_once()
            except Exception as exc:
                self._record_runtime_error(exc)
            iteration += 1
            self.sleep_fn(poll_interval_seconds)

    def close(self) -> None:
        if self._runtime_lock is None:
            return
        try:
            fcntl.flock(self._runtime_lock.fileno(), fcntl.LOCK_UN)
        finally:
            self._runtime_lock.close()
            self._runtime_lock = None

    # -- Conversation advancement -------------------------------------------

    def _advance_project_conversations(
        self,
        projects: list[DevProject],
        trigger: str,
    ) -> None:
        for project in projects:
            if project.status != ProjectStatus.open:
                continue
            latest = self.project_manager.get_project(project.project_id) or project

            # Pre-fetch external context so autonomy LLM can reference it
            if not latest.metadata.get("_github_context"):
                self._fetch_github_context(latest)
            if not latest.metadata.get("_jira_context"):
                self._fetch_jira_context(latest)
            if not latest.metadata.get("_datadog_context"):
                self._fetch_datadog_context(latest)

            channel_name = self.project_manager.resolve_channel_name(latest)
            intents = self.autonomy.plan_turns(
                latest, channel_name=channel_name, trigger=trigger
            )
            if not intents:
                continue

            self.logger.info(
                "autonomy trigger=%s project=%s stage=%s speakers=%s",
                trigger,
                latest.project_id,
                latest.stage.value,
                ",".join(i.agent for i in intents),
            )

            for intent in intents:
                persona = self.autonomy.registry.get(intent.agent)
                if persona is None:
                    continue
                message_ts = self._emit_project_message(
                    latest,
                    text=intent.text,
                    speaker=intent.agent,
                    display_name=persona.display_name,
                    icon_emoji=persona.icon_emoji,
                    kind=DevActivityKind.agent_message,
                    metadata={
                        "action": intent.action,
                        "trigger": trigger,
                        "mentions": list(intent.mention_targets),
                    },
                )
                latest = self.autonomy.record_turn(
                    latest,
                    intent,
                    message_ts=message_ts,
                )
                self.project_manager.save_project(latest)

    # -- Stage management ---------------------------------------------------

    def _workflow_for(self, project: DevProject) -> SprintWorkflow:
        """Return a workflow instance matching the project's type."""
        return SprintWorkflow.for_project_type(project.project_type.value)

    def _auto_advance_stages(self, projects: list[DevProject]) -> None:
        """Auto-advance stages where conversation is done and no human gate.

        For stages with ``auto_advance=True`` (intake, think, build, test, ship, reflect),
        once all stage participants have posted, the stage transitions automatically.
        For stages with ``requires_human_approval=True`` (plan, review, security),
        the project waits for explicit CEO approval via the UI.
        """
        for project in projects:
            if project.status != ProjectStatus.open:
                continue
            cfg = self._workflow_for(project).stage_config(project.stage)
            if not cfg.auto_advance:
                continue
            if cfg.requires_human_approval:
                continue
            # Check if conversation for this stage is done
            if not self.autonomy.is_stage_conversation_done(project):
                continue
            # Don't advance if we're on a spawn stage and agent hasn't reported
            if cfg.spawn_agent:
                spawn_key = self._spawn_key(project)
                if project.metadata.get(spawn_key) and not project.metadata.get(self._spawn_done_key(project)):
                    continue

            # Route to completion or next stage
            self._dispatch_stage_completion(project)

    @staticmethod
    def _spawn_key(project: DevProject) -> str:
        """Single source of truth for spawn metadata key."""
        return f"spawn_{project.stage.value}_{project.project_id}"

    @staticmethod
    def _spawn_done_key(project: DevProject) -> str:
        """Single source of truth for spawn-done metadata key."""
        return f"spawn_done_{project.stage.value}_{project.project_id}"

    def _dispatch_stage_completion(self, project: DevProject) -> None:
        """Route stage completion: terminal stage -> complete, others -> advance."""
        workflow = self._workflow_for(project)
        if workflow.is_terminal_stage(project.stage):
            self._complete_project_with_report(project)
        else:
            cfg = workflow.stage_config(project.stage)
            if cfg.auto_advance and not cfg.requires_human_approval:
                self._try_advance_stage(project)

    def _try_advance_stage(self, project: DevProject) -> DevProject:
        workflow = self._workflow_for(project)
        if workflow.can_advance(project, human_approved=True):
            old_stage = project.stage
            project = self.project_manager.advance_stage(
                project, human_approved=True
            )
            if project.stage != old_stage:
                self._emit_project_message(
                    project,
                    text=f"Stage transition: `{old_stage.value}` -> `{project.stage.value}`",
                    speaker="chief-of-staff",
                    display_name="System",
                    icon_emoji=":arrows_clockwise:",
                    kind=DevActivityKind.stage_transition,
                    metadata={"from_stage": old_stage.value, "to_stage": project.stage.value},
                )
                # Reset autonomy for new stage
                state = dict(project.metadata.get("autonomy", {}))
                state["posted_agents"] = []
                state["human_approved"] = False
                project.metadata["autonomy"] = state
                # Clear stale external context caches so next stage re-fetches
                for _ctx_key in ("_github_context", "_jira_context", "_datadog_context"):
                    project.metadata.pop(_ctx_key, None)
                self.project_manager.save_project(project)

                # Maybe spawn agent for new stage
                if workflow.should_spawn(project.stage):
                    self._maybe_spawn_build_agent(project)
        return project

    # -- Project completion (reflect -> done) ---------------------------------

    def _complete_project_with_report(self, project: DevProject) -> None:
        """Complete a project after reflect stage and generate CoS summary report."""
        if project.metadata.get("_completed"):
            return

        # 1. Generate CoS summary report via LLM
        report = self._generate_completion_report(project)

        # 2. Post the report as CoS message
        cos_persona = self.autonomy.registry.get("chief-of-staff")
        cos_name = cos_persona.display_name if cos_persona else "서준 (CoS)"
        self._emit_project_message(
            project,
            text=report,
            speaker="chief-of-staff",
            display_name=cos_name,
            icon_emoji=":clipboard:",
            kind=DevActivityKind.decision,
            metadata={"action": "completion_report", "report_type": "reflect_summary"},
        )

        # 3. Mark project as completed
        project.status = ProjectStatus.completed
        project.metadata["_completed"] = True
        project.metadata["completed_at"] = self.now_fn().isoformat()
        project.metadata["completion_report"] = report
        self.project_manager.save_project(project)

        # 4. Record a prominent activity for the dashboard
        self.control.record_activity(
            kind=DevActivityKind.decision,
            title=f"✅ 프로젝트 완료: {project.title}",
            body=report,
            author="chief-of-staff",
            project_id=project.project_id,
            stage="reflect",
            metadata={"action": "project_completed", "report_type": "completion_report"},
        )

        # 5. Extract knowledge for the global knowledge base
        try:
            from clawteam.devteam.knowledge import KnowledgeStore

            ks = KnowledgeStore(self.team_name)
            entry = ks.extract_knowledge_from_project(
                project_id=project.project_id,
                project_title=project.title,
                completion_report=report,
                stage_history=list(project.metadata.get("stage_history", [])),
            )
            if entry:
                ks.add_entry(entry)
        except Exception as exc:
            self.logger.debug("knowledge extraction failed: %s", exc)

        self.logger.info(
            "project completed project=%s title=%s",
            project.project_id,
            project.title,
        )

    def _generate_completion_report(self, project: DevProject) -> str:
        """Generate a completion summary report via LLM (CoS perspective)."""
        # Gather all discussion context
        prior_context = self._gather_prior_context(project)

        # Build stage timeline
        stage_history = list(project.metadata.get("stage_history", []))
        timeline = " → ".join(h.get("to", "?") for h in stage_history) if stage_history else "intake → reflect"

        system_prompt = (
            "너는 AI 개발회사의 '서준 (CoS)' (Chief of Staff)이다.\n"
            "프로젝트가 reflect 단계를 마치고 완료되었다.\n"
            "CEO에게 보고하는 완료 리포트를 작성하라.\n\n"
            "규칙:\n"
            "- 한국어로 간결하게 작성한다.\n"
            "- 마크다운 금지. 이모지 금지. 순수 텍스트만.\n"
            "- 구조: 1) 프로젝트 요약 (1줄) 2) 주요 결과물 3) 특이사항/리스크 4) 다음 액션\n"
            "- 5~8문장 이내. 구체적이고 실질적인 내용만.\n"
        )
        user_prompt = (
            f"프로젝트: {project.title}\n"
            f"설명: {project.description or '(없음)'}\n"
            f"유형: {project.project_type.value}\n"
            f"스테이지 경과: {timeline}\n\n"
            f"전체 논의 기록:\n{prior_context}\n\n"
            f"위 내용을 바탕으로 CEO에게 보고할 완료 리포트를 작성하라."
        )

        try:
            from clawteam.devteam.llm import chat
            report = chat(system_prompt, user_prompt, max_tokens=500)
            if report and report.strip():
                return report.strip()
        except Exception as exc:
            self.logger.warning("completion report LLM failed: %s", exc)

        # Fallback: template-based report
        return (
            f"[프로젝트 완료 보고] {project.title}\n"
            f"유형: {project.project_type.value} | 경과: {timeline}\n"
            f"설명: {project.description or '(없음)'}\n"
            f"모든 스테이지를 정상적으로 통과하여 완료되었습니다. "
            f"상세 내역은 프로젝트 대화 기록을 참고해 주세요."
        )

    # -- Agent spawning -----------------------------------------------------

    def _try_reuse_persistent_session(
        self,
        project: DevProject,
        stage_owner: str,
        stage: SprintStage,
        spawn_key: str,
    ) -> bool:
        """기존 tmux 세션이 살아있으면 followup prompt를 보내서 재사용.

        Returns True if session was reused (caller should return early).
        Returns False if no reusable session (caller should proceed with fresh spawn).
        """
        from clawteam.spawn.tmux_backend import TmuxBackend

        if not isinstance(self._spawn_backend, TmuxBackend):
            return False

        # Check persistent_sessions in project metadata
        persistent = project.metadata.get("persistent_sessions", {})
        session_info = persistent.get(stage_owner)
        if not session_info:
            return False

        tmux_target = session_info.get("tmux_target", "")
        agent_name = session_info.get("agent_name", "")
        if not tmux_target or not agent_name:
            return False

        # Check if tmux pane is still alive
        from clawteam.spawn.registry import is_agent_alive
        alive = is_agent_alive(self.team_name, agent_name)
        if not alive:
            self.logger.info(
                "persistent session dead for %s (project=%s), will fresh-spawn",
                stage_owner, project.project_id[:8],
            )
            return False

        # Build followup prompt (stage-specific)
        prior_context = self._gather_prior_context(project)
        gh_context = self._fetch_github_context(project)

        followup = (
            f"\n\n--- 새로운 스테이지: {stage.value} ---\n\n"
            f"프로젝트 '{project.title}'가 {stage.value} 단계로 진입했다.\n"
            f"이전 작업 컨텍스트를 유지한 채 새 작업을 수행하라.\n\n"
        )
        if gh_context:
            followup += f"## GitHub PR Context (updated)\n\n{gh_context}\n\n"

        jira_context = self._fetch_jira_context(project)
        if jira_context:
            followup += f"## Jira Issue Context\n\n{jira_context}\n\n"

        datadog_context = self._fetch_datadog_context(project)
        if datadog_context:
            followup += f"## Datadog Log Context\n\n{datadog_context}\n\n"

        # Stage instruction
        stage_instruction = self._get_stage_instruction(stage)
        if not stage_instruction:
            return False

        followup += f"## Instructions\n\n{stage_instruction}"

        # Inject persona memory context
        memory_ctx = self._get_persona_memory_context(stage_owner)
        if memory_ctx:
            followup += f"\n\n## Your Experience (from past projects)\n\n{memory_ctx}"

        # Inject global knowledge context
        knowledge_ctx = self._get_knowledge_context(project)
        if knowledge_ctx:
            followup += f"\n\n## Company Knowledge Base\n\n{knowledge_ctx}"

        # Send followup prompt to existing tmux session
        result = self._spawn_backend.send_followup_prompt(
            target=tmux_target,
            prompt=followup,
            agent_name=agent_name,
        )

        if isinstance(result, str) and result.startswith("Error"):
            self.logger.warning(
                "followup failed for %s: %s — will fresh-spawn",
                agent_name, result,
            )
            return False

        # Success — mark as spawned for this stage
        project.metadata[spawn_key] = True
        self.project_manager.save_project(project)

        # Update session to reflect new stage
        session_ids = dict(project.metadata.get("session_ids", {}))
        session_id = str(session_ids.get(stage_owner, ""))
        if session_id:
            session = self.sessions.events.get_session(session_id)
            if session:
                session.details["current_stage"] = stage.value
                session.details["followup_count"] = session.details.get("followup_count", 0) + 1
                self.sessions.update_session(session)

        self.control.record_activity(
            kind=DevActivityKind.worklog,
            title=f"Continued {stage_owner} session for {stage.value} (persistent)",
            body=f"Reused existing tmux session {tmux_target}",
            author=stage_owner,
            project_id=project.project_id,
            stage=stage.value,
            metadata={"agent_name": agent_name, "tmux_target": tmux_target, "followup": True},
        )
        self.logger.info(
            "reused persistent session for %s stage=%s project=%s",
            stage_owner, stage.value, project.project_id[:8],
        )
        return True

    def _get_stage_instruction(self, stage: SprintStage) -> str | None:
        """스테이지별 지시사항 반환 (프롬프트 재사용을 위해 추출)."""
        _report = f"clawteam inbox send {self.team_name} chief-of-staff"
        stage_prompts = {
            SprintStage.intake: (
                f"Accept and classify the project. Organize project type, priority, and assignees, "
                f"then request architecture review from the CTO.\n"
                f"When done, report via `{_report} 'Intake complete'`."
            ),
            SprintStage.think: (
                f"Review the architecture. Analyze from system design, tech stack, and scalability perspectives, "
                f"and evaluate implementation feasibility. Collaborate with Lead Engineer for technical decisions.\n"
                f"When done, report via `{_report} 'Architecture review complete'`."
            ),
            SprintStage.plan: (
                f"Create a detailed implementation plan. Reflect architecture review results, "
                f"break down tasks, set timeline, and identify risks. Collaborate with Designer on UI/UX.\n"
                f"When done, report via `{_report} 'Plan complete'`."
            ),
            SprintStage.build: (
                f"Implement based on the discussion above. "
                f"Faithfully reflect the architecture/design agreed upon by the CTO and team.\n"
                f"When done, report via `{_report} 'Implementation complete'`."
            ),
            SprintStage.test: (
                f"Write and run tests. Verify unit test and integration test coverage.\n"
                f"When done, report via `{_report} 'Testing complete'`."
            ),
            SprintStage.review: (
                f"Conduct a multi-perspective code review as coordinating reviewer.\n\n"
                f"Review the implementation from THREE perspectives:\n"
                f"1. **Security**: Input validation, auth/authz flaws, secrets in code, injection risks, unsafe deserialization\n"
                f"2. **Performance**: Algorithm complexity, N+1 queries, memory leaks, blocking I/O, resource leaks\n"
                f"3. **Architecture**: SOLID principles, module boundaries, API consistency, error handling, test coverage\n\n"
                f"For each perspective, rate as CRITICAL / WARNING / CLEAN and provide specific findings.\n"
                f"Synthesize into a unified review summary with: critical issues, suggestions, and approval recommendation.\n"
                f"When done, report via `{_report} 'Code review complete'`."
            ),
            SprintStage.security: (
                f"Perform security audit. Check OWASP Top 10, auth/authz, input validation.\n"
                f"When done, report via `{_report} 'Security audit complete'`."
            ),
        }
        return stage_prompts.get(stage)

    def _get_persona_memory_context(self, stage_owner: str) -> str:
        """페르소나의 장기 메모리에서 프롬프트 컨텍스트를 가져온다."""
        try:
            from clawteam.devteam.memory import PersonaMemoryStore
            store = PersonaMemoryStore(self.team_name)
            return store.get_context_for_prompt(stage_owner, max_chars=2000)
        except Exception:
            return ""

    def _get_knowledge_context(self, project: "DevProject") -> str:
        """Load relevant global knowledge for project context."""
        try:
            from clawteam.devteam.knowledge import KnowledgeStore
            ks = KnowledgeStore(self.team_name)
            return ks.get_context_for_prompt(
                f"{project.title} {project.description}",
                max_chars=1500,
            )
        except Exception:
            return ""

    def _maybe_spawn_build_agent(self, project: DevProject) -> None:
        spawn_key = self._spawn_key(project)
        if project.metadata.get(spawn_key):
            return  # Already spawned for this stage

        workflow = self._workflow_for(project)
        stage_owner = workflow.stage_owner(project.stage)
        stage = project.stage

        # -- Persistent session: try reusing existing tmux session ----------
        reused = self._try_reuse_persistent_session(project, stage_owner, stage, spawn_key)
        if reused:
            return

        # Gather discussion/plan context from prior stages
        prior_context = self._gather_prior_context(project)

        # Build persona context for the stage owner
        persona = self.autonomy.registry.get(stage_owner)
        persona_block = ""
        if persona:
            persona_block = (
                f"## Your Role\n\n"
                f"- Name: {persona.display_name}\n"
                f"- Title: {persona.role}\n"
                f"- Style: {persona.style}\n"
                f"- Responsibilities: {', '.join(persona.responsibilities)}\n\n"
            )

        # Supporting agents context
        cfg = workflow.stage_config(stage)
        supporting = cfg.supporting_agents
        supporting_block = ""
        if supporting:
            lines = []
            for sa in supporting:
                sp = self.autonomy.registry.get(sa)
                if sp:
                    lines.append(f"- {sp.display_name} ({sp.role})")
            if lines:
                supporting_block = f"## Team Members\n\n" + "\n".join(lines) + "\n\n"

        # Stage-specific prompts (single source: _get_stage_instruction)
        stage_instruction = self._get_stage_instruction(stage)
        if stage_instruction is None:
            return

        prompt = (
            f"Project: {project.title}\n"
            f"Description: {project.description or '(none)'}\n"
            f"Current stage: {stage.value}\n\n"
            f"{persona_block}"
            f"{supporting_block}"
        )
        if prior_context and prior_context != "(No prior stage discussion records)":
            prompt += f"## Prior Stage Discussion\n\n{prior_context}\n\n"

        # Inject GitHub PR context for all spawned stages
        gh_context = self._fetch_github_context(project)
        if gh_context:
            prompt += f"## GitHub PR Context\n\n{gh_context}\n\n"

        # Inject Jira issue context
        jira_context = self._fetch_jira_context(project)
        if jira_context:
            prompt += f"## Jira Issue Context\n\n{jira_context}\n\n"

        # Inject Datadog log context
        datadog_context = self._fetch_datadog_context(project)
        if datadog_context:
            prompt += f"## Datadog Log Context\n\n{datadog_context}\n\n"

        prompt += f"## Instructions\n\n{stage_instruction}"

        # Inject persona memory from past projects
        memory_ctx = self._get_persona_memory_context(stage_owner)
        if memory_ctx:
            prompt += f"\n\n## Your Experience (from past projects)\n\n{memory_ctx}"

        # Inject global knowledge context
        knowledge_ctx = self._get_knowledge_context(project)
        if knowledge_ctx:
            prompt += f"\n\n## Company Knowledge Base\n\n{knowledge_ctx}"

        agent_name = f"{stage_owner}-{project.project_id[:8]}"
        workspace = self._workspace_for_agent(stage_owner)
        self._ensure_claude_md(workspace)
        prompt = self._augment_spawn_prompt(prompt, workspace)
        session = self.sessions.start_session(
            agent_name=agent_name,
            agent_id=agent_name,
            agent_type=stage_owner,
            project_id=project.project_id,
            stage=project.stage.value,
            workspace_path=workspace,
            details={"prompt": prompt[:1200], "stageOwner": stage_owner},
        )
        try:
            spawn_env = self._build_claude_spawn_env()
            result = self._spawn_backend.spawn(
                command=["claude"],
                agent_name=agent_name,
                agent_id=agent_name,
                agent_type=stage_owner,
                team_name=self.team_name,
                prompt=prompt,
                cwd=workspace,
                env=spawn_env,
                skip_permissions=True,
            )
            if isinstance(result, str) and result.startswith("Error"):
                # Dynamic backend fallback: retry with Bedrock if Team Plan exhausted
                if self._should_fallback_to_bedrock(result):
                    self.logger.warning("Team Plan quota issue, retrying with Bedrock: %s", result[:200])
                    self.control.record_activity(
                        kind=DevActivityKind.worklog,
                        title="Switching to Bedrock backend (Team Plan quota)",
                        body=result[:300],
                        author="runtime",
                        project_id=project.project_id,
                        stage=project.stage.value,
                    )
                    bedrock_env = self._build_claude_spawn_env(force_bedrock=True)
                    result = self._spawn_backend.spawn(
                        command=["claude"],
                        agent_name=agent_name,
                        agent_id=agent_name,
                        agent_type=stage_owner,
                        team_name=self.team_name,
                        prompt=prompt,
                        cwd=workspace,
                        env=bedrock_env,
                        skip_permissions=True,
                    )
                if isinstance(result, str) and result.startswith("Error"):
                    raise DevTeamRuntimeError(result)
            project.metadata[spawn_key] = True
            if workspace:
                project.metadata.setdefault("workspaces", {})[stage_owner] = workspace
            project.metadata.setdefault("session_ids", {})[stage_owner] = session.session_id

            # Record persistent session for future stage reuse
            tmux_target = f"clawteam-{self.team_name}:{agent_name}"
            project.metadata.setdefault("persistent_sessions", {})[stage_owner] = {
                "tmux_target": tmux_target,
                "agent_name": agent_name,
                "initial_stage": stage.value,
                "workspace": workspace,
            }

            self.project_manager.save_project(project)
            session.status = DevSessionStatus.running
            session.details["spawn_result"] = result
            self.sessions.update_session(session)
            self.sessions.refresh_sessions()
            self.control.record_activity(
                kind=DevActivityKind.worklog,
                title=f"Spawned {stage.value} agent",
                body=prompt[:400],
                author=stage_owner,
                project_id=project.project_id,
                stage=project.stage.value,
                metadata={"agent_name": agent_name, "workspace": workspace, "session_id": session.session_id},
            )
            self.logger.info(
                "spawned agent=%s stage=%s project=%s",
                agent_name,
                stage.value,
                project.project_id,
            )
        except Exception as exc:
            self.logger.error("spawn failed: %s", exc)
            session.status = DevSessionStatus.failed
            session.ended_at = self.now_fn().isoformat()
            session.details["error"] = str(exc)
            self.sessions.update_session(session)

            # CRITICAL: Mark spawn_key even on failure to prevent infinite retry loop.
            # Without this, _ensure_stage_spawns() retries every tick (5s) forever,
            # creating hundreds of failed sessions.
            fail_count = project.metadata.get(f"spawn_fail_count_{stage.value}", 0) + 1
            project.metadata[f"spawn_fail_count_{stage.value}"] = fail_count
            if fail_count >= 3:
                project.metadata[spawn_key] = True  # Stop retrying after 3 failures
                self.logger.error(
                    "spawn failed %d times for %s/%s, giving up",
                    fail_count, stage.value, project.project_id[:8],
                )
            self.project_manager.save_project(project)

            self.control.record_activity(
                kind=DevActivityKind.error,
                title=f"Spawn failed for {stage.value} (attempt {fail_count}/3)",
                body=str(exc),
                author="runtime",
                project_id=project.project_id,
                stage=project.stage.value,
                metadata={"agent_name": agent_name, "session_id": session.session_id, "fail_count": fail_count},
            )

    def _check_all_agent_results(self) -> None:
        for project in self.project_manager.list_projects():
            if project.status != ProjectStatus.open:
                continue
            if not self._workflow_for(project).should_spawn(project.stage):
                continue
            self._check_agent_results(project)

    def _check_agent_results(self, project: DevProject) -> None:
        """Check whether the spawned agent for the current stage reported done.

        Scans **both** the stage-owner's inbox AND the global event log
        (since agents often send completion messages to other recipients
        like ``cto`` or ``chief-of-staff`` rather than themselves).
        """
        # Guard: skip if already processed (prevents replay and double-advance)
        if project.metadata.get(self._spawn_done_key(project)):
            return

        workflow = self._workflow_for(project)
        stage_owner = workflow.stage_owner(project.stage)
        agent_name = f"{stage_owner}-{project.project_id[:8]}"

        _DONE_KEYWORDS = ("complete", "done", "finished", "완료")

        # 1. Check chief-of-staff inbox (unified report target)
        #    Use peek() first to avoid consuming other projects' messages,
        #    then consume only the matched message.
        done_msg: str | None = None
        for inbox_name in ("chief-of-staff", stage_owner):
            messages = self.mailbox.peek(inbox_name)
            for msg in messages:
                content = str(getattr(msg, "content", "")).lower()
                if any(kw in content for kw in _DONE_KEYWORDS):
                    done_msg = str(getattr(msg, "content", ""))
                    # Consume all peeked messages from this inbox to clear them
                    self.mailbox.receive(inbox_name, limit=len(messages))
                    break
            if done_msg:
                break

        # 2. Fallback: scan event log for messages FROM this agent
        if not done_msg:
            events = self.mailbox.get_event_log(limit=50)
            for evt in events:
                sender = str(getattr(evt, "from_agent", "")).lower()
                # Match by agent_name or stage_owner (agents may use either)
                if sender not in (agent_name.lower(), stage_owner.lower()):
                    continue
                content = str(getattr(evt, "content", "")).lower()
                if any(kw in content for kw in _DONE_KEYWORDS):
                    done_msg = str(getattr(evt, "content", ""))
                    break

        if not done_msg:
            return

        self._emit_project_message(
            project,
            text=f"`{stage_owner}` agent reported work complete. Attempting auto stage transition.",
            speaker=stage_owner,
            display_name=stage_owner,
            icon_emoji=":white_check_mark:",
            kind=DevActivityKind.worklog,
            metadata={"mailbox_message": done_msg},
        )
        session_ids = dict(project.metadata.get("session_ids", {}))
        session_id = str(session_ids.get(stage_owner, ""))
        session = self.sessions.events.get_session(session_id) if session_id else None
        if session is not None:
            session.status = DevSessionStatus.completed
            session.ended_at = self.now_fn().isoformat()
            session.details["reported_done"] = True
            session.details["completion_message"] = done_msg
            self.sessions.update_session(session)

        # Mark spawn as done so _auto_advance_stages can proceed
        project.metadata[self._spawn_done_key(project)] = True
        self.project_manager.save_project(project)

        # 3. Save persona learning memory for this stage
        self._save_persona_memory(project, stage_owner, done_msg)

        # 4. Persistent session: DON'T terminate if next stage needs same persona.
        # Only terminate if project is at terminal stage or next stage has different owner.
        has_persistent = bool(project.metadata.get("persistent_sessions", {}).get(stage_owner))
        next_stage = workflow.next_stage(project.stage)
        should_keep_alive = False
        if has_persistent and next_stage:
            next_owner = workflow.stage_owner(next_stage)
            if next_owner == stage_owner:
                should_keep_alive = True
                self.logger.info(
                    "keeping persistent session alive: %s needs %s for next stage %s",
                    agent_name, stage_owner, next_stage.value,
                )

        if not should_keep_alive:
            self._terminate_agent(agent_name)
            # Clean up persistent session entry
            persistent = project.metadata.get("persistent_sessions", {})
            persistent.pop(stage_owner, None)
            self.project_manager.save_project(project)

        self._dispatch_stage_completion(project)

    # -- Persona memory saving ------------------------------------------------

    def _save_persona_memory(self, project: DevProject, stage_owner: str, done_msg: str) -> None:
        """스테이지 완료 시 페르소나 학습 메모리를 저장."""
        try:
            from clawteam.devteam.memory import PersonaMemoryStore
            store = PersonaMemoryStore(self.team_name)

            # Gather discussion context for this stage
            prior_context = self._gather_prior_context(project)
            discussion = f"Stage: {project.stage.value}\nProject: {project.title}\n\n{prior_context}\n\nCompletion: {done_msg}"

            entry = store.generate_learning_summary(
                persona_name=stage_owner,
                project_id=project.project_id,
                project_title=project.title,
                stage=project.stage.value,
                discussion_context=discussion[:3000],
            )
            store.save_memory(stage_owner, entry)
            self.logger.info("saved persona memory for %s stage=%s", stage_owner, project.stage.value)
        except Exception as exc:
            self.logger.debug("persona memory save failed: %s", exc)

    # -- Agent termination ---------------------------------------------------

    def _terminate_agent(self, agent_name: str) -> None:
        """Gracefully terminate an idle agent after it reports completion.

        For tmux: sends ``/exit`` + Enter to the pane.
        For subprocess: sends SIGTERM to the process.
        """
        import signal
        import subprocess as _sp

        from clawteam.spawn.registry import get_spawn_info

        info = get_spawn_info(agent_name, team_name=self.team_name)
        if not info:
            self.logger.debug("no spawn info for %s, skipping terminate", agent_name)
            return

        backend = info.get("backend", "")
        if backend == "tmux":
            target = info.get("tmux_target", "")
            if target:
                try:
                    # Send /exit to Claude Code interactive prompt
                    _sp.run(
                        ["tmux", "send-keys", "-t", target, "/exit", "Enter"],
                        stdout=_sp.PIPE, stderr=_sp.PIPE, timeout=5,
                    )
                    self.logger.info("sent /exit to tmux agent %s (%s)", agent_name, target)
                except Exception as exc:
                    self.logger.debug("tmux terminate failed for %s: %s", agent_name, exc)
        elif backend == "subprocess":
            pid = info.get("pid", 0)
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    self.logger.info("sent SIGTERM to subprocess agent %s (pid=%d)", agent_name, pid)
                except ProcessLookupError:
                    pass
                except Exception as exc:
                    self.logger.debug("subprocess terminate failed for %s: %s", agent_name, exc)

    # -- Dead agent recovery ------------------------------------------------

    def _recover_dead_agents(self, projects: list[DevProject]) -> None:
        """Detect dead agents and re-spawn them for their current stage.

        If an agent process dies (tmux pane closed, PID gone) without
        reporting "done", clear the spawn marker so the next loop iteration
        will re-spawn a fresh agent for that stage.
        """
        for project in projects:
            if project.status != ProjectStatus.open:
                continue
            workflow = self._workflow_for(project)
            cfg = workflow.stage_config(project.stage)
            if not cfg.spawn_agent:
                continue

            spawn_key = self._spawn_key(project)
            done_key = self._spawn_done_key(project)

            # Only check projects where we spawned but didn't get a done signal
            if not project.metadata.get(spawn_key):
                continue
            if project.metadata.get(done_key):
                continue

            # Check if the session for this stage is dead
            session_ids = dict(project.metadata.get("session_ids", {}))
            stage_owner = workflow.stage_owner(project.stage)
            session_id = str(session_ids.get(stage_owner, ""))
            if not session_id:
                continue

            session = self.events.get_session(session_id)
            if session is None:
                continue

            if session.status not in (DevSessionStatus.failed, DevSessionStatus.completed):
                continue

            # Don't recover if agent reported done
            if session.details.get("reported_done"):
                continue

            # Already recovered once? Check retry count
            retries = int(project.metadata.get(f"_recover_count_{project.stage.value}", 0))
            if retries >= 2:
                self.logger.warning(
                    "dead agent recovery exhausted retries=%d project=%s stage=%s",
                    retries, project.project_id, project.stage.value,
                )
                continue

            # Clear spawn marker so _ensure_stage_spawns will re-spawn
            project.metadata.pop(spawn_key, None)
            project.metadata[f"_recover_count_{project.stage.value}"] = retries + 1
            self.project_manager.save_project(project)

            self._emit_project_message(
                project,
                text=f"에이전트 프로세스가 비정상 종료되었습니다. 자동 복구를 시도합니다. (시도 {retries + 1}/2)",
                speaker="chief-of-staff",
                display_name="System",
                icon_emoji=":warning:",
                kind=DevActivityKind.system,
                metadata={"action": "dead_agent_recovery", "retry": retries + 1, "session_id": session_id},
            )

            self.control.record_activity(
                kind=DevActivityKind.system,
                title=f"Dead agent recovery: {stage_owner}",
                body=f"Agent process died for {project.title} at {project.stage.value}. Re-spawning (attempt {retries + 1}/2).",
                author="runtime",
                project_id=project.project_id,
                stage=project.stage.value,
                metadata={"session_id": session_id, "retry": retries + 1},
            )

            self.logger.info(
                "dead agent recovery project=%s stage=%s retry=%d",
                project.project_id, project.stage.value, retries + 1,
            )

    # -- Helpers ------------------------------------------------------------

    def _ensure_stage_spawns(self) -> None:
        for project in self.project_manager.list_projects():
            if project.status != ProjectStatus.open:
                continue
            if self._workflow_for(project).should_spawn(project.stage):
                self._maybe_spawn_build_agent(project)

        # Scale developer pool based on projects needing build work
        build_projects = [
            p for p in self.project_manager.list_projects()
            if p.status == ProjectStatus.open
            and p.stage in (SprintStage.build, SprintStage.test)
        ]
        self._scale_developers(len(build_projects))

    def _scale_developers(self, needed: int) -> None:
        """Dynamically spawn developers from the pool based on demand.

        Args:
            needed: Number of projects currently in build/test stage.
        """
        pool = self.runtime.blueprint.developer_pool
        if not pool or not pool.personas:
            return

        active_devs = list(self.state.metadata.get("active_developers", []))
        current_count = len(active_devs)

        # Clamp needed to pool bounds
        target = max(pool.min_developers, min(needed, pool.max_developers))

        if current_count >= target:
            return

        to_spawn = target - current_count
        available_personas = [
            p for p in pool.personas
            if p.name not in [d.get("persona_name") for d in active_devs]
        ]

        for persona in available_personas[:to_spawn]:
            agent_name = f"pool-dev-{persona.specialty}-{len(active_devs) + 1}"
            workspace = self._workspace_for_agent(agent_name)
            self._ensure_claude_md(workspace)
            prompt = (
                f"## Your Role\n\n"
                f"- Name: {persona.name}\n"
                f"- Style: {persona.style}\n"
                f"- Specialty: {persona.specialty}\n\n"
                f"## Instructions\n\n"
                f"You are a developer from the team pool. "
                f"Pick up build or test tasks from the mailbox and execute them. "
                f"Report progress via `clawteam inbox send {self.team_name} chief-of-staff 'Task update: ...'`."
            )
            prompt = self._augment_spawn_prompt(prompt, workspace)

            session = self.sessions.start_session(
                agent_name=agent_name,
                agent_id=agent_name,
                agent_type="pool-developer",
                project_id="",
                stage="pool",
                workspace_path=workspace,
                details={
                    "prompt": prompt[:1200],
                    "persona_name": persona.name,
                    "specialty": persona.specialty,
                },
            )
            try:
                spawn_env = self._build_claude_spawn_env()
                result = self._spawn_backend.spawn(
                    command=["claude"],
                    agent_name=agent_name,
                    agent_id=agent_name,
                    agent_type="pool-developer",
                    team_name=self.team_name,
                    prompt=prompt,
                    cwd=workspace,
                    env=spawn_env,
                )
                if isinstance(result, str) and result.startswith("Error"):
                    if self._should_fallback_to_bedrock(result):
                        self.logger.warning("Team Plan quota issue (pool), retrying with Bedrock")
                        result = self._spawn_backend.spawn(
                            command=["claude"],
                            agent_name=agent_name,
                            agent_id=agent_name,
                            agent_type="pool-developer",
                            team_name=self.team_name,
                            prompt=prompt,
                            cwd=workspace,
                            env=self._build_claude_spawn_env(force_bedrock=True),
                        )
                    if isinstance(result, str) and result.startswith("Error"):
                        raise DevTeamRuntimeError(result)
                active_devs.append({
                    "persona_name": persona.name,
                    "agent_name": agent_name,
                    "specialty": persona.specialty,
                    "session_id": session.session_id,
                })
                self.state.metadata["active_developers"] = active_devs
                session.status = DevSessionStatus.running
                session.details["spawn_result"] = result
                self.sessions.update_session(session)
                self.control.record_activity(
                    kind=DevActivityKind.worklog,
                    title=f"Scaled developer pool: spawned {persona.name}",
                    body=f"Specialty: {persona.specialty}",
                    author="runtime",
                    metadata={
                        "agent_name": agent_name,
                        "session_id": session.session_id,
                        "persona_name": persona.name,
                    },
                )
                self.logger.info(
                    "pool spawned dev=%s specialty=%s",
                    agent_name,
                    persona.specialty,
                )
            except Exception as exc:
                self.logger.error("pool spawn failed: %s", exc)
                session.status = DevSessionStatus.failed
                session.ended_at = self.now_fn().isoformat()
                session.details["error"] = str(exc)
                self.sessions.update_session(session)

    def _emit_project_message(
        self,
        project: DevProject,
        *,
        text: str,
        speaker: str,
        display_name: str,
        icon_emoji: str,
        kind: DevActivityKind,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        message_ts = self.now_fn().isoformat()
        self.control.record_activity(
            kind=kind,
            title=project.title,
            body=text,
            author=speaker,
            project_id=project.project_id,
            stage=project.stage.value,
            participants=list(project.assigned_agents),
            metadata=metadata or {},
        )
        return message_ts

    def _tick_live_meetings(self) -> list[dict[str, Any]]:
        persona_context = {
            persona.agent: {
                "display_name": persona.display_name or persona.agent,
                "role": persona.role,
            }
            for persona in self.runtime.blueprint.personas
        }
        emitted = self.meetings.tick_live_meetings(persona_context)
        for message in emitted:
            self.control.record_activity(
                kind=DevActivityKind.meeting,
                title=f"Meeting update: {message.speaker}",
                body=message.body,
                author=message.speaker,
                project_id=message.project_id,
                participants=[],
                metadata={"meeting_id": message.meeting_id, "message_id": message.message_id, **message.metadata},
            )
        return [message.model_dump(mode="json") for message in emitted]

    def _gather_prior_context(self, project: DevProject) -> str:
        """Collect discussion/plan context from prior stages for spawned agents."""
        sections: list[str] = []

        # 1. Autonomy ledger -- all agent discussion turns from prior stages
        autonomy_state = dict(project.metadata.get("autonomy", {}))
        ledger = list(autonomy_state.get("ledger", []))
        if ledger:
            lines = []
            for entry in ledger[-30:]:  # Last 30 turns max
                agent = entry.get("agent", "?")
                persona = self.autonomy.registry.get(agent)
                name = persona.display_name if persona else agent
                stage = entry.get("stage", "?")
                text = entry.get("text", "")
                if text:
                    lines.append(f"[{stage}] {name}: {text}")
            if lines:
                sections.append("### Team Discussion Log\n" + "\n".join(lines))

        # 2. Meeting messages related to this project
        meetings = self.meetings.list_meetings(project_id=project.project_id)
        for meeting in meetings[-3:]:  # Last 3 meetings
            messages = self.meetings.list_messages(meeting.meeting_id)
            if messages:
                msg_lines = [f"**Meeting: {meeting.title or meeting.agenda}**"]
                for msg in messages[-15:]:
                    msg_lines.append(f"- {msg.speaker}: {msg.body}")
                sections.append("\n".join(msg_lines))

        # 3. Human instructions
        human_text = str(autonomy_state.get("last_human_message_text", "")).strip()
        if human_text:
            sections.append(f"### CEO Final Instruction\n{human_text}")

        if not sections:
            return "(No prior stage discussion records)"

        return "\n\n".join(sections)

    def _workspace_for_agent(self, agent_name: str) -> str:
        if self.workspace_manager is None:
            return self.workspace_dir
        existing = self.workspace_manager.get_workspace(self.team_name, agent_name)
        if existing is not None:
            return existing.worktree_path
        created = self.workspace_manager.create_workspace(
            self.team_name,
            agent_name=agent_name,
            agent_id=f"{self.team_name}-{agent_name}",
        )
        return created.worktree_path

    # -- CLAUDE.md propagation ------------------------------------------------

    _LBOX_CLAUDE_MD = """\
# ClawTeam Agent Instructions

## LBox 코딩 철학 7원칙

1. **메시지 패싱**: 캡슐화 유지 — 내부 구현을 노출하지 않는다
2. **높은 응집도, 낮은 결합도**: 유사한 책임은 모으고, 의존성은 최소화
3. **Early Exit**: 예외 상황을 먼저 처리하고 Happy Path 진행
4. **Custom Exception**: 명확한 이름의 예외로 의도 전달
5. **테스트는 실패 케이스 중심**: Failure ≥ 60%, Happy Path ≤ 40%
6. **Factory Pattern**: 복잡한 생성 로직은 Factory로 분리
7. **Value Object**: 타입 안전성과 유효성 검증 캡슐화

## Code Review Checklist

- [ ] 보안: 인젝션, 인증/인가, 시크릿 노출
- [ ] 성능: 알고리즘 복잡도, N+1 쿼리, 메모리 누수
- [ ] 아키텍처: SOLID, 모듈 경계, API 일관성
- [ ] 에러 처리: Custom Exception 사용, 복구 가능성
- [ ] 테스트: 실패 케이스 비율 60%+, 경계값

## Git Workflow

- Commit 메시지는 한 줄 요약 + 본문 형식
- feature 브랜치에서 작업, main 직접 push 금지
- 테스트 통과 없이 PR 생성 금지
"""

    def _ensure_claude_md(self, workspace: str) -> None:
        """Ensure the agent workspace has a .claude/CLAUDE.md with LBox principles.

        If the workspace already has one (e.g. from the project root), the
        existing file is preserved.  Otherwise, creates a new one with the
        standard LBox coding philosophy and review checklist.
        """
        from pathlib import Path

        if not workspace:
            return

        claude_dir = Path(workspace) / ".claude"
        claude_md = claude_dir / "CLAUDE.md"

        if claude_md.exists():
            return

        # Also check for project-root CLAUDE.md (one level up or same dir)
        project_claude = Path(self.workspace_dir) / "CLAUDE.md"
        try:
            claude_dir.mkdir(parents=True, exist_ok=True)
            if project_claude.exists():
                # Symlink to project-root CLAUDE.md so agents share the same config
                claude_md.symlink_to(project_claude.resolve())
                self.logger.debug("symlinked CLAUDE.md in %s → %s", workspace, project_claude)
            else:
                claude_md.write_text(self._LBOX_CLAUDE_MD, encoding="utf-8")
                self.logger.debug("wrote LBox CLAUDE.md to %s", workspace)
        except OSError as exc:
            self.logger.debug("failed to propagate CLAUDE.md: %s", exc)

    def _augment_spawn_prompt(self, prompt: str, workspace: str) -> str:
        guidance = [prompt.strip()]
        if workspace:
            guidance.append(f"Working directory: {workspace}")

        # Load AGENTS.md content from opencode-config (key sections only)
        agents_md_content = self._load_agents_md_summary()
        if agents_md_content:
            guidance.append(f"## Coding Standards (from AGENTS.md)\n\n{agents_md_content}")

        rules = list(self.opencode_profile.get("rules", []))
        if rules:
            guidance.append(f"Operating rules to follow first: {rules[0]}")

        skills_root = str(self.opencode_profile.get("skillsRoot", "")).strip()
        if skills_root:
            guidance.append(
                f"Available OpenCode skills root: {skills_root}\n"
                f"You can reference skills in {skills_root}/ for specialized tasks."
            )

        guidance.append(
            "## Critical Rules\n\n"
            "- **절대 `gh pr checkout`이나 `git checkout` 등 워크트리를 변경하는 명령을 실행하지 마라.**\n"
            "  GitHub PR Context 섹션에 이미 diff, 변경 파일 목록, PR 정보가 모두 포함되어 있다.\n"
            "  checkout은 퍼미션 충돌과 워크트리 손상을 유발한다.\n"
            "- `gh pr diff`, `gh pr view` 등 읽기 전용 명령은 사용 가능하다.\n"
            "- 코드를 직접 수정해야 할 때는 현재 워크트리의 파일을 직접 편집하라.\n"
            "- Always follow the repo's AGENTS.md / dev rules first.\n"
            "- **작업 완료 후 반드시 mailbox로 보고하고, 그 즉시 `/exit`을 입력하여 세션을 종료하라.**\n"
            "  예: mailbox 전송 → `/exit` (idle 상태로 남지 마라)"
        )
        return "\n\n".join(part for part in guidance if part)

    def _load_agents_md_summary(self) -> str:
        """Read the AGENTS.md from opencode-config and return key sections.

        Returns a condensed version (first ~3000 chars) to avoid bloating
        the spawn prompt while still giving agents the coding philosophy,
        testing guidelines, and git workflow.
        """
        from pathlib import Path

        rules = list(self.opencode_profile.get("rules", []))
        for rule_path in rules:
            p = Path(rule_path)
            if p.exists() and p.name == "AGENTS.md":
                try:
                    content = p.read_text(encoding="utf-8")
                    # Return a reasonable summary -- first 3000 chars covers
                    # philosophy, skill system overview, and key guidelines
                    if len(content) > 3000:
                        # Try to cut at a section boundary
                        cut = content[:3000].rfind("\n## ")
                        if cut > 1500:
                            return content[:cut].strip()
                        return content[:3000].strip() + "\n\n(...truncated)"
                    return content.strip()
                except OSError:
                    pass
        return ""

    def _fetch_github_context(self, project: DevProject) -> str:
        """Extract PR info from GitHub if the project references a PR.

        Parses repo + PR number from the project title/description,
        fetches PR details, changed files, diff, and Actions status.
        Caches the result in project metadata to avoid re-fetching.
        """
        # Check cache first
        cached = project.metadata.get("_github_context")
        if cached:
            return cached

        if not self.integrations.get("github"):
            return ""

        try:
            from clawteam.devteam.github import (
                extract_pr_number,
                extract_repo_from_text,
                fetch_pr_context_for_project,
            )

            combined_text = f"{project.title} {project.description} {project.repository}"
            pr_number = extract_pr_number(combined_text)
            repo = project.repository or extract_repo_from_text(combined_text)

            if not pr_number or not repo:
                self.logger.info(
                    "GitHub context extraction failed: pr=%s repo=%s "
                    "title=%r desc=%r repo_field=%r",
                    pr_number, repo,
                    project.title[:80], (project.description or "")[:80],
                    project.repository,
                )
                return ""

            self.logger.info("fetching GitHub context repo=%s pr=%d", repo, pr_number)
            ctx = fetch_pr_context_for_project(
                repo, pr_number,
                include_diff=True,
                max_diff_chars=6000,
            )

            if "error" in ctx:
                self.logger.warning("GitHub context error: %s", ctx["error"])
                return ""

            pr = ctx.get("pr", {})
            files = ctx.get("files", [])
            diff = ctx.get("diff", "")
            actions = ctx.get("actions", [])

            lines = [
                f"PR #{pr.get('number')}: {pr.get('title')}",
                f"Author: {pr.get('author')} | Branch: {pr.get('headBranch')} → {pr.get('baseBranch')}",
                f"Changes: +{pr.get('additions', 0)} -{pr.get('deletions', 0)} ({pr.get('changedFiles', 0)} files)",
                f"Mergeable: {pr.get('mergeable', 'N/A')} | Review: {pr.get('reviewDecision', 'N/A')}",
                f"Checks: {pr.get('checksStatus', 'N/A')}",
            ]

            if pr.get("labels"):
                lines.append(f"Labels: {', '.join(pr['labels'])}")

            # Actions runs
            if actions:
                lines.append("\nGitHub Actions:")
                for run in actions[:5]:
                    conclusion = run.get("conclusion") or run.get("status", "?")
                    lines.append(f"  - {run.get('name', '?')}: {conclusion}")

            # Changed files
            if files:
                lines.append(f"\nChanged files ({len(files)}):")
                for f in files[:20]:
                    status_icon = {"added": "+", "modified": "M", "removed": "-"}.get(f.get("status", ""), "?")
                    lines.append(f"  {status_icon} {f.get('filename', '?')} (+{f.get('additions', 0)} -{f.get('deletions', 0)})")
                if len(files) > 20:
                    lines.append(f"  ... and {len(files) - 20} more files")

            # Diff (truncated)
            if diff:
                lines.append(f"\nDiff (truncated):\n```\n{diff}\n```")

            context_str = "\n".join(lines)

            # Cache in metadata
            project.metadata["_github_context"] = context_str
            project.metadata["_github_pr"] = {
                "repo": repo,
                "number": pr_number,
                "url": pr.get("url", ""),
                "checksStatus": pr.get("checksStatus", ""),
                "reviewDecision": pr.get("reviewDecision", ""),
            }
            self.project_manager.save_project(project)

            return context_str

        except Exception as exc:
            self.logger.warning("GitHub context fetch failed: %s", exc)
            return ""

    def _fetch_jira_context(self, project: DevProject) -> str:
        """Extract Jira issue key from project and fetch context."""
        if not self.integrations.get("jira"):
            return ""
        cached = project.metadata.get("_jira_context")
        if cached:
            return cached
        text = f"{project.title} {project.description or ''}"
        try:
            from clawteam.devteam.jira import extract_jira_key, fetch_jira_context_for_project
            jira_key = extract_jira_key(text)
            if not jira_key:
                return ""
            context = fetch_jira_context_for_project(jira_key)
            if context:
                project.metadata["_jira_context"] = context
                self.project_manager.save_project(project)
            return context
        except Exception as exc:
            self.logger.debug("Jira context fetch failed: %s", exc)
            return ""

    def _fetch_datadog_context(self, project: DevProject) -> str:
        """Extract Datadog query from project and fetch log context."""
        if not self.integrations.get("datadog"):
            return ""
        cached = project.metadata.get("_datadog_context")
        if cached:
            return cached
        # Only fetch for log_analysis projects
        if project.project_type.value != "log_analysis":
            return ""
        import re
        text = f"{project.title} {project.description or ''}"
        service_match = re.search(r"service[:\s]+([a-z0-9_-]+)", text.lower())
        service = service_match.group(1) if service_match else ""
        try:
            from clawteam.devteam.datadog import fetch_datadog_context_for_project
            query = service or "*"
            context = fetch_datadog_context_for_project(query, service=service)
            if context:
                project.metadata["_datadog_context"] = context
                self.project_manager.save_project(project)
            return context
        except Exception as exc:
            self.logger.debug("Datadog context fetch failed: %s", exc)
            return ""

    def _infer_project_type(self, text: str) -> ProjectType:
        lowered = text.lower()
        # PR / code review detection
        if any(kw in lowered for kw in ("pr ", "pull request", "코드 리뷰", "code review", "github.com/", "/pull/")):
            return ProjectType.code_review
        # Datadog / log analysis detection
        if any(kw in lowered for kw in ("datadog", "dd-", "로그 분석", "log analysis", "app.datadoghq.com")):
            return ProjectType.log_analysis
        # E2E test detection
        if any(kw in lowered for kw in ("e2e", "end-to-end", "통합 테스트", "integration test")):
            return ProjectType.e2e_test
        # Existing type detection
        if any(kw in lowered for kw in ("bug", "fix", "error", "버그")):
            return ProjectType.bugfix
        if any(kw in lowered for kw in ("refactor", "improve", "cleanup", "리팩토링")):
            return ProjectType.refactor
        if any(kw in lowered for kw in ("spike", "research", "poc", "조사", "리서치")):
            return ProjectType.spike
        return ProjectType.feature

    def _refresh_projects_for_startup(self) -> None:
        for project in self.project_manager.list_projects():
            if project.status != ProjectStatus.open:
                continue
            refreshed = self.autonomy.refresh_project_session(project)
            self.project_manager.save_project(refreshed)

    def _touch_heartbeat(self) -> None:
        self.state.last_heartbeat_at = self.now_fn().isoformat()
        company = self.events.get_company_state()
        company.last_heartbeat_at = self.state.last_heartbeat_at
        company.runtime_status = self.state.mode or company.runtime_status
        company.ui_status = "online"
        company.scheduler_status = "online"
        company.active_sessions = len([
            session for session in self.events.list_sessions(limit=200)
            if session.ended_at == ""
        ])
        self.events.save_company_state(company)

    # -- Schedule -----------------------------------------------------------

    def _run_due_schedules(self) -> list[str]:
        due = self.scheduler.due_schedules(
            self.runtime.blueprint.schedules, self.now_fn()
        )
        ran: list[str] = []
        for due_schedule in due:
            self._dispatch_protocol(
                due_schedule.key,
                reason="schedule",
                receipt_key=f"{due_schedule.key}:{due_schedule.slot_key}",
            )
            self.scheduler.mark_run(due_schedule)
            ran.append(due_schedule.key)
        dynamic_jobs = self.control.list_jobs()
        dynamic_due = self.scheduler.due_schedules(
            [
                ScheduleSpec(
                    key=job.key,
                    cadence=job.cadence,
                    owner=job.owner,
                    description=job.title,
                    channels=job.channels,
                )
                for job in dynamic_jobs
                if job.enabled
            ],
            self.now_fn(),
        )
        for due_job in dynamic_due:
            job = self.control.get_job(due_job.key)
            if job is None:
                continue
            self._dispatch_dynamic_job(job)
            self.scheduler.mark_run(due_job)
            self.control.mark_job_run(job.key, self.now_fn().isoformat())
            ran.append(job.key)
        return ran

    def _safe_run_due_schedules(self) -> list[str]:
        try:
            return self._run_due_schedules()
        except Exception as exc:
            self._record_runtime_error(exc)
            return []

    def _dispatch_protocol(
        self, protocol_key: str, reason: str, receipt_key: str = ""
    ) -> None:
        protocol = self.runtime.blueprint.protocols.get(protocol_key)
        if protocol is None:
            return
        self.logger.info("dispatch protocol=%s reason=%s", protocol_key, reason)

        # For standup/sprint_review: generate LLM-powered status summary
        if protocol_key in ("standup", "sprint_review"):
            text = self._generate_protocol_summary(protocol_key, protocol)
        else:
            lines = [
                f"*{protocol.title}*",
                f"Owner: {protocol.owner}",
                f"Reason: {reason}",
                "Steps:",
            ]
            lines.extend(
                f"{idx}. {step}"
                for idx, step in enumerate(protocol.steps, start=1)
            )
            text = "\n".join(lines)

        channels = protocol.channels or ["dev-ops"]
        self.state.last_protocol_runs[protocol_key] = self.now_fn().isoformat()
        self.control.record_activity(
            kind=DevActivityKind.schedule,
            title=protocol.title,
            body=text,
            author=protocol.owner,
            participants=[protocol.owner],
            metadata={"protocol": protocol_key, "reason": reason, "channels": channels},
        )

    def _generate_protocol_summary(self, protocol_key: str, protocol) -> str:
        """Generate LLM-powered standup / sprint review summary."""
        projects = self.project_manager.list_projects()
        open_projects = [p for p in projects if p.status == ProjectStatus.open]
        completed = [p for p in projects if p.status == ProjectStatus.completed]

        project_lines = []
        for p in open_projects:
            owner = self._workflow_for(p).stage_owner(p.stage)
            persona = self.autonomy.registry.get(owner)
            owner_name = persona.display_name if persona else owner
            project_lines.append(f"- {p.title} [{p.stage.value}] 담당: {owner_name}")

        if completed:
            project_lines.append(f"\n최근 완료: {len(completed)}건")
            for p in completed[-3:]:
                project_lines.append(f"- {p.title} (완료)")

        project_summary = "\n".join(project_lines) if project_lines else "진행 중인 프로젝트 없음"

        is_standup = protocol_key == "standup"
        system_prompt = (
            "너는 AI 개발회사의 '서준 (CoS)'이다.\n"
            f"{'매일 아침 스탠드업' if is_standup else '주간 스프린트 리뷰'}을 진행한다.\n"
            "규칙: 한국어, 반말 업무체, 3~6문장, 마크다운/이모지 금지, 순수 텍스트만.\n"
        )
        user_prompt = (
            f"현재 프로젝트 현황:\n{project_summary}\n\n"
            f"{'오늘의 스탠드업 요약을 작성하라. 각 프로젝트 진행상황, 블로커, 오늘 우선순위를 정리.' if is_standup else '이번 주 스프린트 리뷰를 작성하라. 완료된 작업, 진행 중인 작업, 다음 주 우선순위를 정리.'}"
        )

        try:
            from clawteam.devteam.llm import chat
            result = chat(system_prompt, user_prompt, max_tokens=400)
            if result and result.strip():
                return result.strip()
        except Exception as exc:
            self.logger.warning("protocol LLM summary failed: %s", exc)

        # Fallback
        return f"[{protocol.title}]\n{project_summary}"

    def _dispatch_dynamic_job(self, job) -> None:
        text = (
            f"*{job.title}*\n"
            f"Owner: {job.owner}\n"
            f"Cadence: {job.cadence}\n"
            f"Instruction: {job.instruction}"
        )
        self.mailbox.send(
            from_agent="scheduler",
            to=job.owner,
            content=job.instruction,
            request_id=f"schedule-{job.key}",
        )
        self.control.record_activity(
            kind=DevActivityKind.schedule,
            title=job.title,
            body=job.instruction,
            author="scheduler",
            participants=[job.owner],
            metadata={"job_key": job.key, "cadence": job.cadence},
        )

    # -- Error handling -----------------------------------------------------

    def _record_runtime_error(self, exc: Exception) -> None:
        self.logger.error("runtime error: %s", exc)
        self.state = load_runtime_state(self.team_name)
        errors = list(self.state.metadata.get("runtime_errors", []))
        errors.append({"at": self.now_fn().isoformat(), "error": str(exc)})
        self.state.metadata["runtime_errors"] = errors[-50:]
        save_runtime_state(self.state)
        company = self.events.get_company_state()
        company.status = DevCompanyStatus.degraded
        company.errors = errors[-20:]
        company.last_heartbeat_at = self.now_fn().isoformat()
        self.events.save_company_state(company)
        self.control.record_activity(
            kind=DevActivityKind.error,
            title="Runtime error",
            body=str(exc),
            author="runtime",
        )

    # -- Logger / timezone --------------------------------------------------

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger(
            f"clawteam.devteam.runtime.{self.team_name}"
        )
        if logger.handlers:
            return logger
        logger.setLevel(logging.INFO)
        logger.propagate = False
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)
        return logger

    def _build_now_fn(self):
        tz_name = os.environ.get("CLAWTEAM_RUNTIME_TZ", "").strip()
        try:
            tz = ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo
        except Exception as exc:
            raise DevTeamRuntimeError(
                f"Invalid CLAWTEAM_RUNTIME_TZ '{tz_name}'. "
                f"Use an IANA timezone like 'Asia/Seoul'."
            ) from exc
        return lambda: datetime.now(tz)

    def _acquire_runtime_lock(self) -> None:
        if self._runtime_lock is not None:
            return
        lock_path = devteam_dir(self.team_name) / ".runtime.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise DevTeamRuntimeError(
                f"Dev team runtime for '{self.team_name}' is already running"
            ) from exc
        self._runtime_lock = lock_file
