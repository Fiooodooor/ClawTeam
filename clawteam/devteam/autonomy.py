"""Stage-driven autonomous conversation engine for dev team projects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from clawteam.devteam.models import DevProject, PersonaSpec, SprintStage
from clawteam.devteam.workflow import SprintWorkflow


@dataclass(frozen=True)
class DevPersonaIdentity:
    agent: str
    display_name: str
    role: str
    style: str
    channels: tuple[str, ...]
    icon_emoji: str
    responsibilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DevConversationIntent:
    agent: str
    priority: float
    action: str
    text: str
    mention_targets: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Persona registry (dev-team icons)
# ---------------------------------------------------------------------------


class DevPersonaRegistry:
    """Maps agent names to persona identities."""

    def __init__(self, personas: list[PersonaSpec]):
        self._by_agent: dict[str, DevPersonaIdentity] = {
            p.agent: DevPersonaIdentity(
                agent=p.agent,
                display_name=p.display_name or p.agent,
                role=p.role,
                style=p.style,
                channels=tuple(p.channels),
                icon_emoji=self._icon_for(p),
                responsibilities=tuple(p.responsibilities),
            )
            for p in personas
        }

    def get(self, agent: str) -> DevPersonaIdentity | None:
        return self._by_agent.get(agent)

    def list_agents(self) -> list[str]:
        return list(self._by_agent)

    def resolve_mentions(self, text: str) -> list[str]:
        lowered = text.lower()
        matches: list[str] = []
        for agent, persona in self._by_agent.items():
            tokens = {f"@{agent.lower()}", f"@{persona.display_name.lower()}"}
            if any(tok in lowered for tok in tokens):
                matches.append(agent)
        return matches

    def tag(self, agent: str) -> str:
        persona = self.get(agent)
        return f"@{persona.display_name}" if persona else f"@{agent}"

    @staticmethod
    def _icon_for(persona: PersonaSpec) -> str:
        role = persona.role.lower()
        if "chief" in role or "staff" in role:
            return ":office:"
        if "cto" in role or "architect" in role:
            return ":brain:"
        if "lead" in role and "engineer" in role:
            return ":hammer_and_wrench:"
        if "design" in role:
            return ":art:"
        if "qa" in role or "test" in role:
            return ":mag:"
        if "security" in role:
            return ":shield:"
        if "devops" in role or "infra" in role:
            return ":rocket:"
        if "writer" in role or "doc" in role:
            return ":memo:"
        return ":robot_face:"


# ---------------------------------------------------------------------------
# Conversation engine
# ---------------------------------------------------------------------------


class DevConversationEngine:
    """Determines who should speak next based on sprint stage."""

    def __init__(
        self,
        personas: list[PersonaSpec],
        workflow: SprintWorkflow,
        now_fn: Callable[[], datetime],
    ):
        self.registry = DevPersonaRegistry(personas)
        self._default_workflow = workflow
        self.now_fn = now_fn

    def _workflow_for(self, project: DevProject) -> SprintWorkflow:
        """Resolve workflow per project type, falling back to default."""
        return SprintWorkflow.for_project_type(project.project_type.value)

    # -- Public API ---------------------------------------------------------

    def note_human_message(
        self, project: DevProject, text: str, message_ts: str
    ) -> DevProject:
        state = self._state(project)
        mentions = self.registry.resolve_mentions(text)
        if mentions:
            pending = set(state.get("pending_mentions", []))
            pending.update(mentions)
            state["pending_mentions"] = sorted(pending)
        state["human_waiting"] = True
        state["last_human_message_ts"] = message_ts
        state["last_human_message_text"] = text
        # Check for stage advance commands
        lowered = text.lower().strip()
        if any(
            cmd in lowered
            for cmd in ("승인", "approve", "다음 단계", "next stage", "진행")
        ):
            state["human_approved"] = True
        project.metadata["autonomy"] = state
        return project

    def plan_turns(
        self,
        project: DevProject,
        channel_name: str,
        trigger: str,
    ) -> list[DevConversationIntent]:
        state = self._state(project)
        if self._should_pause(project, trigger, state):
            return []

        candidates = self._candidate_agents(project, channel_name, state)
        intents = [
            intent
            for agent in candidates
            if (intent := self._build_intent(project, channel_name, trigger, agent, state))
            is not None
        ]
        if not intents:
            return []

        intents.sort(key=lambda i: i.priority, reverse=True)
        max_turns = 2 if trigger in {"startup", "human_message"} else 1
        selected: list[DevConversationIntent] = []
        seen: set[str] = set()
        for intent in intents:
            if intent.priority < 25:
                continue
            if intent.agent in seen:
                continue
            selected.append(intent)
            seen.add(intent.agent)
            if len(selected) >= max_turns:
                break
        return selected

    def record_turn(
        self, project: DevProject, intent: DevConversationIntent, message_ts: str
    ) -> DevProject:
        state = self._state(project)
        ledger = list(state.get("ledger", []))
        ledger.append(
            {
                "agent": intent.agent,
                "action": intent.action,
                "ts": message_ts,
                "at": self.now_fn().isoformat(),
                "mentions": list(intent.mention_targets),
                "stage": project.stage.value,
                "text": (intent.text or "")[:500],
            }
        )
        posted = set(state.get("posted_agents", []))
        posted.add(intent.agent)
        pending = set(state.get("pending_mentions", []))
        pending.discard(intent.agent)
        pending.update(t for t in intent.mention_targets if t != intent.agent)

        agent_state = dict(state.get("agent_state", {}))
        agent_state[intent.agent] = {
            "last_action": intent.action,
            "last_message_ts": message_ts,
            "last_posted_at": self.now_fn().isoformat(),
        }

        state["human_waiting"] = False
        state["last_agent"] = intent.agent
        state["last_turn_at"] = self.now_fn().isoformat()
        state["pending_mentions"] = sorted(pending)
        state["posted_agents"] = sorted(posted)
        state["agent_state"] = agent_state
        state["ledger"] = ledger[-50:]
        project.metadata["autonomy"] = state
        return project

    def is_stage_conversation_done(self, project: DevProject) -> bool:
        """Return True if all stage participants have posted at least once.

        This is used by the runtime to decide when to auto-advance
        stages that have ``auto_advance=True``.
        """
        state = self._state(project)
        posted = set(state.get("posted_agents", []))
        if not posted:
            return False
        wf = self._workflow_for(project)
        participants = set(wf.stage_participants(project.stage))
        # Stage is done when the primary owner has posted at minimum
        owner = wf.stage_owner(project.stage)
        return owner in posted and participants <= (posted | {owner})

    def refresh_project_session(self, project: DevProject) -> DevProject:
        state = self._state(project)
        last_turn_at = str(state.get("last_turn_at", ""))
        if not last_turn_at:
            return project
        try:
            last_turn = datetime.fromisoformat(last_turn_at)
        except ValueError:
            return project
        now = self.now_fn()
        if last_turn.date() == now.date() and now - last_turn < timedelta(hours=6):
            return project
        project.metadata["autonomy"] = {
            "pending_mentions": [],
            "posted_agents": [],
            "agent_state": {},
            "ledger": [],
            "human_waiting": False,
            "human_approved": False,
            "session_reset_at": now.isoformat(),
        }
        return project

    # -- Candidate selection ------------------------------------------------

    def _candidate_agents(
        self, project: DevProject, channel_name: str, state: dict[str, Any]
    ) -> list[str]:
        candidates: list[str] = []
        wf = self._workflow_for(project)
        stage_participants = set(wf.stage_participants(project.stage))
        pending = state.get("pending_mentions", [])

        for agent in self.registry.list_agents():
            persona = self.registry.get(agent)
            if persona is None:
                continue
            if (
                agent in stage_participants
                or agent in pending
                or agent in project.assigned_agents
                or channel_name in persona.channels
            ):
                candidates.append(agent)
        return candidates

    def _build_intent(
        self,
        project: DevProject,
        channel_name: str,
        trigger: str,
        agent: str,
        state: dict[str, Any],
    ) -> DevConversationIntent | None:
        persona = self.registry.get(agent)
        if persona is None:
            return None

        score = 0.0
        wf = self._workflow_for(project)
        stage_owner = wf.stage_owner(project.stage)
        stage_participants = set(wf.stage_participants(project.stage))
        mentioned = agent in state.get("pending_mentions", [])

        # Stage-based scoring
        if agent == stage_owner:
            score += 40
        elif agent in stage_participants:
            score += 20

        # Mention scoring
        if mentioned:
            score += 60
            if trigger == "human_message":
                score += 40

        # Channel match
        if channel_name in persona.channels:
            score += 10

        # Assigned agent bonus
        if agent in project.assigned_agents:
            score += 15

        # First turn bonus for stage owner
        if not state.get("posted_agents") and agent == stage_owner:
            score += 25

        # Penalties
        if agent == state.get("last_agent") and not (mentioned and trigger == "human_message"):
            score -= 35

        if agent in state.get("posted_agents", []) and not mentioned:
            score -= 25

        if self._recently_posted(state, agent) and not (mentioned and trigger == "human_message"):
            score -= 40

        # Loop trigger: skip already posted non-owners
        if (
            trigger == "loop"
            and agent in state.get("posted_agents", [])
            and agent != stage_owner
            and not mentioned
        ):
            return None

        if score < 20:
            return None

        action = self._action_for(project, agent)
        mention_targets = self._mention_targets(project, agent, state)
        text = self._compose_message(project, agent, action, mention_targets, state)

        return DevConversationIntent(
            agent=agent,
            priority=score,
            action=action,
            text=text,
            mention_targets=tuple(mention_targets),
        )

    # -- Action resolution --------------------------------------------------

    def _action_for(self, project: DevProject, agent: str) -> str:
        stage = project.stage
        owner = self._workflow_for(project).stage_owner(stage)

        if agent == "chief-of-staff":
            if stage == SprintStage.intake:
                return "triage"
            if stage == SprintStage.reflect:
                return "retrospective"
            return "coordinate"

        if agent == "cto":
            if stage in (SprintStage.think, SprintStage.plan):
                return "architecture"
            if stage == SprintStage.review:
                return "code_review"
            return "advise"

        if agent == "lead-engineer":
            if stage == SprintStage.build:
                return "implement"
            if stage == SprintStage.think:
                return "feasibility"
            return "support"

        if agent == "designer":
            return "design_review"

        if agent == "qa-lead":
            return "test_plan" if stage == SprintStage.test else "qa_review"

        if agent == "security-officer":
            return "security_audit" if stage == SprintStage.security else "security_review"

        if agent == "devops":
            return "deploy" if stage == SprintStage.ship else "infra_review"

        if agent == "tech-writer":
            return "documentation"

        return "contribute"

    # -- Message composition (LLM-powered) ------------------------------------

    def _compose_message(
        self,
        project: DevProject,
        agent: str,
        action: str,
        mention_targets: list[str],
        state: dict[str, Any],
    ) -> str:
        mention_prefix = " ".join(self.registry.tag(t) for t in mention_targets)

        # Try LLM generation first
        llm_text = self._compose_via_llm(project, agent, action, mention_targets, state)
        if llm_text:
            if mention_prefix and mention_prefix not in llm_text:
                llm_text = f"{llm_text} {mention_prefix}"
            return llm_text.strip()

        # Fallback to template if LLM is unavailable
        return self._compose_template_fallback(
            project, agent, action, mention_targets, state
        )

    def _compose_via_llm(
        self,
        project: DevProject,
        agent: str,
        action: str,
        mention_targets: list[str],
        state: dict[str, Any],
    ) -> str:
        from clawteam.devteam.llm import chat

        persona = self.registry.get(agent)
        if persona is None:
            return ""

        # Build conversation history context
        recent_ledger = state.get("ledger", [])[-6:]
        history_lines = []
        for entry in recent_ledger:
            speaker = entry.get("agent", "?")
            speaker_persona = self.registry.get(speaker)
            speaker_name = speaker_persona.display_name if speaker_persona else speaker
            history_lines.append(f"- {speaker_name} ({speaker}): [{entry.get('action', '?')}]")
        history_context = "\n".join(history_lines) if history_lines else "(첫 발언)"

        # CEO's instruction if any
        human_instruction = ""
        if state.get("human_waiting") and state.get("last_human_message_text"):
            human_instruction = f"\n\nCEO 지시사항: {state['last_human_message_text']}"

        # Mention context
        mention_names = []
        for t in mention_targets:
            p = self.registry.get(t)
            mention_names.append(f"@{p.display_name} ({t})" if p else f"@{t}")
        mention_note = f"\n다음 사람에게 넘길 것: {', '.join(mention_names)}" if mention_names else ""

        system_prompt = (
            f"너는 AI 개발회사의 '{persona.display_name}' ({persona.role})이다.\n"
            f"말투: {persona.style}\n"
            f"담당: {', '.join(persona.responsibilities)}\n\n"
            f"규칙:\n"
            f"- 한국어로 말한다. 반말 업무체로 간결하게. ('~한다', '~하겠다', '~이다')\n"
            f"- 너의 역할과 전문성에 맞는 실질적인 의견/분석/판단을 제시한다.\n"
            f"- 프로젝트 내용을 실제로 이해하고 구체적으로 말한다. 뻔한 소리 금지.\n"
            f"- 2~4문장. 길게 쓰지 않는다.\n"
            f"- 마크다운 금지. 이모지 금지. 순수 텍스트만."
        )

        # Inject GitHub PR context if available
        gh_context = ""
        gh_data = project.metadata.get("_github_context", "")
        if gh_data:
            # Truncate for conversation LLM (keep first 2000 chars to stay within token budget)
            gh_context = f"\n\nGitHub PR 정보:\n{gh_data[:2000]}"

        user_prompt = (
            f"프로젝트: {project.title}\n"
            f"설명: {project.description or '(없음)'}\n"
            f"유형: {project.project_type.value}\n"
            f"현재 스테이지: {project.stage.value}\n"
            f"너의 액션: {action}\n\n"
            f"지금까지 대화:\n{history_context}"
            f"{gh_context}"
            f"{human_instruction}"
            f"{mention_note}\n\n"
            f"위 맥락에서 '{persona.display_name}'로서 발언하라."
        )

        return chat(system=system_prompt, user=user_prompt, max_tokens=300)

    def _compose_template_fallback(
        self,
        project: DevProject,
        agent: str,
        action: str,
        mention_targets: list[str],
        state: dict[str, Any],
    ) -> str:
        """Rule-based Korean template — used when LLM is unavailable."""
        stage = project.stage
        title = project.title
        mention_prefix = " ".join(self.registry.tag(t) for t in mention_targets)
        lead = self._lead_context(state)
        focus = self._focus_context(state)
        desc_hint = f" ({project.description[:80]})" if project.description else ""

        if agent == "chief-of-staff":
            if action == "triage":
                return (
                    f"{lead} `{title}` 접수 완료. 프로젝트 유형은 {project.project_type.value}로 분류한다.{desc_hint} "
                    f"지금부터 sprint workflow에 따라 진행하겠다. 먼저 CTO의 아키텍처 검토가 필요하다. "
                    f"{focus} {mention_prefix}".strip()
                )
            if action == "retrospective":
                return (
                    f"{lead} `{title}` 프로젝트 회고를 시작한다. "
                    f"전체 sprint를 돌아보며 잘된 점, 개선할 점, 다음에 적용할 교훈을 정리하겠다. "
                    f"{focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` 현재 {stage.value} 단계다. 진행 상황 확인하고 조율하겠다. "
                f"{focus} {mention_prefix}".strip()
            )

        if agent == "cto":
            if action == "architecture":
                return (
                    f"{lead} `{title}` 아키텍처 검토 들어간다.{desc_hint} "
                    f"시스템 설계, 기술 스택, 확장성 관점에서 분석하겠다. "
                    f"구현 전에 설계가 확정돼야 한다. {focus} {mention_prefix}".strip()
                )
            if action == "code_review":
                return (
                    f"{lead} `{title}` 코드 리뷰 시작한다. "
                    f"코드 품질, 아키텍처 일관성, 엣지 케이스 위주로 보겠다. "
                    f"{focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` 기술적 관점에서 의견 드린다. {focus} {mention_prefix}".strip()
            )

        if agent == "lead-engineer":
            if action == "implement":
                return (
                    f"{lead} `{title}` 구현 착수한다. "
                    f"CTO의 설계안을 기반으로 코드 작성에 들어간다. "
                    f"진행 상황은 실시간으로 공유하겠다. {focus} {mention_prefix}".strip()
                )
            if action == "feasibility":
                return (
                    f"{lead} `{title}` 구현 타당성 검토한다. "
                    f"기술적 난이도, 예상 작업량, 잠재적 리스크를 정리하겠다. "
                    f"{focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` 엔지니어링 관점에서 서포트한다. {focus} {mention_prefix}".strip()
            )

        if agent == "designer":
            return (
                f"{lead} `{title}` 디자인 리뷰한다. "
                f"UI/UX 관점에서 사용성, 접근성, 컴포넌트 구조를 확인하겠다. "
                f"{focus} {mention_prefix}".strip()
            )

        if agent == "qa-lead":
            if action == "test_plan":
                return (
                    f"{lead} `{title}` 테스트 계획 수립한다. "
                    f"단위 테스트, 통합 테스트, 엣지 케이스 커버리지를 확인하겠다. "
                    f"테스트 통과 전까지는 다음 단계로 넘어가지 않는다. {focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` QA 관점에서 검토한다. {focus} {mention_prefix}".strip()
            )

        if agent == "security-officer":
            if action == "security_audit":
                return (
                    f"{lead} `{title}` 보안 감사 시작한다. "
                    f"OWASP Top 10, 인증/인가, 입력 검증, 시크릿 관리 위주로 체크하겠다. "
                    f"보안 이슈 발견 시 즉시 블록한다. {focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` 보안 관점에서 확인한다. {focus} {mention_prefix}".strip()
            )

        if agent == "devops":
            if action == "deploy":
                return (
                    f"{lead} `{title}` 배포 준비한다. "
                    f"CI/CD 파이프라인 확인하고 스테이징/프로덕션 배포 계획을 잡겠다. "
                    f"{focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} `{title}` 인프라 관점에서 확인한다. {focus} {mention_prefix}".strip()
            )

        if agent == "tech-writer":
            return (
                f"{lead} `{title}` 문서화 작업 시작한다. "
                f"API 문서, README 업데이트, 변경 사항 정리를 진행하겠다. "
                f"{focus} {mention_prefix}".strip()
            )

        return f"{lead} `{title}` 확인 중이다. {focus} {mention_prefix}".strip()

    # -- Mention targets ----------------------------------------------------

    def _mention_targets(
        self, project: DevProject, agent: str, state: dict[str, Any]
    ) -> list[str]:
        pending = set(state.get("pending_mentions", []))
        posted = set(state.get("posted_agents", []))

        # If there are pending mentions, route to them
        if pending and agent not in pending:
            return [t for t in sorted(pending) if not self._recently_posted(state, t)][:2]

        # Stage-based mention routing
        stage = project.stage
        if agent == "chief-of-staff" and stage == SprintStage.intake:
            return ["cto"] if self.registry.get("cto") and "cto" not in posted else []

        if agent == "cto" and stage in (SprintStage.think, SprintStage.plan):
            targets = ["lead-engineer"]
            if stage == SprintStage.plan and self.registry.get("designer"):
                targets.append("designer")
            return [t for t in targets if self.registry.get(t) and t not in posted][:2]

        if agent == "cto" and stage == SprintStage.review:
            return (
                ["security-officer"]
                if self.registry.get("security-officer") and "security-officer" not in posted
                else []
            )

        if agent == "lead-engineer" and stage == SprintStage.build:
            return (
                ["cto"]
                if self.registry.get("cto") and "cto" not in posted
                else []
            )

        if agent == "qa-lead" and stage == SprintStage.test:
            return (
                ["lead-engineer"]
                if self.registry.get("lead-engineer") and "lead-engineer" not in posted
                else []
            )

        if agent == "security-officer" and stage == SprintStage.security:
            return (
                ["cto"]
                if self.registry.get("cto") and "cto" not in posted
                else []
            )

        if agent == "devops" and stage == SprintStage.ship:
            return (
                ["tech-writer"]
                if self.registry.get("tech-writer") and "tech-writer" not in posted
                else []
            )

        return []

    # -- Helpers ------------------------------------------------------------

    def _lead_context(self, state: dict[str, Any]) -> str:
        last_agent = str(state.get("last_agent", "")).strip()
        if not last_agent:
            return ""
        previous = self.registry.get(last_agent)
        if previous is None:
            return ""
        if state.get("last_human_message_text") and state.get("human_waiting"):
            return "Human 지시 확인했다."
        return f"{self.registry.tag(last_agent)} 이어서 보겠다."

    def _focus_context(self, state: dict[str, Any]) -> str:
        if not state.get("human_waiting"):
            return ""
        human_text = str(state.get("last_human_message_text", "")).strip()
        if not human_text:
            return ""
        normalized = " ".join(human_text.split())
        if len(normalized) > 120:
            normalized = normalized[:117].rstrip() + "..."
        return f"방금 지시사항: `{normalized}`"

    def _recently_posted(self, state: dict[str, Any], agent: str) -> bool:
        agent_state = dict(state.get("agent_state", {})).get(agent, {})
        last_posted_at = str(agent_state.get("last_posted_at", ""))
        if not last_posted_at:
            return False
        try:
            last_posted = datetime.fromisoformat(last_posted_at)
        except ValueError:
            return False
        return self.now_fn() - last_posted < timedelta(minutes=10)

    def _state(self, project: DevProject) -> dict[str, Any]:
        state = dict(project.metadata.get("autonomy", {}))
        state.setdefault("pending_mentions", [])
        state.setdefault("posted_agents", [])
        state.setdefault("agent_state", {})
        state.setdefault("ledger", [])
        state.setdefault("human_waiting", False)
        state.setdefault("human_approved", False)
        return state

    def _should_pause(
        self, project: DevProject, trigger: str, state: dict[str, Any]
    ) -> bool:
        if trigger in {"startup", "human_message"}:
            return False
        if state.get("human_waiting") or state.get("pending_mentions"):
            return False
        # Pause if enough agents have posted in this stage
        stage_posts = [
            entry
            for entry in state.get("ledger", [])
            if entry.get("stage") == project.stage.value
        ]
        if len(stage_posts) >= 4:
            return True
        return False
