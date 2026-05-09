"""Detects which team members have a live tmux session/window."""

from __future__ import annotations

import shutil
import subprocess

from clawteam.spawn.tmux_backend import TmuxBackend


def tmux_windows(team_name: str) -> set[str]:
    """Return the set of window names in the team's tmux session.

    Returns an empty set when tmux is missing, the session does not exist,
    or any subprocess error occurs. Never raises.
    """
    if not shutil.which("tmux"):
        return set()

    session = TmuxBackend.session_name(team_name)
    try:
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return set()

    if result.returncode != 0:
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def agents_online(team_name: str, member_names: list[str]) -> dict[str, bool]:
    """Map each member name → whether a tmux window of the same name is live."""
    windows = tmux_windows(team_name)
    return {name: name in windows for name in member_names}
