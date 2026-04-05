"""Bootstrap helpers for persistent investment operating system state."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

from clawteam.investment.models import (
    InvestmentBlueprint,
    InvestmentRuntimeBlueprint,
    InvestmentRuntimeState,
)
from clawteam.investment.slack import build_slack_manifest, to_yaml
from clawteam.team.models import get_data_dir


def investment_dir(team_name: str, create: bool = True) -> Path:
    path = get_data_dir() / "teams" / team_name / "investment"
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
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
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
    blueprint: InvestmentBlueprint,
) -> InvestmentRuntimeBlueprint:
    return InvestmentRuntimeBlueprint(
        template=template_name,
        team_name=team_name,
        goal=goal,
        leader=leader,
        members=members,
        blueprint=blueprint,
    )


def bootstrap_investment_team(
    template_name: str,
    team_name: str,
    goal: str,
    leader: str,
    members: list[str],
    blueprint: InvestmentBlueprint,
) -> InvestmentRuntimeBlueprint:
    runtime = build_runtime_blueprint(
        template_name=template_name,
        team_name=team_name,
        goal=goal,
        leader=leader,
        members=members,
        blueprint=blueprint,
    )
    root = investment_dir(team_name)
    _write_json(root / "blueprint.json", runtime.model_dump(mode="json"))
    state = InvestmentRuntimeState(
        team_name=team_name,
        strategy_states={
            strategy.strategy_id: strategy.lifecycle for strategy in blueprint.strategies
        },
        watchlists={"priority": [], "active": [], "archive": []},
    )
    _write_json(root / "state.json", state.model_dump(mode="json"))
    _write_text(root / "slack-manifest.yaml", to_yaml(build_slack_manifest(runtime)))
    _write_text(root / "README.md", build_team_readme(runtime))
    for strategy in blueprint.strategies:
        _write_json(
            root / "strategies" / f"{strategy.strategy_id}.json",
            strategy.model_dump(mode="json", by_alias=True),
        )
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


def load_runtime_blueprint(team_name: str) -> InvestmentRuntimeBlueprint:
    path = investment_dir(team_name, create=False) / "blueprint.json"
    if not path.exists():
        raise FileNotFoundError(f"Investment runtime not found for team '{team_name}'")
    data = _read_json(path)
    return InvestmentRuntimeBlueprint.model_validate(data)


def load_runtime_state(team_name: str) -> InvestmentRuntimeState:
    path = investment_dir(team_name, create=False) / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"Investment runtime state not found for team '{team_name}'")
    data = _read_json(path)
    return InvestmentRuntimeState.model_validate(data)


def save_runtime_state(state: InvestmentRuntimeState) -> None:
    _write_json(
        investment_dir(state.team_name) / "state.json",
        state.model_dump(mode="json"),
    )


def build_team_readme(runtime: InvestmentRuntimeBlueprint) -> str:
    blueprint = runtime.blueprint
    channels = "\n".join(f"- #{channel.name}: {channel.purpose}" for channel in blueprint.channels)
    strategies = "\n".join(
        f"- {strategy.strategy_id} ({strategy.lifecycle.value}) - {strategy.name}"
        for strategy in blueprint.strategies
    )
    schedules = "\n".join(
        f"- {schedule.key}: {schedule.cadence} / {schedule.owner}"
        for schedule in blueprint.schedules
    )
    return (
        f"# {runtime.team_name} Investment OS\n\n"
        f"- template: {runtime.template}\n"
        f"- leader: {runtime.leader}\n"
        f"- goal: {runtime.goal or '(none)'}\n"
        f"- ceo mode: {blueprint.ceo_mode}\n"
        f"- execution mode: {blueprint.execution.default_mode.value}\n\n"
        f"## Channels\n{channels or '- (none)'}\n\n"
        f"## Strategies\n{strategies or '- (none)'}\n\n"
        f"## Schedules\n{schedules or '- (none)'}\n"
    )
