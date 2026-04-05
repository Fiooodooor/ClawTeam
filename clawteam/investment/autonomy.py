"""Autonomous multi-persona conversation engine for investment cases."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from clawteam.investment.cases import InvestmentCase
from clawteam.investment.models import PersonaSpec


@dataclass(frozen=True)
class PersonaIdentity:
    agent: str
    display_name: str
    role: str
    style: str
    slack_channels: tuple[str, ...]
    icon_emoji: str


@dataclass(frozen=True)
class ConversationIntent:
    agent: str
    priority: float
    action: str
    text: str
    mention_targets: tuple[str, ...] = ()


class PersonaRegistry:
    """Resolves runtime personas into Slack-facing identities."""

    def __init__(self, personas: list[PersonaSpec]):
        self._by_agent: dict[str, PersonaIdentity] = {
            persona.agent: PersonaIdentity(
                agent=persona.agent,
                display_name=persona.display_name or persona.agent,
                role=persona.role,
                style=persona.style,
                slack_channels=tuple(persona.slack_channels),
                icon_emoji=self._icon_for(persona),
            )
            for persona in personas
        }

    def get(self, agent: str) -> PersonaIdentity | None:
        return self._by_agent.get(agent)

    def list_agents(self) -> list[str]:
        return list(self._by_agent)

    def resolve_mentions(self, text: str) -> list[str]:
        lowered = text.lower()
        matches: list[str] = []
        for agent, persona in self._by_agent.items():
            tokens = {f"@{agent.lower()}", f"@{persona.display_name.lower()}"}
            if any(token in lowered for token in tokens):
                matches.append(agent)
        return matches

    def tag(self, agent: str) -> str:
        persona = self.get(agent)
        return f"@{persona.display_name}" if persona else f"@{agent}"

    def _icon_for(self, persona: PersonaSpec) -> str:
        role = persona.role.lower()
        if "chief" in role:
            return ":office:"
        if "pm" in role:
            return ":spiral_calendar_pad:"
        if "macro" in role:
            return ":globe_with_meridians:"
        if "theme" in role:
            return ":satellite_antenna:"
        if "technical" in role:
            return ":chart_with_upwards_trend:"
        if "risk" in role:
            return ":rotating_light:"
        if "vip" in role:
            return ":briefcase:"
        if "editor" in role:
            return ":memo:"
        if "publisher" in role:
            return ":outbox_tray:"
        return ":robot_face:"


class AutonomousConversationEngine:
    """Determines who should speak next for each investment case."""

    def __init__(self, personas: list[PersonaSpec], now_fn: Callable[[], datetime]):
        self.registry = PersonaRegistry(personas)
        self.now_fn = now_fn

    def note_human_message(
        self, case: InvestmentCase, text: str, message_ts: str
    ) -> InvestmentCase:
        state = self._state(case)
        mentions = self.registry.resolve_mentions(text)
        if mentions:
            pending = set(state.get("pending_mentions", []))
            pending.update(mentions)
            state["pending_mentions"] = sorted(pending)
        state["human_waiting"] = True
        state["last_human_message_ts"] = message_ts
        state["last_human_message_text"] = text
        case.metadata["autonomy"] = state
        return case

    def refresh_case_for_session(self, case: InvestmentCase) -> InvestmentCase:
        state = self._state(case)
        last_turn_at = str(state.get("last_turn_at", ""))
        if not last_turn_at:
            return case
        try:
            last_turn = datetime.fromisoformat(last_turn_at)
        except ValueError:
            return case
        now = self.now_fn()
        reset_hours = self._session_reset_hours(case)
        if last_turn.date() == now.date() and now - last_turn < timedelta(hours=reset_hours):
            return case
        archive = list(case.metadata.get("autonomy_history", []))
        archive.append(
            {
                "reset_at": now.isoformat(),
                "previous_last_turn_at": last_turn_at,
                "previous_posted_agents": list(state.get("posted_agents", [])),
            }
        )
        case.metadata["autonomy_history"] = archive[-20:]
        case.metadata["autonomy"] = {
            "pending_mentions": [],
            "posted_agents": [],
            "agent_state": {},
            "ledger": [],
            "risk_gate": "open",
            "client_plan_ready": False,
            "draft_ready": False,
            "publish_ready": False,
            "published": False,
            "human_waiting": False,
            "session_reset_at": now.isoformat(),
        }
        return case

    def plan_turns(
        self,
        case: InvestmentCase,
        channel_name: str,
        trigger: str,
    ) -> list[ConversationIntent]:
        if not case.thread:
            return []
        state = self._state(case)
        if self._should_pause_case(case, trigger, state):
            return []
        candidates = self._candidate_agents(case, channel_name)
        intents = [
            intent
            for agent in candidates
            if (intent := self._build_intent(case, channel_name, trigger, agent, state)) is not None
        ]
        if not intents:
            return []
        intents.sort(key=lambda item: item.priority, reverse=True)
        selected: list[ConversationIntent] = []
        selected_families: set[str] = set()
        max_turns = 2 if trigger in {"startup", "human_message"} else 1
        for intent in intents:
            if intent.priority < 30:
                continue
            family = self._family(intent.agent)
            if family in selected_families and family != "vip":
                continue
            selected.append(intent)
            selected_families.add(family)
            if len(selected) >= max_turns:
                break
        return selected

    def record_turn(
        self, case: InvestmentCase, intent: ConversationIntent, message_ts: str
    ) -> InvestmentCase:
        state = self._state(case)
        ledger = list(state.get("ledger", []))
        ledger.append(
            {
                "agent": intent.agent,
                "action": intent.action,
                "ts": message_ts,
                "at": self.now_fn().isoformat(),
                "mentions": list(intent.mention_targets),
            }
        )
        posted_agents = set(state.get("posted_agents", []))
        posted_agents.add(intent.agent)
        pending_mentions = set(state.get("pending_mentions", []))
        pending_mentions.discard(intent.agent)
        pending_mentions.update(
            target for target in intent.mention_targets if target != intent.agent
        )
        agent_state = dict(state.get("agent_state", {}))
        agent_state[intent.agent] = {
            "last_action": intent.action,
            "last_message_ts": message_ts,
            "last_posted_at": self.now_fn().isoformat(),
        }
        if intent.action == "risk_block":
            state["risk_gate"] = "blocked"
        elif intent.action == "risk_review":
            state["risk_gate"] = "review"
        elif intent.agent.startswith("vip-") and state.get("risk_gate") == "blocked":
            state["client_plan_ready"] = True
        elif intent.agent == "editor-serin":
            state["draft_ready"] = True
        elif intent.agent == "main" and intent.action in {"coordinate", "escalate"}:
            state["publish_ready"] = True
        elif intent.agent == "publisher-minji":
            state["published"] = True
        state["human_waiting"] = False
        state["last_agent"] = intent.agent
        state["last_turn_at"] = self.now_fn().isoformat()
        state["pending_mentions"] = sorted(pending_mentions)
        state["posted_agents"] = sorted(posted_agents)
        state["agent_state"] = agent_state
        state["ledger"] = ledger[-50:]
        case.metadata["autonomy"] = state
        return case

    def _candidate_agents(self, case: InvestmentCase, channel_name: str) -> list[str]:
        candidates: list[str] = []
        state = self._state(case)
        pending_mentions = state.get("pending_mentions", [])
        workflow_agents = self._workflow_agents(case, state)
        for agent in self.registry.list_agents():
            persona = self.registry.get(agent)
            if persona is None:
                continue
            if (
                agent in case.assigned_agents
                or channel_name in persona.slack_channels
                or agent in pending_mentions
                or agent in self._role_fit_agents(case)
                or agent in workflow_agents
            ):
                candidates.append(agent)
        return candidates

    def _build_intent(
        self,
        case: InvestmentCase,
        channel_name: str,
        trigger: str,
        agent: str,
        state: dict[str, Any],
    ) -> ConversationIntent | None:
        persona = self.registry.get(agent)
        if persona is None:
            return None
        score = 0.0
        mentioned = agent in state.get("pending_mentions", [])
        if agent in case.assigned_agents:
            score += 20
        if channel_name in persona.slack_channels:
            score += 10
        if mentioned:
            score += 60
            if trigger == "human_message":
                score += 40
        if trigger == "startup" and agent in self._role_fit_agents(case):
            score += 10
        if agent == "research-pm" and not state.get("posted_agents"):
            score += 30
        if agent in self._workflow_agents(case, state):
            score += 28
        if agent == state.get("last_agent") and not (mentioned and trigger == "human_message"):
            score -= 35
        if agent in state.get("posted_agents", []) and agent not in state.get(
            "pending_mentions", []
        ):
            score -= 25
        if trigger == "loop" and self._recently_posted(state, agent):
            return None
        if (
            trigger == "loop"
            and agent in state.get("posted_agents", [])
            and agent not in self._workflow_agents(case, state)
            and not mentioned
        ):
            return None
        if self._recently_posted(state, agent) and not (mentioned and trigger == "human_message"):
            score -= 40
        score += self._fit_score(case, agent)
        if score < 20:
            return None
        action = self._action_for(case, agent, state)
        if action == "abstain":
            return None
        mention_targets = self._mention_targets(case, agent, state)
        if agent == "editor-serin" and not self._editor_ready(state):
            return None
        if agent == "publisher-minji" and not state.get("draft_ready"):
            return None
        text = self._compose_message(case, agent, action, mention_targets, state)
        return ConversationIntent(
            agent=agent,
            priority=score,
            action=action,
            text=text,
            mention_targets=tuple(mention_targets),
        )

    def _compose_message(
        self,
        case: InvestmentCase,
        agent: str,
        action: str,
        mention_targets: list[str],
        state: dict[str, Any],
    ) -> str:
        questions = case.open_questions[:3]
        joined_questions = "; ".join(questions) if questions else "핵심 질문은 실행 조건 정리다."
        mention_prefix = " ".join(self.registry.tag(target) for target in mention_targets)
        lead = self._lead_context(case, action, state)
        focus = self._focus_context(state)
        if agent == "research-pm":
            owners = ", ".join(
                self.registry.tag(item) for item in self._mention_targets(case, agent, state)
            )
            owners = owners or ", ".join(case.assigned_agents[:2])
            return (
                f"{lead} `{case.case_id}` triage 기준으로 지금 핵심은 `{case.title}`를 decision-ready 상태로 압축하는 것이다. "
                f"Open questions: {joined_questions}. {focus} {owners} 우선 커버 부탁한다."
            )
        if agent == "macro-minho":
            return (
                f"{lead} Macro frame 먼저 잡겠다. `{case.title}`는 regime 확인 없이 결론 내리기 어렵다. "
                f"내 기준 핵심 체크포인트는 {joined_questions}. {focus} {mention_prefix}".strip()
            )
        if agent == "theme-harin":
            return (
                f"{lead} Narrative side에서 보면 `{case.title}`는 아직 winner/loser 압축이 덜 됐다. "
                f"지금은 {joined_questions} 축으로 narrative를 좁히는 게 우선이다. {focus} {mention_prefix}".strip()
            )
        if agent == "technical-yujin":
            return (
                f"{lead} Technical view: 자리 확인 전에는 추격 금지다. `{case.title}` 관련해서 buy-now / wait / wrong 레벨을 먼저 잠그겠다. "
                f"현재 미정인 축은 {joined_questions}. {focus} {mention_prefix}".strip()
            )
        if agent == "risk-jaehyun":
            if action == "risk_review":
                return (
                    f"{lead} 아직 outright block까지는 아니다. 다만 `{case.title}`는 downside, sizing, account fit이 숫자로 정리돼야 다음 단계로 넘길 수 있다. "
                    f"남은 체크는 {joined_questions}. {focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} Risk gate 걸어둔다. `{case.title}`는 downside, sizing, account fit 정리 전까지 execution 전진 금지다. "
                f"특히 {joined_questions} 해소 전에는 보수적으로 본다. {focus} {mention_prefix}".strip()
            )
        if agent.startswith("vip-"):
            client_name = case.client_id or case.title.split()[0]
            return (
                f"{lead} Client frame for `{client_name}`: 바로 주문으로 점프하지 않고 오늘 할 일과 기다릴 일을 분리하겠다. "
                f"현재 고객 메모 기준 핵심은 {joined_questions}. {focus} {mention_prefix}".strip()
            )
        if agent == "main":
            if action == "escalate":
                return (
                    f"{lead} Escalation only. `{case.title}`는 desk 의견이 충분히 올라와서 이제 decision rule을 잠그면 된다. "
                    f"남은 일은 {joined_questions} 정리와 signoff 순서 확인이다. {focus} {mention_prefix}".strip()
                )
            return (
                f"{lead} Coordination note: `{case.title}`는 필요한 desk만 더 움직인다. "
                f"지금 우선순위는 {joined_questions} 정리 후 decision path를 잠그는 것이다. {focus} {mention_prefix}".strip()
            )
        if agent == "editor-serin":
            return (
                f"{lead} Editorial note: 지금 thread에서 conclusion/why/action 구조가 보이기 시작했다. "
                f"결론 문장만 확정되면 memo 형태로 바로 정리 가능하다. {focus} {mention_prefix}".strip()
            )
        if agent == "publisher-minji":
            return (
                f"{lead} Publication hold 상태로 본다. 승인된 결론과 대상 채널이 확정되면 archive까지 같이 닫겠다. "
                f"{focus} {mention_prefix}".strip()
            )
        return f"{lead} `{case.title}` 확인 중이다. {joined_questions}. {focus} {mention_prefix}".strip()

    def _fit_score(self, case: InvestmentCase, agent: str) -> float:
        fits = self._role_fit_agents(case)
        if agent in fits:
            return 35
        if agent == "main":
            return 8
        if agent == "editor-serin":
            return 6
        if agent == "publisher-minji":
            return 4
        return 0

    def _role_fit_agents(self, case: InvestmentCase) -> set[str]:
        mapping = {
            "market": {"research-pm", "macro-minho", "risk-jaehyun", "theme-harin"},
            "theme": {"research-pm", "theme-harin", "risk-jaehyun"},
            "technical": {"research-pm", "technical-yujin", "risk-jaehyun"},
            "flow": {"research-pm", "theme-harin", "technical-yujin", "risk-jaehyun"},
            "ownership": {"research-pm", "main", "risk-jaehyun"},
            "single_name": {"research-pm", "theme-harin", "technical-yujin", "risk-jaehyun"},
            "risk": {"risk-jaehyun", "main"},
            "vip": {
                "research-pm",
                "risk-jaehyun",
                f"vip-{case.client_id}-arin",
                f"vip-{case.client_id}-junho",
            },
            "intake": {"research-pm", "main"},
        }
        return {
            agent
            for agent in mapping.get(case.case_type, {"research-pm"})
            if self.registry.get(agent)
        }

    def _family(self, agent: str) -> str:
        if agent.startswith("vip-"):
            return "vip"
        return agent.split("-", 1)[0]

    def _action_for(self, case: InvestmentCase, agent: str, state: dict[str, Any]) -> str:
        if agent == "risk-jaehyun" and case.case_type in {
            "vip",
            "single_name",
            "technical",
            "market",
        }:
            substantive_agents = {
                item.get("agent", "")
                for item in state.get("ledger", [])
                if item.get("agent") not in {"editor-serin", "publisher-minji", "main"}
            }
            if len(substantive_agents) >= 2:
                return "risk_block"
            return "risk_review"
        if agent == "research-pm":
            return "triage"
        if agent == "editor-serin":
            return "draft"
        if agent == "publisher-minji":
            return "publish"
        if agent == "main" and state.get("risk_gate") == "blocked":
            return "escalate" if state.get("draft_ready") else "coordinate"
        if agent.startswith("vip-"):
            return "client_plan"
        return "analysis"

    def _mention_targets(
        self, case: InvestmentCase, agent: str, state: dict[str, Any]
    ) -> list[str]:
        posted = set(state.get("posted_agents", []))
        pending = set(state.get("pending_mentions", []))
        if pending and agent not in pending:
            return [item for item in sorted(pending) if not self._recently_posted(state, item)][:2]
        if agent == "research-pm":
            candidate_groups = {
                "market": [["macro-minho", "risk-jaehyun"], ["theme-harin"]],
                "vip": [
                    [f"vip-{case.client_id}-arin", f"vip-{case.client_id}-junho", "risk-jaehyun"]
                ],
                "single_name": [["technical-yujin", "risk-jaehyun"], ["theme-harin"]],
                "technical": [["technical-yujin", "risk-jaehyun"]],
                "flow": [["theme-harin", "technical-yujin"], ["risk-jaehyun"]],
                "ownership": [["main", "risk-jaehyun"]],
                "intake": [["main"]],
            }
            for candidate_group in candidate_groups.get(case.case_type, [["risk-jaehyun"]]):
                targets = [
                    item
                    for item in candidate_group
                    if self.registry.get(item) and item not in posted
                ]
                targets = [item for item in targets if not self._recently_posted(state, item)]
                if targets:
                    return targets[:2]
        if agent == "risk-jaehyun":
            targets = [
                item
                for item in case.assigned_agents
                if item.startswith("vip-") or item == "technical-yujin"
            ]
            if not targets and case.case_type in {"market", "theme", "flow", "single_name"}:
                targets = ["research-pm", "main"]
            return [
                item
                for item in targets
                if self.registry.get(item) and not self._recently_posted(state, item)
            ][:2]
        if agent.startswith("vip-") and state.get("risk_gate") == "blocked":
            return [] if self._recently_posted(state, "risk-jaehyun") else ["risk-jaehyun"]
        if agent == "editor-serin":
            targets = ["main"]
            if case.case_type == "vip":
                targets.extend(item for item in case.assigned_agents if item.startswith("vip-"))
            return [
                item
                for item in targets
                if self.registry.get(item) and not self._recently_posted(state, item)
            ][:2]
        return []

    def _editor_ready(self, state: dict[str, Any]) -> bool:
        substantive_agents = {
            item.get("agent", "")
            for item in state.get("ledger", [])
            if item.get("agent") not in {"editor-serin", "publisher-minji"}
        }
        return len(substantive_agents) >= 2

    def _workflow_agents(self, case: InvestmentCase, state: dict[str, Any]) -> set[str]:
        agents: set[str] = set()
        if state.get("risk_gate") == "blocked":
            agents.add("main")
        if self._editor_ready(state) and not state.get("draft_ready"):
            agents.add("editor-serin")
        if state.get("draft_ready") and state.get("publish_ready") and not state.get("published"):
            agents.add("publisher-minji")
        if (
            case.case_type == "vip"
            and state.get("risk_gate") == "blocked"
            and not state.get("client_plan_ready")
        ):
            agents.update(item for item in case.assigned_agents if item.startswith("vip-"))
        return agents

    def _lead_context(self, case: InvestmentCase, action: str, state: dict[str, Any]) -> str:
        last_agent = str(state.get("last_agent", "")).strip()
        if not last_agent:
            return ""
        previous = self.registry.get(last_agent)
        if previous is None:
            return ""
        if state.get("last_human_message_text") and state.get("human_waiting"):
            return "Human ask 확인했다."
        if action in {"draft", "publish", "escalate"}:
            return f"{self.registry.tag(last_agent)}까지 올라온 내용을 이어받겠다."
        return f"{self.registry.tag(last_agent)} 포인트 이어서 보겠다."

    def _focus_context(self, state: dict[str, Any]) -> str:
        if not state.get("human_waiting"):
            return ""
        human_text = str(state.get("last_human_message_text", "")).strip()
        if not human_text:
            return ""
        normalized = " ".join(human_text.split())
        if len(normalized) > 120:
            normalized = normalized[:117].rstrip() + "..."
        return f"방금 human prompt는 `{normalized}`였다."

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

    def _state(self, case: InvestmentCase) -> dict[str, Any]:
        state = dict(case.metadata.get("autonomy", {}))
        state.setdefault("pending_mentions", [])
        state.setdefault("posted_agents", [])
        state.setdefault("agent_state", {})
        state.setdefault("ledger", [])
        state.setdefault("risk_gate", "open")
        state.setdefault("client_plan_ready", False)
        state.setdefault("draft_ready", False)
        state.setdefault("publish_ready", False)
        state.setdefault("published", False)
        state.setdefault("human_waiting", False)
        return state

    def _session_reset_hours(self, case: InvestmentCase) -> float:
        raw = os.environ.get("CLAWTEAM_AUTONOMY_SESSION_RESET_HOURS", "6").strip()
        try:
            base = float(raw) if raw else 6.0
        except ValueError:
            base = 6.0
        if case.case_type == "market":
            return min(base, 4.0)
        if case.case_type == "vip":
            return max(base, 4.0)
        return base

    def _should_pause_case(
        self,
        case: InvestmentCase,
        trigger: str,
        state: dict[str, Any],
    ) -> bool:
        if trigger in {"startup", "human_message"}:
            return False
        if state.get("human_waiting") or state.get("pending_mentions"):
            return False
        if self._workflow_agents(case, state):
            return False
        substantive_agents = {
            item.get("agent", "")
            for item in state.get("ledger", [])
            if item.get("agent") not in {"editor-serin", "publisher-minji", "main"}
        }
        if case.case_type == "vip":
            return state.get("risk_gate") == "blocked" and len(substantive_agents) >= 3
        return len(substantive_agents) >= 4
