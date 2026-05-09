"""Tests for get_data_dir — project-local auto-discovery with walk-up."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Remove CLAWTEAM_DATA_DIR and point HOME at a scratch dir for these tests.

    The autouse ``isolated_data_dir`` fixture in conftest.py pre-creates
    ``tmp_path/.clawteam``. Remove it so walk-up tests don't spuriously pick it up.
    """
    monkeypatch.delenv("CLAWTEAM_DATA_DIR", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    stray = tmp_path / ".clawteam"
    if stray.is_dir():
        import shutil
        shutil.rmtree(stray)


def test_env_var_wins(tmp_path, monkeypatch):
    forced = tmp_path / "forced"
    monkeypatch.setenv("CLAWTEAM_DATA_DIR", str(forced))
    monkeypatch.chdir(tmp_path)

    from clawteam.team import models
    assert models.get_data_dir() == forced


def test_walks_up_from_cwd_to_find_project_dotclawteam(tmp_path, monkeypatch):
    project = tmp_path / "myrepo"
    (project / ".clawteam").mkdir(parents=True)
    nested = project / "src" / "deep" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    from clawteam.team import models
    assert models.get_data_dir() == project / ".clawteam"


def test_falls_back_to_home_when_no_project_found(tmp_path, monkeypatch):
    elsewhere = tmp_path / "nowhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    from clawteam.team import models
    result = models.get_data_dir()
    assert result == Path(os.environ["HOME"]) / ".clawteam"


def test_walks_up_stops_at_first_match(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (outer / ".clawteam").mkdir(parents=True)
    (inner / ".clawteam").mkdir(parents=True)
    start = inner / "src"
    start.mkdir()
    monkeypatch.chdir(start)

    from clawteam.team import models
    assert models.get_data_dir() == inner / ".clawteam"
