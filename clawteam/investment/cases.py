"""Case and Slack thread persistence for the investment runtime."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from clawteam.investment.bootstrap import load_runtime_state, save_runtime_state


class CaseThreadRef(BaseModel):
    channel: str
    channel_name: str = ""
    thread_ts: str
    root_ts: str = ""
    last_message_ts: str = ""


class InvestmentCase(BaseModel):
    case_id: str
    case_type: str
    title: str
    status: str = "open"
    client_id: str = ""
    thread: CaseThreadRef | None = None
    assigned_agents: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    dissent_refs: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class CaseBindingResult:
    case: InvestmentCase
    created_thread: bool


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "case"


class CaseManager:
    """Loads, saves, and binds investment cases to Slack threads."""

    def __init__(self, team_name: str, workspace_dir: str | None = None):
        self.team_name = team_name
        self.workspace_dir = (
            Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        )
        self.shared_cases_dir = self.workspace_dir / "shared" / "cases"

    def list_cases(self) -> list[InvestmentCase]:
        if not self.shared_cases_dir.exists():
            return []
        cases: list[InvestmentCase] = []
        for path in sorted(self.shared_cases_dir.glob("**/*.json")):
            try:
                cases.append(self._load_case_path(path))
            except Exception:
                continue
        return cases

    def get_case(self, case_id: str) -> InvestmentCase | None:
        path = self._find_case_path(case_id)
        if path is None:
            return None
        return self._load_case_path(path)

    def save_case(self, case: InvestmentCase) -> InvestmentCase:
        path = self._find_case_path(case.case_id)
        if path is None:
            path = self._new_case_path(case)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
        self._sync_runtime_thread(case)
        return case

    def ensure_case_thread(
        self,
        case_id: str,
        slack_client,
        channel_name: str,
        private: bool = False,
        channel_info: dict[str, Any] | None = None,
    ) -> CaseBindingResult:
        case = self.get_case(case_id)
        if case is None:
            raise FileNotFoundError(f"Case '{case_id}' not found")
        channel_info = channel_info or slack_client.ensure_channel(channel_name, private=private)
        channel_id = channel_info["id"]
        if case.thread and case.thread.thread_ts:
            existing = case.thread.model_copy(
                update={
                    "channel": channel_id,
                    "channel_name": channel_name,
                }
            )
            case.thread = existing
            self.save_case(case)
            return CaseBindingResult(case=case, created_thread=False)

        response = slack_client.post_message(
            channel_id,
            self._case_summary(case),
            metadata={
                "event_type": "clawteam_case_opened",
                "event_payload": {
                    "team": self.team_name,
                    "case_id": case.case_id,
                    "case_type": case.case_type,
                },
            },
        )
        ts = response.get("ts", "")
        case.thread = CaseThreadRef(
            channel=channel_id,
            channel_name=channel_name,
            thread_ts=ts,
            root_ts=ts,
            last_message_ts=ts,
        )
        self.save_case(case)
        return CaseBindingResult(case=case, created_thread=True)

    def bind_existing_thread(
        self,
        case_id: str,
        channel_id: str,
        channel_name: str,
        thread_ts: str,
        last_message_ts: str = "",
    ) -> InvestmentCase:
        case = self.get_case(case_id)
        if case is None:
            raise FileNotFoundError(f"Case '{case_id}' not found")
        case.thread = CaseThreadRef(
            channel=channel_id,
            channel_name=channel_name,
            thread_ts=thread_ts,
            root_ts=thread_ts,
            last_message_ts=last_message_ts or thread_ts,
        )
        return self.save_case(case)

    def find_case_by_thread(self, channel_id: str, thread_ts: str) -> InvestmentCase | None:
        for case in self.list_cases():
            if (
                case.thread
                and case.thread.channel == channel_id
                and case.thread.thread_ts == thread_ts
            ):
                return case
        return None

    def open_intake_case(
        self,
        title: str,
        case_type: str,
        assigned_agents: list[str] | None = None,
        source_channel: str = "",
        source_thread_ts: str = "",
        client_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> InvestmentCase:
        case_id = self._build_case_id(case_type, title, source_thread_ts)
        case = InvestmentCase(
            case_id=case_id,
            case_type=case_type,
            title=title,
            client_id=client_id,
            assigned_agents=assigned_agents or [],
            metadata={
                "source_channel": source_channel,
                "source_thread_ts": source_thread_ts,
                **(metadata or {}),
            },
        )
        return self.save_case(case)

    def update_case_activity(self, case: InvestmentCase, message_ts: str) -> InvestmentCase:
        if case.thread:
            case.thread.last_message_ts = message_ts
        case.metadata["last_activity_ts"] = message_ts
        return self.save_case(case)

    def resolve_channel_name(self, case: InvestmentCase) -> str:
        if case.thread and case.thread.channel_name:
            return case.thread.channel_name
        channel_name = str(case.metadata.get("channel_name", "")).strip()
        if channel_name:
            return channel_name
        if case.case_type == "vip" and case.client_id:
            return f"lbox-vip-{_slugify(case.client_id)}-ops"
        mapping = {
            "market": "lbox-macro",
            "theme": "lbox-themes",
            "technical": "lbox-technicals",
            "flow": "lbox-flow",
            "ownership": "lbox-ownership",
            "single_name": "lbox-single-names",
            "risk": "lbox-risk",
            "intake": "lbox-intake",
        }
        return mapping.get(case.case_type, "lbox-ops")

    def _find_case_path(self, case_id: str) -> Path | None:
        if not self.shared_cases_dir.exists():
            return None
        for path in self.shared_cases_dir.glob("**/*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("case_id") == case_id:
                return path
        return None

    def _new_case_path(self, case: InvestmentCase) -> Path:
        if case.case_type == "vip" and case.client_id:
            return (
                self.shared_cases_dir
                / "vip"
                / _slugify(case.client_id)
                / f"{_slugify(case.title)}.json"
            )
        return self.shared_cases_dir / case.case_type / f"{case.case_id}.json"

    def _load_case_path(self, path: Path) -> InvestmentCase:
        data = json.loads(path.read_text(encoding="utf-8"))
        return InvestmentCase.model_validate(data)

    def _case_summary(self, case: InvestmentCase) -> str:
        lines = [
            f"*{case.title}*",
            f"Case ID: `{case.case_id}`",
            f"Type: {case.case_type}",
        ]
        if case.open_questions:
            lines.append("Open questions:")
            lines.extend(f"- {question}" for question in case.open_questions[:5])
        if case.assigned_agents:
            lines.append(f"Owners: {', '.join(case.assigned_agents)}")
        return "\n".join(lines)

    def _build_case_id(self, case_type: str, title: str, source_thread_ts: str) -> str:
        base = f"{case_type}-{_slugify(title)}"
        if source_thread_ts:
            suffix = source_thread_ts.replace(".", "-")
            return f"{base}-{suffix}"
        return base

    def _sync_runtime_thread(self, case: InvestmentCase) -> None:
        if not case.thread:
            return
        state = load_runtime_state(self.team_name)
        state.active_case_threads[case.case_id] = case.thread.thread_ts
        save_runtime_state(state)
