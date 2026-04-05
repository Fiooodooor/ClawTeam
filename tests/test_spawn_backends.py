"""Tests for spawn backend environment propagation."""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, cast

from clawteam.spawn.cli_env import build_spawn_path, resolve_clawteam_executable
from clawteam.spawn.subprocess_backend import SubprocessBackend
from clawteam.spawn.tmux_backend import (
    TmuxBackend,
    _confirm_workspace_trust_if_prompted,
    _detect_idle_from_pane_output,
)

TMUX_BIN = "/opt/homebrew/bin/tmux"


class DummyProcess:
    def __init__(self, pid: int = 4321):
        self.pid = pid

    def poll(self):
        return None


def test_subprocess_backend_prepends_current_clawteam_bin_to_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return DummyProcess()

    monkeypatch.setattr(
        "clawteam.spawn.command_validation.shutil.which",
        lambda name, path=None: "/usr/bin/codex" if name == "codex" else None,
    )
    monkeypatch.setattr("clawteam.spawn.subprocess_backend.subprocess.Popen", fake_popen)
    monkeypatch.setattr("clawteam.spawn.registry.register_agent", lambda **_: None)

    backend = SubprocessBackend()
    backend.spawn(
        command=["codex"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    env = cast(dict[str, str], captured["env"])
    assert env["PATH"].startswith(f"{clawteam_bin.parent}:")
    assert env["CLAWTEAM_BIN"] == str(clawteam_bin)


def test_tmux_backend_exports_spawn_path_for_agent_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    run_calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        run_calls.append(args)
        if args[:3] == [TMUX_BIN, "has-session", "-t"]:
            return Result(returncode=1)
        if args[:3] == [TMUX_BIN, "list-panes", "-t"]:
            return Result(returncode=0, stdout="9876\n")
        return Result(returncode=0)

    original_which = __import__("shutil").which
    monkeypatch.setattr(
        "clawteam.spawn.tmux_backend.shutil.which",
        lambda name, path=None: TMUX_BIN if name == "tmux" else original_which(name),
    )
    monkeypatch.setattr(
        "clawteam.spawn.command_validation.shutil.which",
        lambda name, path=None: "/usr/bin/codex" if name == "codex" else original_which(name),
    )
    monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
    monkeypatch.setattr("clawteam.spawn.registry.register_agent", lambda **_: None)

    backend = TmuxBackend()
    backend.spawn(
        command=["codex"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    new_session = next(call for call in run_calls if call[:3] == [TMUX_BIN, "new-session", "-d"])
    full_cmd = new_session[-1]
    assert f"export PATH={clawteam_bin.parent}:/usr/bin:/bin" in full_cmd
    assert f"export CLAWTEAM_BIN={clawteam_bin}" in full_cmd
    assert f"{clawteam_bin} lifecycle on-exit --team demo-team --agent worker1" in full_cmd


def test_tmux_backend_returns_error_when_command_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    run_calls: list[list[str]] = []

    def fake_which(name, path=None):
        if name == "tmux":
            return TMUX_BIN
        return None

    def fake_run(args, **kwargs):
        run_calls.append(args)
        raise AssertionError("tmux should not be invoked when the command is missing")

    monkeypatch.setattr("clawteam.spawn.tmux_backend.shutil.which", fake_which)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)

    backend = TmuxBackend()
    result = backend.spawn(
        command=["nanobot"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    assert result == (
        "Error: command 'nanobot' not found in PATH. "
        "Install the agent CLI first or pass an executable path."
    )
    assert run_calls == []


def test_subprocess_backend_returns_error_when_command_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    popen_called = False

    def fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("Popen should not be called when the command is missing")

    monkeypatch.setattr("clawteam.spawn.subprocess_backend.subprocess.Popen", fake_popen)

    backend = SubprocessBackend()
    result = backend.spawn(
        command=["nanobot"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    assert result == (
        "Error: command 'nanobot' not found in PATH. "
        "Install the agent CLI first or pass an executable path."
    )
    assert popen_called is False


def test_tmux_backend_normalizes_bare_nanobot_to_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    run_calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        run_calls.append(args)
        if args[:3] == [TMUX_BIN, "has-session", "-t"]:
            return Result(returncode=1)
        if args[:3] == [TMUX_BIN, "list-panes", "-t"]:
            return Result(returncode=0, stdout="9876\n")
        return Result(returncode=0)

    def fake_which(name, path=None):
        if name == "tmux":
            return TMUX_BIN
        if name == "nanobot":
            return "/usr/bin/nanobot"
        return None

    monkeypatch.setattr("clawteam.spawn.tmux_backend.shutil.which", fake_which)
    monkeypatch.setattr("clawteam.spawn.command_validation.shutil.which", fake_which)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
    monkeypatch.setattr("clawteam.spawn.registry.register_agent", lambda **_: None)

    backend = TmuxBackend()
    backend.spawn(
        command=["nanobot"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    new_session = next(call for call in run_calls if call[:3] == [TMUX_BIN, "new-session", "-d"])
    full_cmd = new_session[-1]
    assert " nanobot agent -w /tmp/demo -m 'do work';" in full_cmd


def test_tmux_backend_confirms_claude_workspace_trust_prompt(monkeypatch):
    run_calls: list[list[str]] = []
    capture_count = 0

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        nonlocal capture_count
        run_calls.append(args)
        if args[:4] == [TMUX_BIN, "capture-pane", "-p", "-t"]:
            capture_count += 1
            if capture_count == 1:
                return Result(
                    stdout=("Quick safety check\nYes, I trust this folder\nEnter to confirm\n")
                )
            return Result(stdout="")
        return Result()

    monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)

    confirmed = _confirm_workspace_trust_if_prompted("demo:agent", ["claude"], tmux_bin=TMUX_BIN)

    assert confirmed is True
    assert [TMUX_BIN, "send-keys", "-t", "demo:agent", "Enter"] in run_calls


def test_tmux_backend_confirms_codex_workspace_trust_prompt(monkeypatch):
    run_calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        run_calls.append(args)
        if args[:4] == [TMUX_BIN, "capture-pane", "-p", "-t"]:
            return Result(
                stdout=("Do you trust the contents of this directory?\nPress enter to continue\n")
            )
        return Result()

    monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
    monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)

    confirmed = _confirm_workspace_trust_if_prompted("demo:agent", ["codex"], tmux_bin=TMUX_BIN)

    assert confirmed is True
    assert [TMUX_BIN, "send-keys", "-t", "demo:agent", "Enter"] in run_calls


def test_subprocess_backend_normalizes_nanobot_and_uses_message_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    clawteam_bin = tmp_path / "venv" / "bin" / "clawteam"
    clawteam_bin.parent.mkdir(parents=True)
    clawteam_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "argv", [str(clawteam_bin)])

    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return DummyProcess()

    monkeypatch.setattr(
        "clawteam.spawn.command_validation.shutil.which",
        lambda name, path=None: "/usr/bin/nanobot" if name == "nanobot" else None,
    )
    monkeypatch.setattr("clawteam.spawn.subprocess_backend.subprocess.Popen", fake_popen)
    monkeypatch.setattr("clawteam.spawn.registry.register_agent", lambda **_: None)

    backend = SubprocessBackend()
    backend.spawn(
        command=["nanobot"],
        agent_name="worker1",
        agent_id="agent-1",
        agent_type="general-purpose",
        team_name="demo-team",
        prompt="do work",
        cwd="/tmp/demo",
        skip_permissions=True,
    )

    assert "nanobot agent -w /tmp/demo -m 'do work'" in cast(str, captured["cmd"])


# ---------- _detect_idle_from_pane_output ----------


class TestDetectIdleFromPaneOutput:
    """idle 감지 헬퍼의 단위 테스트.

    비율: Failure 9 / Happy 4 = 69% / 31%
    """

    # --- Failure cases (idle이 아닌 경우) ---

    def test_empty_string_is_not_idle(self):
        assert _detect_idle_from_pane_output("") is False

    def test_none_like_empty_is_not_idle(self):
        assert _detect_idle_from_pane_output("   \n   \n   ") is False

    def test_active_output_without_prompt_is_not_idle(self):
        pane = "Analyzing codebase...\nReading files...\nProcessing"
        assert _detect_idle_from_pane_output(pane) is False

    def test_greater_than_in_middle_of_text_is_not_idle(self):
        """'>' 가 문장 중간에 있으면 idle로 판단하지 않아야 한다."""
        pane = "value > threshold detected\nstill running"
        assert _detect_idle_from_pane_output(pane) is False

    def test_only_whitespace_lines_is_not_idle(self):
        pane = "\n\n\n"
        assert _detect_idle_from_pane_output(pane) is False

    def test_single_non_prompt_line_is_not_idle(self):
        pane = "Building project..."
        assert _detect_idle_from_pane_output(pane) is False

    def test_partial_prompt_char_in_word_is_not_idle(self):
        """'>' 가 줄 시작이 아니라 단어 내부에 있으면 idle 아님."""
        pane = "foo>bar\nbaz"
        assert _detect_idle_from_pane_output(pane) is False

    def test_output_ending_with_content_no_trailing_newline_is_not_idle(self):
        pane = "line1\nline2\nstill working"
        assert _detect_idle_from_pane_output(pane) is False

    def test_only_newlines_no_content_is_not_idle(self):
        pane = "\n"
        assert _detect_idle_from_pane_output(pane) is False

    # --- Happy path (idle인 경우) ---

    def test_claude_prompt_char_detected(self):
        pane = "Done.\n\u276f "
        assert _detect_idle_from_pane_output(pane) is True

    def test_bypass_permissions_indicator_detected(self):
        pane = "Ready\n\u23f5\u23f5 "
        assert _detect_idle_from_pane_output(pane) is True

    def test_generic_prompt_greater_than_detected(self):
        pane = "Output complete\n> "
        assert _detect_idle_from_pane_output(pane) is True

    def test_trailing_empty_line_after_content_is_idle(self):
        pane = "Task finished successfully.\n\n"
        assert _detect_idle_from_pane_output(pane) is True


# ---------- is_agent_idle ----------


class TestIsAgentIdle:
    """TmuxBackend.is_agent_idle 통합 테스트.

    비율: Failure 4 / Happy 2 = 67% / 33%
    """

    # --- Failure cases ---

    def test_returns_false_on_capture_pane_error(self, monkeypatch):
        """tmux capture-pane 자체가 실패하면 False."""

        class Result:
            def __init__(self):
                self.returncode = 1
                self.stdout = ""

        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.subprocess.run",
            lambda *a, **kw: Result(),
        )
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1, 5]))

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=1.0) is False

    def test_returns_false_when_agent_is_busy(self, monkeypatch):
        """에이전트가 작업 중이면 timeout까지 폴링 후 False."""

        class Result:
            def __init__(self):
                self.returncode = 0
                self.stdout = "Analyzing code...\nReading files...\nProcessing"

        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.subprocess.run",
            lambda *a, **kw: Result(),
        )
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1, 5]))

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=1.0) is False

    def test_returns_false_on_empty_pane_output(self, monkeypatch):
        """pane 출력이 비어있으면 idle 아님."""

        class Result:
            def __init__(self):
                self.returncode = 0
                self.stdout = ""

        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.subprocess.run",
            lambda *a, **kw: Result(),
        )
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1, 5]))

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=1.0) is False

    def test_respects_timeout(self, monkeypatch):
        """timeout 내에 idle이 감지되지 않으면 False."""
        call_count = 0

        class Result:
            def __init__(self):
                self.returncode = 0
                self.stdout = "still working..."

        def fake_run(*a, **kw):
            nonlocal call_count
            call_count += 1
            return Result()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        # 0, 0.5, 1.0, 1.5 -> deadline exceeded
        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.time.monotonic",
            _make_monotonic_sequence([0, 0.5, 1.0, 1.5, 5]),
        )

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=1.0) is False
        assert call_count >= 1

    # --- Happy path ---

    def test_returns_true_when_prompt_detected(self, monkeypatch):
        """프롬프트 문자가 감지되면 즉시 True."""

        class Result:
            def __init__(self):
                self.returncode = 0
                self.stdout = "Done.\n\u276f "

        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.subprocess.run",
            lambda *a, **kw: Result(),
        )
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1]))

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=3.0) is True

    def test_returns_true_on_second_poll(self, monkeypatch):
        """첫 폴링은 busy, 두 번째에 idle 감지."""
        call_count = 0

        class BusyResult:
            returncode = 0
            stdout = "Processing..."

        class IdleResult:
            returncode = 0
            stdout = "Done.\n\u276f "

        def fake_run(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return BusyResult()
            return IdleResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.time.monotonic",
            _make_monotonic_sequence([0, 0.5, 1.0]),
        )

        assert TmuxBackend.is_agent_idle("demo:agent", timeout_seconds=3.0) is True
        assert call_count == 2


# ---------- send_followup_prompt ----------


class TestSendFollowupPrompt:
    """TmuxBackend.send_followup_prompt 테스트.

    비율: Failure 5 / Happy 2 = 71% / 29%
    """

    # --- Failure cases ---

    def test_error_on_empty_prompt(self, monkeypatch):
        backend = TmuxBackend()
        result = backend.send_followup_prompt("demo:agent", "", "worker1")
        assert result.startswith("Error:")
        assert "empty" in result

    def test_error_when_target_not_found(self, monkeypatch):
        class Result:
            returncode = 1
            stdout = ""
            stderr = ""

        monkeypatch.setattr(
            "clawteam.spawn.tmux_backend.subprocess.run",
            lambda *a, **kw: Result(),
        )

        backend = TmuxBackend()
        result = backend.send_followup_prompt("nonexistent:agent", "do work", "worker1")
        assert result.startswith("Error:")
        assert "not found" in result

    def test_error_when_agent_not_idle(self, monkeypatch):
        call_args: list[list[str]] = []

        class ListPanesResult:
            returncode = 0
            stdout = "%1\n"
            stderr = ""

        class CapturePaneResult:
            returncode = 0
            stdout = "Still processing..."

        def fake_run(args, **kw):
            call_args.append(args)
            if "list-panes" in args:
                return ListPanesResult()
            if "capture-pane" in args:
                return CapturePaneResult()
            return ListPanesResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1, 5]))

        backend = TmuxBackend()
        result = backend.send_followup_prompt("demo:agent", "next task", "worker1")
        assert result.startswith("Error:")
        assert "not idle" in result

    def test_error_when_load_buffer_fails(self, monkeypatch, tmp_path):
        """load-buffer 실패 시 에러 반환 + tmpfile 정리."""

        class OkResult:
            returncode = 0
            stdout = "%1\n"
            stderr = ""

        class FailResult:
            returncode = 1
            stdout = ""
            stderr = "buffer error"

        def fake_run(args, **kw):
            if "list-panes" in args:
                return OkResult()
            if "capture-pane" in args:
                r = OkResult()
                r.stdout = "Done.\n\u276f "
                return r
            if "load-buffer" in args:
                return FailResult()
            if "delete-buffer" in args:
                return OkResult()
            return OkResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1]))

        backend = TmuxBackend()
        result = backend.send_followup_prompt("demo:agent", "next task", "worker1")
        assert result.startswith("Error:")
        assert "load-buffer" in result

    def test_error_when_paste_buffer_fails(self, monkeypatch):
        """paste-buffer 실패 시 에러 반환."""

        class OkResult:
            returncode = 0
            stdout = "%1\n"
            stderr = ""

        class FailResult:
            returncode = 1
            stdout = ""
            stderr = "paste error"

        def fake_run(args, **kw):
            if "list-panes" in args:
                return OkResult()
            if "capture-pane" in args:
                r = OkResult()
                r.stdout = "Done.\n\u276f "
                return r
            if "load-buffer" in args:
                return OkResult()
            if "paste-buffer" in args:
                return FailResult()
            if "delete-buffer" in args:
                return OkResult()
            return OkResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1]))

        backend = TmuxBackend()
        result = backend.send_followup_prompt("demo:agent", "next task", "worker1")
        assert result.startswith("Error:")
        assert "paste-buffer" in result

    # --- Happy path ---

    def test_success_sends_prompt_via_buffer(self, monkeypatch):
        """정상 시나리오: idle 확인 -> buffer 전송 -> Enter 2회."""
        run_calls: list[list[str]] = []

        class OkResult:
            returncode = 0
            stdout = "%1\n"
            stderr = ""

        def fake_run(args, **kw):
            run_calls.append(args)
            if "capture-pane" in args:
                r = OkResult()
                r.stdout = "Done.\n\u276f "
                return r
            return OkResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1]))

        backend = TmuxBackend()
        result = backend.send_followup_prompt("demo:agent", "do next stage", "worker1")

        assert "Followup prompt sent" in result
        assert "worker1" in result

        # load-buffer, paste-buffer, send-keys(Enter) x2, delete-buffer 호출 확인
        load_calls = [c for c in run_calls if "load-buffer" in c]
        paste_calls = [c for c in run_calls if "paste-buffer" in c]
        enter_calls = [c for c in run_calls if c[-1:] == ["Enter"] and "send-keys" in c]
        delete_calls = [c for c in run_calls if "delete-buffer" in c]

        assert len(load_calls) == 1
        assert len(paste_calls) == 1
        assert len(enter_calls) == 2
        assert len(delete_calls) == 1

    def test_success_cleans_up_tmpfile(self, monkeypatch):
        """전송 후 임시 파일이 삭제되는지 확인."""
        created_files: list[str] = []
        original_named_temp = tempfile.NamedTemporaryFile

        class TrackingNamedTemp:
            def __init__(self, *a, **kw):
                self._f = original_named_temp(*a, **kw)
                created_files.append(self._f.name)

            def __enter__(self):
                self._f.__enter__()
                return self._f

            def __exit__(self, *a):
                return self._f.__exit__(*a)

        class OkResult:
            returncode = 0
            stdout = "%1\n"
            stderr = ""

        def fake_run(args, **kw):
            if "capture-pane" in args:
                r = OkResult()
                r.stdout = "Done.\n\u276f "
                return r
            return OkResult()

        monkeypatch.setattr("clawteam.spawn.tmux_backend.subprocess.run", fake_run)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.sleep", lambda *_: None)
        monkeypatch.setattr("clawteam.spawn.tmux_backend.time.monotonic", _make_monotonic_sequence([0, 0.1]))
        monkeypatch.setattr("clawteam.spawn.tmux_backend.tempfile.NamedTemporaryFile", TrackingNamedTemp)

        backend = TmuxBackend()
        backend.send_followup_prompt("demo:agent", "do next", "worker1")

        assert len(created_files) == 1
        assert not os.path.exists(created_files[0])


# ---------- test helpers ----------


def _make_monotonic_sequence(values: list[float]):
    """time.monotonic()를 지정된 값 시퀀스로 대체하는 callable 생성."""
    iterator = iter(values)
    last = [values[-1]]  # 마지막 값 반복용

    def fake_monotonic():
        try:
            return next(iterator)
        except StopIteration:
            return last[0]

    return fake_monotonic


def test_resolve_clawteam_executable_ignores_unrelated_argv0(monkeypatch, tmp_path):
    unrelated = tmp_path / "not-clawteam-review"
    unrelated.write_text("#!/bin/sh\n")
    resolved_bin = tmp_path / "bin" / "clawteam"
    resolved_bin.parent.mkdir(parents=True)
    resolved_bin.write_text("#!/bin/sh\n")

    monkeypatch.setattr(sys, "argv", [str(unrelated)])
    monkeypatch.setattr("clawteam.spawn.cli_env.shutil.which", lambda name: str(resolved_bin))

    assert resolve_clawteam_executable() == str(resolved_bin)
    assert build_spawn_path("/usr/bin:/bin").startswith(f"{resolved_bin.parent}:")


def test_resolve_clawteam_executable_ignores_relative_argv0_even_if_local_file_exists(
    monkeypatch, tmp_path
):
    local_shadow = tmp_path / "clawteam"
    local_shadow.write_text("#!/bin/sh\n")
    resolved_bin = tmp_path / "venv" / "bin" / "clawteam"
    resolved_bin.parent.mkdir(parents=True)
    resolved_bin.write_text("#!/bin/sh\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["clawteam"])
    monkeypatch.setattr("clawteam.spawn.cli_env.shutil.which", lambda name: str(resolved_bin))

    assert resolve_clawteam_executable() == str(resolved_bin)
    assert build_spawn_path("/usr/bin:/bin").startswith(f"{resolved_bin.parent}:")


def test_resolve_clawteam_executable_accepts_relative_path_with_explicit_directory(
    monkeypatch, tmp_path
):
    relative_bin = tmp_path / ".venv" / "bin" / "clawteam"
    relative_bin.parent.mkdir(parents=True)
    relative_bin.write_text("#!/bin/sh\n")
    fallback_bin = tmp_path / "fallback" / "clawteam"
    fallback_bin.parent.mkdir(parents=True)
    fallback_bin.write_text("#!/bin/sh\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["./.venv/bin/clawteam"])
    monkeypatch.setattr("clawteam.spawn.cli_env.shutil.which", lambda name: str(fallback_bin))

    assert resolve_clawteam_executable() == str(relative_bin.resolve())
    assert build_spawn_path("/usr/bin:/bin").startswith(f"{relative_bin.parent.resolve()}:")
