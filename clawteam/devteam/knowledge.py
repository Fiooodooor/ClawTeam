"""Global knowledge store for ClawTeam -- the company's Second Brain.

Stores cross-project knowledge, lessons learned, technical decisions,
and domain expertise. Each entry is tagged with topics for retrieval.
Unlike PersonaMemory (per-persona learning), this is shared across
all personas and projects.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clawteam.team.models import get_data_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeEntry:
    """A single piece of organizational knowledge."""

    entry_id: str
    title: str
    content: str
    source: str  # "project_completion", "manual", "meeting", "code_review"
    topics: list[str] = field(default_factory=list)
    project_id: str = ""
    author: str = ""  # persona or "CEO"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeBase:
    """The full knowledge base."""

    entries: list[KnowledgeEntry] = field(default_factory=list)
    summary: str = ""  # LLM-compressed summary of old entries
    version: int = 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 50

_EXTRACT_SYSTEM_PROMPT = (
    "당신은 AI 개발회사의 지식 관리자입니다.\n"
    "프로젝트 완료 보고서에서 회사 전체에 유용한 핵심 지식을 추출하세요.\n\n"
    "규칙:\n"
    "- 프로젝트 특수 사항이 아닌 범용적인 인사이트만 추출\n"
    "- 기술적 결정, 발견된 패턴, 주의사항 위주\n"
    "- 반드시 아래 JSON 형식으로만 응답:\n"
    '{"title": "...", "content": "2-3문장 요약", "topics": ["topic1", "topic2"]}\n'
)

_COMPRESS_SYSTEM_PROMPT = (
    "기존 지식 요약과 오래된 지식 항목들을 통합하여 새로운 요약을 작성하세요.\n"
    "5-8문장으로 핵심 인사이트만 유지. JSON이 아닌 순수 텍스트.\n"
    "한국어로 응답하세요."
)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """Manages the company's global knowledge base.

    Storage: {data_dir}/teams/{team}/knowledge/global.json

    Retention policy:
    - Keep last 50 detailed entries
    - When exceeding 50, compress oldest into summary via LLM
    - Topics index for fast retrieval
    """

    def __init__(self, team_name: str) -> None:
        self._team_name = team_name
        self._base_dir = get_data_dir() / "teams" / team_name / "knowledge"

    @property
    def _path(self) -> Path:
        return self._base_dir / "global.json"

    # -- public API ---------------------------------------------------------

    def load(self) -> KnowledgeBase:
        """Load the knowledge base from disk."""
        if not self._path.exists():
            return KnowledgeBase()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            entries = [KnowledgeEntry(**e) for e in data.get("entries", [])]
            return KnowledgeBase(
                entries=entries,
                summary=data.get("summary", ""),
                version=data.get("version", 1),
            )
        except Exception as exc:
            logger.warning("Failed to load knowledge base: %s", exc)
            return KnowledgeBase()

    def save(self, kb: KnowledgeBase) -> None:
        """Save the knowledge base to disk (atomic write)."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [asdict(e) for e in kb.entries],
            "summary": kb.summary,
            "version": kb.version,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(self._path)

    def add_entry(self, entry: KnowledgeEntry) -> None:
        """Add a knowledge entry, compressing old entries if needed."""
        kb = self.load()

        if not entry.entry_id:
            entry.entry_id = f"k-{time.time_ns()}-{len(kb.entries)}"
        if not entry.created_at:
            from datetime import datetime, timezone

            entry.created_at = datetime.now(timezone.utc).isoformat()

        kb.entries.append(entry)

        if len(kb.entries) > _MAX_ENTRIES:
            self._compress_old_entries(kb)

        self.save(kb)
        logger.info("Knowledge entry added: %s (%s)", entry.title, entry.entry_id)

    def search(self, query: str, limit: int = 10) -> list[KnowledgeEntry]:
        """Simple keyword search across titles, content, and topics."""
        kb = self.load()
        query_lower = query.lower()
        scored: list[tuple[int, KnowledgeEntry]] = []

        for entry in kb.entries:
            score = 0
            searchable = f"{entry.title} {entry.content} {' '.join(entry.topics)}".lower()
            for word in query_lower.split():
                if word in searchable:
                    score += 1
                    if word in entry.title.lower():
                        score += 2  # title match bonus
                    if word in [t.lower() for t in entry.topics]:
                        score += 3  # topic match bonus

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def search_by_topic(self, topic: str) -> list[KnowledgeEntry]:
        """Find all entries with a given topic tag."""
        kb = self.load()
        topic_lower = topic.lower()
        return [e for e in kb.entries if any(t.lower() == topic_lower for t in e.topics)]

    def get_context_for_prompt(self, query: str, max_chars: int = 2000) -> str:
        """Build a context string for LLM prompt injection.

        Includes the compressed summary + most relevant entries.
        """
        kb = self.load()
        parts: list[str] = []

        if kb.summary:
            parts.append(f"[Company Knowledge Summary]\n{kb.summary}")

        relevant = self.search(query, limit=5)
        if relevant:
            parts.append("\n[Relevant Knowledge]")
            for entry in relevant:
                entry_text = f"- {entry.title}: {entry.content[:300]}"
                if entry.topics:
                    entry_text += f" (topics: {', '.join(entry.topics)})"
                parts.append(entry_text)

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    def extract_knowledge_from_project(
        self,
        project_id: str,
        project_title: str,
        completion_report: str,
        stage_history: list[dict],
    ) -> KnowledgeEntry | None:
        """Auto-extract knowledge from a completed project using LLM."""
        try:
            from clawteam.devteam.llm import chat
        except ImportError:
            return None

        user_prompt = (
            f"프로젝트: {project_title}\n"
            f"완료 보고서: {completion_report}\n"
            f"스테이지 이력: {json.dumps(stage_history, ensure_ascii=False)}\n"
        )

        try:
            raw = chat(_EXTRACT_SYSTEM_PROMPT, user_prompt, max_tokens=300)
            parsed = _parse_json_response(raw)
            if not parsed:
                return None
            return KnowledgeEntry(
                entry_id="",
                title=parsed.get("title", project_title),
                content=parsed.get("content", ""),
                source="project_completion",
                topics=parsed.get("topics", []),
                project_id=project_id,
                author="knowledge-extractor",
            )
        except Exception as exc:
            logger.debug("Knowledge extraction failed: %s", exc)
            return None

    # -- internal -----------------------------------------------------------

    def _compress_old_entries(self, kb: KnowledgeBase) -> None:
        """Compress oldest entries into summary when exceeding limit."""
        overflow = kb.entries[:-_MAX_ENTRIES]
        kb.entries = kb.entries[-_MAX_ENTRIES:]

        overflow_text = "\n".join(
            f"- {e.title}: {e.content[:200]}" for e in overflow
        )
        existing_summary = kb.summary or "(없음)"

        try:
            from clawteam.devteam.llm import chat

            user_prompt = (
                f"기존 요약:\n{existing_summary}\n\n"
                f"통합할 항목들:\n{overflow_text}\n"
            )
            compressed = chat(
                _COMPRESS_SYSTEM_PROMPT,
                user_prompt,
                temperature=0.3,
                max_tokens=400,
            )
            if compressed and compressed.strip():
                kb.summary = compressed.strip()
        except Exception:
            # Fallback: just append overflow titles to summary
            titles = ", ".join(e.title for e in overflow)
            kb.summary = f"{existing_summary}\nArchived: {titles}".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON object from LLM response. Returns empty dict on failure."""
    if not text:
        return {}

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}
