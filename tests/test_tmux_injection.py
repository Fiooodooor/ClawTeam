"""Tests for the tmux runtime injection safety guards."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from clawteam.spawn import tmux_backend


def _completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@pytest.mark.parametrize("cmd", ["bash", "zsh", "fish", "sh", "less", "vim", "fzf", "tmux"])
def test_pane_safe_to_inject_returns_false_for_shells_and_tuis(cmd):
    with patch("subprocess.run", return_value=_completed(stdout=f"{cmd}\n")):
        assert tmux_backend._pane_safe_to_inject("session:0") is False


@pytest.mark.parametrize(
    "cmd",
    ["claude", "codex", "gemini", "kimi", "qwen", "opencode", "nanobot", "openclaw", "pi", "node", "python"],
)
def test_pane_safe_to_inject_returns_true_for_known_agent_clis(cmd):
    with patch("subprocess.run", return_value=_completed(stdout=f"{cmd}\n")):
        assert tmux_backend._pane_safe_to_inject("session:0") is True


def test_pane_safe_to_inject_returns_false_when_tmux_query_fails():
    with patch("subprocess.run", return_value=_completed(returncode=1)):
        assert tmux_backend._pane_safe_to_inject("session:0") is False


def test_inject_runtime_message_refuses_on_unsafe_pane():
    backend = tmux_backend.TmuxBackend()
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%1\n")  # pane exists
        if "display-message" in cmd:
            return _completed(stdout="bash\n")  # but it's a shell
        return _completed()

    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=fake_run):
        ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is False
    assert "shell" in reason.lower() or "unsafe" in reason.lower()


def test_inject_uses_unique_buffer_name_per_call(monkeypatch):
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    tmux_backend._inject_prompt_via_buffer("session:0", "leader", "first")
    tmux_backend._inject_prompt_via_buffer("session:0", "leader", "second")

    buf_names = [
        cmd[cmd.index("-b") + 1]
        for cmd in calls
        if isinstance(cmd, list) and "-b" in cmd
    ]
    assert len(set(buf_names)) >= 2, f"buffer names collided: {buf_names}"


def test_inject_raises_when_load_buffer_fails(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "load-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    with pytest.raises(RuntimeError, match="load-buffer"):
        tmux_backend._inject_prompt_via_buffer("session:0", "leader", "x")


def test_inject_raises_when_paste_buffer_fails(monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if "paste-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    with pytest.raises(RuntimeError, match="paste-buffer"):
        tmux_backend._inject_prompt_via_buffer("session:0", "leader", "x")


def test_inject_runtime_message_returns_false_on_paste_failure(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%1\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        if "paste-buffer" in cmd:
            return _completed(returncode=1)
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is False
    assert "paste-buffer" in reason


def test_inject_uses_recorded_pane_id_when_available(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    backend._agents[("demo", "leader")] = {
        "target": "clawteam-demo:leader",
        "pane_id": "%42",
    }
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    seen_targets = []

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            seen_targets.append(cmd[cmd.index("-t") + 1])
            return _completed(stdout="%42\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        if "paste-buffer" in cmd or "send-keys" in cmd:
            seen_targets.append(cmd[cmd.index("-t") + 1])
            return _completed()
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, _ = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is True
    assert all(t == "%42" for t in seen_targets), seen_targets


def test_inject_falls_back_to_window_name_when_no_pane_id(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    envelope = MagicMock(summary="hi", source="w", target="leader",
                         channel="direct", priority="high",
                         evidence=[], recommended_next_action="",
                         payload={}, dedupe_key="d", created_at="t",
                         requires_injection=True)

    def fake_run(cmd, *args, **kwargs):
        if "list-panes" in cmd:
            return _completed(stdout="%99\n")
        if "display-message" in cmd:
            return _completed(stdout="claude\n")
        return _completed()

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/tmux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("time.sleep", lambda _x: None)

    ok, reason = backend.inject_runtime_message("demo", "leader", envelope)
    assert ok is True, reason


def test_list_running_returns_pane_id_and_team(monkeypatch):
    backend = tmux_backend.TmuxBackend()
    backend._agents[("demo", "leader")] = {
        "target": "clawteam-demo:leader",
        "pane_id": "%42",
    }
    backend._agents[("demo", "worker")] = {
        "target": "clawteam-demo:worker",
        "pane_id": "%43",
    }

    rows = backend.list_running()
    by_name = {r["name"]: r for r in rows}
    assert by_name["leader"]["pane_id"] == "%42"
    assert by_name["leader"]["team"] == "demo"
    assert by_name["worker"]["pane_id"] == "%43"
