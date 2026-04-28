"""Runtime installation and version helpers for the dashboard."""

from __future__ import annotations

import json
import platform
import re
import shutil
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path

from clawteam import __version__

PYPI_URL = "https://pypi.org/pypi/clawteam/json"


def get_runtime_status(timeout: float = 4.0) -> dict:
    """Return local ClawTeam runtime status for the Web/Electron dashboard."""

    current_version = _installed_version()
    latest_version = _latest_pypi_version(timeout=timeout)
    command_path = _resolve_command_path()
    return {
        "installed": bool(current_version or command_path),
        "current_version": current_version,
        "latest_version": latest_version,
        "upgrade_available": _is_newer(latest_version, current_version),
        "command_path": command_path,
        "install_root": str(Path.home() / ".clawteam"),
        "platform": platform.system().lower(),
        "source": "pypi",
    }


def _installed_version() -> str:
    try:
        return metadata.version("clawteam")
    except metadata.PackageNotFoundError:
        return __version__


def _latest_pypi_version(timeout: float) -> str | None:
    try:
        req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        version = payload.get("info", {}).get("version")
        return str(version) if version else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _resolve_command_path() -> str:
    candidates = [
        Path.home() / ".clawteam" / ".venv" / "bin" / "clawteam",
        Path.home() / ".local" / "bin" / "clawteam",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("clawteam") or ""


def _version_key(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts[:4])


def _is_newer(latest: str | None, current: str | None) -> bool:
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    return bool(latest_key and current_key and latest_key > current_key)
