from __future__ import annotations

from pathlib import Path

import pytest

from clawteam.plane.config import PlaneConfig, load_plane_config, save_plane_config


def test_plane_config_defaults():
    cfg = PlaneConfig()
    assert cfg.url == ""
    assert cfg.api_key == ""
    assert cfg.workspace_slug == ""
    assert cfg.project_id == ""
    assert cfg.sync_enabled is False
    assert cfg.webhook_secret == ""
    assert cfg.webhook_port == 9091


def test_plane_config_from_dict():
    cfg = PlaneConfig(
        url="http://localhost:8082",
        api_key="pl_test_key",
        workspace_slug="my-workspace",
        project_id="abc123",
        sync_enabled=True,
    )
    assert cfg.url == "http://localhost:8082"
    assert cfg.api_key == "pl_test_key"
    assert cfg.workspace_slug == "my-workspace"
    assert cfg.project_id == "abc123"
    assert cfg.sync_enabled is True


def test_plane_config_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(tmp_path))
    cfg = PlaneConfig(
        url="http://localhost:8082",
        api_key="pl_test_key",
        workspace_slug="ws",
        project_id="proj1",
    )
    save_plane_config(cfg)
    loaded = load_plane_config()
    assert loaded.url == cfg.url
    assert loaded.api_key == cfg.api_key
    assert loaded.workspace_slug == cfg.workspace_slug
    assert loaded.project_id == cfg.project_id


def test_plane_config_in_clawteam_config():
    from clawteam.config import ClawTeamConfig

    cfg = ClawTeamConfig()
    assert hasattr(cfg, "plane")
    assert isinstance(cfg.plane, PlaneConfig)
