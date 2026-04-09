"""Plane integration configuration."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from clawteam.team.models import get_data_dir


class PlaneConfig(BaseModel):
    """Configuration for Plane integration."""

    url: str = ""  # e.g. "http://localhost:8082"
    api_key: str = ""
    workspace_slug: str = ""
    project_id: str = ""
    sync_enabled: bool = False
    webhook_secret: str = ""
    webhook_port: int = 9091
    state_mapping: dict[str, str] = Field(default_factory=dict)


def _plane_config_path() -> Path:
    return get_data_dir() / "plane-config.json"


def load_plane_config() -> PlaneConfig:
    """Load Plane config from data dir. Returns defaults if not found."""
    p = _plane_config_path()
    if not p.exists():
        return PlaneConfig()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PlaneConfig.model_validate(data)
    except Exception:
        return PlaneConfig()


def save_plane_config(cfg: PlaneConfig) -> None:
    """Persist Plane config to data dir."""
    from clawteam.fileutil import atomic_write_text

    p = _plane_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, cfg.model_dump_json(indent=2))
