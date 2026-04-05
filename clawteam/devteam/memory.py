"""페르소나별 장기 메모리 저장소.

프로젝트 간 경험 학습을 JSON 파일로 관리하고,
Retention 정책(최근 10개)에 따라 오래된 엔트리를 LLM 요약으로 압축한다.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawteam.team.models import get_data_dir

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PersonaMemoryEntry:
    """페르소나의 단일 학습 기록."""

    project_id: str
    project_title: str
    stage: str
    summary: str
    key_decisions: list[str]
    patterns_learned: list[str]
    created_at: str


@dataclass
class PersonaMemory:
    """페르소나의 전체 메모리."""

    persona_name: str
    team_name: str
    entries: list[PersonaMemoryEntry] = field(default_factory=list)
    meta_summary: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 10
_RECENT_FOR_PROMPT = 3

_LEARNING_SYSTEM_PROMPT = (
    "당신은 소프트웨어 개발 팀의 {persona_name}입니다.\n"
    "방금 완료한 작업에서 배운 것을 정리하세요.\n\n"
    "- key_decisions: 내린 핵심 기술 결정 (최대 3개)\n"
    "- patterns_learned: 발견한 패턴, 인사이트, 주의사항 (최대 3개)\n"
    "- summary: 2문장 이내 요약\n\n"
    "반드시 아래 JSON 형식으로만 응답하세요:\n"
    '{{"summary": "...", "key_decisions": ["...", ...], "patterns_learned": ["...", ...]}}'
)

_COMPRESS_SYSTEM_PROMPT = (
    "당신은 메모리 압축 전문가입니다.\n"
    "아래의 기존 요약과 새로운 학습 기록들을 하나의 통합 요약으로 압축하세요.\n"
    "핵심 패턴과 반복되는 의사결정만 남기고, 3~5문장 이내로 작성하세요.\n"
    "한국어로 응답하세요."
)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class PersonaMemoryStore:
    """페르소나별 장기 메모리 관리.

    저장 경로: {data_dir}/teams/{team}/memory/{persona}.json

    Retention 정책:
    - 최근 10개 프로젝트 엔트리 유지
    - 11번째부터는 LLM으로 meta_summary에 압축 통합
    """

    def __init__(self, team_name: str) -> None:
        self.team_name = team_name
        self._base_dir = get_data_dir() / "teams" / team_name / "memory"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # -- public API ---------------------------------------------------------

    def save_memory(self, persona_name: str, entry: PersonaMemoryEntry) -> None:
        """새 학습 기록 저장. 10개 초과 시 가장 오래된 것을 meta_summary로 압축."""
        memory = self.load_memory(persona_name) or PersonaMemory(
            persona_name=persona_name,
            team_name=self.team_name,
        )
        memory.entries.append(entry)

        if len(memory.entries) > _MAX_ENTRIES:
            self._compress_old_entries(memory)

        self._write(persona_name, memory)

    def load_memory(self, persona_name: str) -> PersonaMemory | None:
        """페르소나 메모리 전체 로드. 파일이 없으면 None 반환."""
        path = self._path_for(persona_name)
        if not path.exists():
            return None

        raw = json.loads(path.read_text(encoding="utf-8"))
        return _dict_to_memory(raw)

    def get_context_for_prompt(
        self, persona_name: str, max_chars: int = 2000
    ) -> str:
        """프롬프트 주입용 메모리 컨텍스트 생성.

        meta_summary + 최근 3개 프로젝트의 주요 학습을 텍스트로 반환.
        max_chars를 초과하면 뒤에서부터 잘라낸다.
        """
        memory = self.load_memory(persona_name)
        if not memory:
            return ""

        parts: list[str] = []

        if memory.meta_summary:
            parts.append(f"[과거 경험 요약]\n{memory.meta_summary}")

        recent = memory.entries[-_RECENT_FOR_PROMPT:]
        for entry in recent:
            block = (
                f"\n[{entry.project_title} / {entry.stage}]\n"
                f"요약: {entry.summary}\n"
                f"결정: {', '.join(entry.key_decisions)}\n"
                f"패턴: {', '.join(entry.patterns_learned)}"
            )
            parts.append(block)

        if max_chars <= 0:
            return ""

        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    def generate_learning_summary(
        self,
        persona_name: str,
        project_id: str,
        project_title: str,
        stage: str,
        discussion_context: str,
    ) -> PersonaMemoryEntry:
        """LLM을 사용해 스테이지 완료 시 학습 요약을 생성."""
        from clawteam.devteam.llm import chat

        system = _LEARNING_SYSTEM_PROMPT.format(persona_name=persona_name)
        user_msg = (
            f"프로젝트: {project_title} (ID: {project_id})\n"
            f"스테이지: {stage}\n\n"
            f"대화 기록:\n{discussion_context}"
        )

        raw = chat(system=system, user=user_msg, temperature=0.3, max_tokens=400)
        parsed = _parse_json_response(raw)

        return PersonaMemoryEntry(
            project_id=project_id,
            project_title=project_title,
            stage=stage,
            summary=parsed.get("summary", ""),
            key_decisions=parsed.get("key_decisions", []),
            patterns_learned=parsed.get("patterns_learned", []),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    # -- internal -----------------------------------------------------------

    def _compress_old_entries(self, memory: PersonaMemory) -> None:
        """10개 초과 엔트리를 meta_summary로 압축.

        가장 오래된 엔트리들을 LLM으로 요약해 meta_summary에 통합하고,
        최근 _MAX_ENTRIES개만 entries에 남긴다.
        """
        overflow = memory.entries[:-_MAX_ENTRIES]
        memory.entries = memory.entries[-_MAX_ENTRIES:]

        overflow_text = "\n".join(
            f"- [{e.project_title}/{e.stage}] {e.summary}" for e in overflow
        )
        existing = memory.meta_summary or "(없음)"
        user_msg = (
            f"기존 요약:\n{existing}\n\n"
            f"새로 압축할 항목:\n{overflow_text}"
        )

        from clawteam.devteam.llm import chat

        compressed = chat(
            system=_COMPRESS_SYSTEM_PROMPT,
            user=user_msg,
            temperature=0.3,
            max_tokens=300,
        )
        memory.meta_summary = compressed.strip() if compressed else existing

    def _path_for(self, persona_name: str) -> Path:
        """페르소나 JSON 파일 경로."""
        safe_name = persona_name.replace("/", "_").replace("\\", "_")
        return self._base_dir / f"{safe_name}.json"

    def _write(self, persona_name: str, memory: PersonaMemory) -> None:
        """Atomic file write: tmp 파일 작성 후 rename."""
        path = self._path_for(persona_name)
        data = _memory_to_dict(memory)
        content = json.dumps(data, ensure_ascii=False, indent=2)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._base_dir), suffix=".tmp"
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp_path, str(path))
        except BaseException:
            os.close(fd) if not _is_fd_closed(fd) else None
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _memory_to_dict(memory: PersonaMemory) -> dict[str, Any]:
    return {
        "persona_name": memory.persona_name,
        "team_name": memory.team_name,
        "meta_summary": memory.meta_summary,
        "entries": [asdict(e) for e in memory.entries],
    }


def _dict_to_memory(raw: dict[str, Any]) -> PersonaMemory:
    entries = [
        PersonaMemoryEntry(**e)
        for e in raw.get("entries", [])
    ]
    return PersonaMemory(
        persona_name=raw["persona_name"],
        team_name=raw["team_name"],
        entries=entries,
        meta_summary=raw.get("meta_summary", ""),
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    """LLM 응답에서 JSON 객체를 추출. 실패 시 빈 dict 반환."""
    if not text:
        return {}

    # JSON 블록이 ```json ... ``` 안에 있을 수 있음
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}


def _is_fd_closed(fd: int) -> bool:
    """파일 디스크립터가 이미 닫혔는지 확인."""
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True
