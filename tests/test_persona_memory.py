"""PersonaMemoryStore 테스트.

테스트 비율: Failure 67% / Happy 33%
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from clawteam.devteam.memory import (
    PersonaMemory,
    PersonaMemoryEntry,
    PersonaMemoryStore,
    _dict_to_memory,
    _memory_to_dict,
    _parse_json_response,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_data_dir(tmp_path: Path):
    """get_data_dir()를 tmp_path로 오버라이드."""
    with patch("clawteam.devteam.memory.get_data_dir", return_value=tmp_path):
        yield tmp_path


@pytest.fixture()
def store(tmp_data_dir: Path) -> PersonaMemoryStore:
    return PersonaMemoryStore(team_name="test-team")


def _make_entry(
    project_id: str = "proj-1",
    project_title: str = "Test Project",
    stage: str = "design",
    summary: str = "Learned something useful.",
    key_decisions: list[str] | None = None,
    patterns_learned: list[str] | None = None,
) -> PersonaMemoryEntry:
    return PersonaMemoryEntry(
        project_id=project_id,
        project_title=project_title,
        stage=stage,
        summary=summary,
        key_decisions=key_decisions or ["decision-1"],
        patterns_learned=patterns_learned or ["pattern-1"],
        created_at="2025-01-01T00:00:00+00:00",
    )


# ===========================================================================
# Happy Path (33%)
# ===========================================================================


class TestHappyPath:
    """정상 동작 테스트."""

    def test_save_and_load_roundtrip(self, store: PersonaMemoryStore) -> None:
        """저장 후 로드하면 동일한 데이터를 반환한다."""
        entry = _make_entry()
        store.save_memory("alice", entry)

        memory = store.load_memory("alice")
        assert memory is not None
        assert memory.persona_name == "alice"
        assert memory.team_name == "test-team"
        assert len(memory.entries) == 1
        assert memory.entries[0].project_id == "proj-1"
        assert memory.entries[0].key_decisions == ["decision-1"]

    def test_get_context_for_prompt_formats_text(
        self, store: PersonaMemoryStore
    ) -> None:
        """컨텍스트 문자열이 올바른 형식으로 생성된다."""
        store.save_memory("bob", _make_entry(project_title="Alpha"))
        store.save_memory("bob", _make_entry(project_title="Beta"))

        ctx = store.get_context_for_prompt("bob")
        assert "Alpha" in ctx
        assert "Beta" in ctx
        assert "요약:" in ctx

    def test_generate_learning_summary_returns_entry(
        self, store: PersonaMemoryStore
    ) -> None:
        """LLM 응답을 파싱해 PersonaMemoryEntry를 생성한다."""
        mock_response = json.dumps(
            {
                "summary": "Good progress.",
                "key_decisions": ["Use DDD"],
                "patterns_learned": ["Early return"],
            }
        )
        with patch("clawteam.devteam.llm.chat", return_value=mock_response):
            entry = store.generate_learning_summary(
                persona_name="charlie",
                project_id="p-1",
                project_title="Proj",
                stage="implement",
                discussion_context="We discussed architecture.",
            )
        assert entry.summary == "Good progress."
        assert entry.key_decisions == ["Use DDD"]
        assert entry.project_id == "p-1"

    def test_multiple_entries_append(self, store: PersonaMemoryStore) -> None:
        """여러 엔트리를 순서대로 추가할 수 있다."""
        for i in range(5):
            store.save_memory("dave", _make_entry(project_id=f"p-{i}"))

        memory = store.load_memory("dave")
        assert memory is not None
        assert len(memory.entries) == 5
        assert memory.entries[-1].project_id == "p-4"


# ===========================================================================
# Failure Cases (67%)
# ===========================================================================


class TestLoadFailures:
    """load_memory 실패 케이스."""

    def test_load_nonexistent_persona_returns_none(
        self, store: PersonaMemoryStore
    ) -> None:
        """존재하지 않는 페르소나는 None을 반환한다."""
        result = store.load_memory("nonexistent")
        assert result is None

    def test_load_corrupted_json_raises(
        self, store: PersonaMemoryStore, tmp_data_dir: Path
    ) -> None:
        """손상된 JSON 파일은 예외를 발생시킨다."""
        path = tmp_data_dir / "teams" / "test-team" / "memory" / "broken.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            store.load_memory("broken")

    def test_load_missing_required_fields_raises(
        self, store: PersonaMemoryStore, tmp_data_dir: Path
    ) -> None:
        """필수 필드 누락 시 KeyError를 발생시킨다."""
        path = tmp_data_dir / "teams" / "test-team" / "memory" / "partial.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"entries": []}', encoding="utf-8")

        with pytest.raises(KeyError):
            store.load_memory("partial")


class TestContextFailures:
    """get_context_for_prompt 실패/엣지 케이스."""

    def test_empty_persona_returns_empty_string(
        self, store: PersonaMemoryStore
    ) -> None:
        """메모리가 없는 페르소나는 빈 문자열을 반환한다."""
        assert store.get_context_for_prompt("ghost") == ""

    def test_max_chars_truncation(self, store: PersonaMemoryStore) -> None:
        """max_chars 제한이 동작한다."""
        for i in range(5):
            store.save_memory(
                "eve",
                _make_entry(
                    project_id=f"p-{i}",
                    summary="A" * 500,
                    key_decisions=["B" * 200],
                    patterns_learned=["C" * 200],
                ),
            )

        ctx = store.get_context_for_prompt("eve", max_chars=100)
        assert len(ctx) <= 100

    def test_max_chars_zero(self, store: PersonaMemoryStore) -> None:
        """max_chars=0이면 빈 문자열을 반환한다."""
        store.save_memory("frank", _make_entry())
        ctx = store.get_context_for_prompt("frank", max_chars=0)
        assert ctx == ""


class TestRetentionPolicy:
    """Retention 정책 (압축) 실패/엣지 케이스."""

    def test_11th_entry_triggers_compression(
        self, store: PersonaMemoryStore
    ) -> None:
        """11번째 엔트리 저장 시 압축이 트리거된다."""
        with patch("clawteam.devteam.llm.chat", return_value="Compressed summary"):
            for i in range(11):
                store.save_memory("gina", _make_entry(project_id=f"p-{i}"))

        memory = store.load_memory("gina")
        assert memory is not None
        assert len(memory.entries) == 10
        assert memory.meta_summary == "Compressed summary"

    def test_compression_llm_failure_keeps_existing_summary(
        self, store: PersonaMemoryStore
    ) -> None:
        """LLM 압축 실패(빈 응답) 시 기존 meta_summary를 유지한다."""
        # 먼저 10개 채우기
        for i in range(10):
            store.save_memory("hank", _make_entry(project_id=f"p-{i}"))

        # meta_summary를 수동 설정
        memory = store.load_memory("hank")
        assert memory is not None
        memory.meta_summary = "Existing summary"
        store._write("hank", memory)

        # 11번째 추가 - LLM이 빈 문자열 반환
        with patch("clawteam.devteam.llm.chat", return_value=""):
            store.save_memory("hank", _make_entry(project_id="p-10"))

        memory = store.load_memory("hank")
        assert memory is not None
        assert memory.meta_summary == "Existing summary"


class TestGenerateLearningFailures:
    """generate_learning_summary 실패 케이스."""

    def test_llm_returns_empty_string(self, store: PersonaMemoryStore) -> None:
        """LLM이 빈 문자열을 반환하면 빈 필드의 엔트리를 생성한다."""
        with patch("clawteam.devteam.llm.chat", return_value=""):
            entry = store.generate_learning_summary(
                persona_name="iris",
                project_id="p-1",
                project_title="Proj",
                stage="review",
                discussion_context="...",
            )
        assert entry.summary == ""
        assert entry.key_decisions == []
        assert entry.patterns_learned == []

    def test_llm_returns_invalid_json(self, store: PersonaMemoryStore) -> None:
        """LLM이 잘못된 JSON을 반환하면 빈 필드의 엔트리를 생성한다."""
        with patch(
            "clawteam.devteam.llm.chat",
            return_value="This is not JSON at all!",
        ):
            entry = store.generate_learning_summary(
                persona_name="jack",
                project_id="p-1",
                project_title="Proj",
                stage="plan",
                discussion_context="...",
            )
        assert entry.summary == ""
        assert entry.key_decisions == []

    def test_llm_returns_partial_json(self, store: PersonaMemoryStore) -> None:
        """LLM이 일부 필드만 포함한 JSON을 반환해도 동작한다."""
        with patch(
            "clawteam.devteam.llm.chat",
            return_value='{"summary": "Only this."}',
        ):
            entry = store.generate_learning_summary(
                persona_name="kate",
                project_id="p-1",
                project_title="Proj",
                stage="test",
                discussion_context="...",
            )
        assert entry.summary == "Only this."
        assert entry.key_decisions == []
        assert entry.patterns_learned == []

    def test_llm_raises_exception_propagates(
        self, store: PersonaMemoryStore
    ) -> None:
        """LLM 호출 자체가 실패하면 예외가 전파된다."""
        with patch(
            "clawteam.devteam.llm.chat",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            with pytest.raises(RuntimeError, match="LLM unavailable"):
                store.generate_learning_summary(
                    persona_name="leo",
                    project_id="p-1",
                    project_title="Proj",
                    stage="deploy",
                    discussion_context="...",
                )


class TestSerializationEdgeCases:
    """직렬화/역직렬화 엣지 케이스."""

    def test_parse_json_empty_string(self) -> None:
        assert _parse_json_response("") == {}

    def test_parse_json_markdown_fenced(self) -> None:
        """마크다운 코드 블록 안의 JSON을 파싱한다."""
        text = '```json\n{"summary": "ok"}\n```'
        result = _parse_json_response(text)
        assert result == {"summary": "ok"}

    def test_parse_json_garbage(self) -> None:
        assert _parse_json_response("hello world!") == {}

    def test_roundtrip_serialization(self) -> None:
        """PersonaMemory -> dict -> PersonaMemory 왕복 변환."""
        memory = PersonaMemory(
            persona_name="test",
            team_name="team",
            entries=[_make_entry()],
            meta_summary="some summary",
        )
        d = _memory_to_dict(memory)
        restored = _dict_to_memory(d)
        assert restored.persona_name == memory.persona_name
        assert restored.meta_summary == memory.meta_summary
        assert len(restored.entries) == 1
        assert restored.entries[0].project_id == memory.entries[0].project_id

    def test_persona_name_with_slashes_sanitized(
        self, store: PersonaMemoryStore
    ) -> None:
        """슬래시가 포함된 페르소나 이름이 안전하게 처리된다."""
        entry = _make_entry()
        store.save_memory("evil/path/../name", entry)

        memory = store.load_memory("evil/path/../name")
        assert memory is not None
        assert memory.persona_name == "evil/path/../name"
