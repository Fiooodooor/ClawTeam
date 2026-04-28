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
