"""Bootstrap helpers for persistent dev team operating system state."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from clawteam.devteam.models import (
    DevTeamBlueprint,
    DevTeamRuntimeBlueprint,
    DevTeamRuntimeState,
)
from clawteam.team.manager import TeamManager
from clawteam.team.models import get_data_dir


def devteam_dir(team_name: str, create: bool = True) -> Path:
    path = get_data_dir() / "teams" / team_name / "devteam"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> dict:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_runtime_blueprint(
    template_name: str,
    team_name: str,
    goal: str,
    leader: str,
    members: list[str],
    blueprint: DevTeamBlueprint,
) -> DevTeamRuntimeBlueprint:
    return DevTeamRuntimeBlueprint(
        template=template_name,
        team_name=team_name,
        goal=goal,
        leader=leader,
        members=members,
        blueprint=blueprint,
    )


def bootstrap_devteam(
    template_name: str,
    team_name: str,
    goal: str,
    leader: str,
    members: list[str],
    blueprint: DevTeamBlueprint,
) -> DevTeamRuntimeBlueprint:
    runtime = build_runtime_blueprint(
        template_name=template_name,
        team_name=team_name,
        goal=goal,
        leader=leader,
        members=members,
        blueprint=blueprint,
    )
    root = devteam_dir(team_name)
    _ensure_team_registry(team_name, leader, members, blueprint.summary)

    _write_json(root / "blueprint.json", runtime.model_dump(mode="json"))

    state = DevTeamRuntimeState(team_name=team_name)
    _write_json(root / "state.json", state.model_dump(mode="json"))

    _write_text(root / "README.md", build_team_readme(runtime))

    for protocol_key, protocol in blueprint.protocols.items():
        steps = "\n".join(f"- {step}" for step in protocol.steps)
        channels = ", ".join(protocol.channels) if protocol.channels else "(none)"
        _write_text(
            root / "protocols" / f"{protocol_key}.md",
            f"# {protocol.title}\n\n"
            f"- owner: {protocol.owner}\n"
            f"- when: {protocol.when}\n"
            f"- channels: {channels}\n\n"
            f"## Steps\n{steps}",
        )

    return runtime


def _ensure_team_registry(
    team_name: str,
    leader: str,
    members: list[str],
    description: str,
) -> None:
    user = os.environ.get("CLAWTEAM_USER", "")
    config = TeamManager.get_team(team_name)
    if config is None:
        TeamManager.create_team(
            name=team_name,
            leader_name=leader,
            leader_id=f"{team_name}-{leader}",
            description=description,
            user=user,
        )
    existing = {member.name for member in TeamManager.list_members(team_name)}
    for member in members:
        if member in existing:
            continue
        TeamManager.add_member(
            team_name,
            member_name=member,
            agent_id=f"{team_name}-{member}",
            agent_type="devteam-persona",
            user=user,
        )


def load_runtime_blueprint(team_name: str) -> DevTeamRuntimeBlueprint:
    path = devteam_dir(team_name, create=False) / "blueprint.json"
    if not path.exists():
        raise FileNotFoundError(
            f"DevTeam runtime not found for team '{team_name}'"
        )
    data = _read_json(path)
    return DevTeamRuntimeBlueprint.model_validate(data)


def load_runtime_state(team_name: str) -> DevTeamRuntimeState:
    path = devteam_dir(team_name, create=False) / "state.json"
    if not path.exists():
        raise FileNotFoundError(
            f"DevTeam runtime state not found for team '{team_name}'"
        )
    data = _read_json(path)
    return DevTeamRuntimeState.model_validate(data)


def save_runtime_state(state: DevTeamRuntimeState) -> None:
    _write_json(
        devteam_dir(state.team_name) / "state.json",
        state.model_dump(mode="json"),
    )


def build_team_readme(runtime: DevTeamRuntimeBlueprint) -> str:
    bp = runtime.blueprint
    channels = "\n".join(
        f"- #{ch.name}: {ch.purpose}" for ch in bp.channels
    )
    personas = "\n".join(
        f"- {p.agent} ({p.display_name}): {p.role}" for p in bp.personas
    )
    stages = "\n".join(
        f"- {sc.stage.value}: {sc.primary_owner} + {', '.join(sc.supporting_agents) or '(solo)'}"
        for sc in bp.workflow_stages
    )
    schedules = "\n".join(
        f"- {s.key}: {s.cadence} / {s.owner}" for s in bp.schedules
    )
    return (
        f"# {runtime.team_name} Dev Team\n\n"
        f"- template: {runtime.template}\n"
        f"- leader: {runtime.leader}\n"
        f"- goal: {runtime.goal or '(none)'}\n\n"
        f"## Channels\n{channels or '- (none)'}\n\n"
        f"## Personas\n{personas or '- (none)'}\n\n"
        f"## Sprint Stages\n{stages or '- (none)'}\n\n"
        f"## Schedules\n{schedules or '- (none)'}\n"
    )
