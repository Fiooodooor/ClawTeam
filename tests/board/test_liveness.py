"""Tests for the board liveness helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from clawteam.board import liveness


def _fake_run(stdout: str = "", returncode: int = 0):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=returncode,
            stdout=stdout,
            stderr="",
        )
    return runner


def test_tmux_windows_returns_window_names_when_session_exists():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run("leader\ncoder-1\n")):
        assert liveness.tmux_windows("my-swarm") == {"leader", "coder-1"}


def test_tmux_windows_returns_empty_when_session_missing():
    with patch("shutil.which", return_value="/usr/bin/tmux"), \
         patch("subprocess.run", side_effect=_fake_run(returncode=1)):
        assert liveness.tmux_windows("missing") == set()


def test_tmux_windows_returns_empty_when_tmux_not_installed():
    with patch("shutil.which", return_value=None):
        assert liveness.tmux_windows("any-team") == set()


def test_agents_online_counts_matching_members():
    with patch("clawteam.board.liveness.tmux_windows", return_value={"leader", "coder-1"}):
        online = liveness.agents_online("t", ["leader", "coder-1", "coder-2"])
    assert online == {"leader": True, "coder-1": True, "coder-2": False}
