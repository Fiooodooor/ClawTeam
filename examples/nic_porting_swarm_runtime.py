from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from clawteam.team.manager import TeamManager
from clawteam.team.models import TaskPriority, TaskStatus
from clawteam.team.tasks import TaskStore
from clawteam.workspace.manager import WorkspaceManager
from clawteam.spawn.registry import is_agent_alive


@dataclass(frozen=True)
class ChapterSpec:
    key: str
    index: int
    title: str
    objective: str


@dataclass(frozen=True)
class RoleSpec:
    name: str
    subject: str
    priority: str
    chapter_key: str
    depends_on: list[str]


CHAPTER_SPECS: list[ChapterSpec] = [
    ChapterSpec(
        key="scope-baseline",
        index=1,
        title="Chapter 1 - Scope and Baseline",
        objective="Freeze baseline commit, define hard constraints, and scope acceptance gates.",
    ),
    ChapterSpec(
        key="kpi-mapping",
        index=2,
        title="Chapter 2 - Dependency and KPI Mapping",
        objective="Map Linux APIs to FreeBSD LinuxKPI/iflib seam contracts.",
    ),
    ChapterSpec(
        key="seam-design",
        index=3,
        title="Chapter 3 - Seam Layer Design",
        objective="Create wrappers and compatibility seams with minimal Linux source edits.",
    ),
    ChapterSpec(
        key="incremental-port",
        index=4,
        title="Chapter 4 - Incremental Porting Execution",
        objective="Port in micro-slices and validate each subsystem before expansion.",
    ),
    ChapterSpec(
        key="gates",
        index=5,
        title="Chapter 5 - Build, Test, and Performance Gates",
        objective="Enforce compile, test, and perf gates continuously.",
    ),
    ChapterSpec(
        key="merge-sync",
        index=6,
        title="Chapter 6 - Merge and Upstream Sync Strategy",
        objective="Prepare merges and preserve future upstream synchronization.",
    ),
    ChapterSpec(
        key="future-targets",
        index=7,
        title="Chapter 7 - Future Target Extension",
        objective="Ensure new OS targets extend shim layers without core rewrites.",
    ),
]


ROLE_SPECS: list[RoleSpec] = [
    RoleSpec(
        name="linux-analyst",
        subject="Map Linux driver dependencies and data-path entry points",
        priority="high",
        chapter_key="scope-baseline",
        depends_on=[],
    ),
    RoleSpec(
        name="kpi-mapper",
        subject="Define FreeBSD LinuxKPI and iflib compatibility mapping seams",
        priority="high",
        chapter_key="kpi-mapping",
        depends_on=["linux-analyst"],
    ),
    RoleSpec(
        name="seam-architect",
        subject="Design #ifdef trees, wrappers, weak symbols, and isolated shim headers",
        priority="high",
        chapter_key="seam-design",
        depends_on=["kpi-mapper"],
    ),
    RoleSpec(
        name="porting-engineer",
        subject="Implement incremental low-touch Linux to FreeBSD port slices",
        priority="high",
        chapter_key="incremental-port",
        depends_on=["seam-architect"],
    ),
    RoleSpec(
        name="build-ci",
        subject="Create deterministic compile, unit-test, and static-analysis gates",
        priority="medium",
        chapter_key="gates",
        depends_on=["porting-engineer"],
    ),
    RoleSpec(
        name="perf-verifier",
        subject="Measure overhead and verify regression budgets per slice",
        priority="medium",
        chapter_key="gates",
        depends_on=["build-ci"],
    ),
    RoleSpec(
        name="integration-reviewer",
        subject="Validate merge readiness and future target extensibility policy",
        priority="medium",
        chapter_key="merge-sync",
        depends_on=["perf-verifier"],
    ),
]


class RuntimeState(TypedDict):
    team_name: str
    goal: str
    run_id: str
    resume: bool
    driver_repo: str
    linux_driver_path: str
    freebsd_target_path: str
    backend: str
    agent_command: list[str]
    output_dir: str
    poll_interval: int
    timeout_seconds: int
    max_iterations: int
    package_patches: bool
    auto_cleanup: bool
    cleanup_team: bool
    role_to_task_id: dict[str, str]
    spawned_agents: list[str]
    chapters: list[dict[str, Any]]
    iteration_events: list[dict[str, Any]]
    packaging_outputs: list[dict[str, str]]
    observations: list[str]
    llm_enabled: bool
    checkpoint_path: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chapter_map() -> dict[str, ChapterSpec]:
    return {ch.key: ch for ch in CHAPTER_SPECS}


def run(cmd: list[str], cwd: str | None = None, fail: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command. Used only for `clawteam spawn` and `git`."""
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if fail and proc.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(cmd)
            + "\nstdout:\n"
            + proc.stdout
            + "\nstderr:\n"
            + proc.stderr
        )
    return proc


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Missing executable: {name}")


def persist_checkpoint(state: RuntimeState) -> None:
    path = Path(state["checkpoint_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "team_name": state["team_name"],
        "goal": state["goal"],
        "run_id": state["run_id"],
        "role_to_task_id": state["role_to_task_id"],
        "spawned_agents": state["spawned_agents"],
        "chapters": state["chapters"],
        "iteration_events": state["iteration_events"],
        "packaging_outputs": state["packaging_outputs"],
        "observations": state["observations"],
        "updated_at": _utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_checkpoint_if_exists(state: RuntimeState) -> None:
    if not state["resume"]:
        return

    path = Path(state["checkpoint_path"])
    if not path.exists():
        state["observations"].append("Resume enabled but no checkpoint file found")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ["role_to_task_id", "spawned_agents", "chapters", "iteration_events", "packaging_outputs", "observations"]:
        if key in data and isinstance(data[key], list if key != "role_to_task_id" else dict):
            state[key] = data[key]

    if isinstance(data.get("run_id"), str) and data.get("run_id"):
        state["run_id"] = data["run_id"]

    state["observations"].append("Loaded checkpoint state")


def maybe_prompt_refiner() -> Any | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None

    model = os.getenv("PORTING_MODEL", "gpt-5")
    llm = ChatOpenAI(model=model, temperature=0)
    prompt = PromptTemplate.from_template(
        """
You are defining one worker mission in an elite NIC portability swarm.

Global goal:
{goal}
Linux path:
{linux_driver_path}
FreeBSD path:
{freebsd_target_path}
Role:
{role}
Role subject:
{subject}
Chapter:
{chapter_title}
Chapter objective:
{chapter_objective}

Return concise executable instructions with:
1) strict seam-first policy
2) minimal Linux source touch
3) concrete done criteria
4) at least 3 explicit shell commands
"""
    )
    return prompt | llm | StrOutputParser()


def build_worker_task(
    role: RoleSpec,
    chapter: ChapterSpec,
    goal: str,
    linux_driver_path: str,
    freebsd_target_path: str,
    chain: Any | None,
) -> str:
    base = (
        f"Role: {role.name}. Chapter: {chapter.title}. Mission: {role.subject}. "
        "Strictly use seam-first architecture with #ifdef trees, wrappers, weak symbols, and isolated KPI layers. "
        "Never perform broad Linux source rewrites; touch only minimum required lines. "
        "Run tests and compile gates for each micro-slice. "
        "After completion, update your task status and send a concise summary to orchestrator."
    )

    if chain is None:
        return base

    refined = chain.invoke(
        {
            "goal": goal,
            "linux_driver_path": linux_driver_path,
            "freebsd_target_path": freebsd_target_path,
            "role": role.name,
            "subject": role.subject,
            "chapter_title": chapter.title,
            "chapter_objective": chapter.objective,
        }
    )
    return refined.strip() if refined and refined.strip() else base


def build_chapters(goal: str, linux_driver_path: str, freebsd_target_path: str) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for ch in CHAPTER_SPECS:
        chapters.append(
            {
                "key": ch.key,
                "index": ch.index,
                "title": ch.title,
                "objective": ch.objective,
                "scope": {
                    "goal": goal,
                    "linux_driver_path": linux_driver_path,
                    "freebsd_target_path": freebsd_target_path,
                },
                "status": "planned",
            }
        )
    return chapters


def _priority_enum(value: str) -> TaskPriority:
    return TaskPriority(value)


def _chapter_for_role(role: RoleSpec) -> ChapterSpec:
    cmap = _chapter_map()
    if role.chapter_key not in cmap:
        raise RuntimeError(f"Role {role.name} has unknown chapter key: {role.chapter_key}")
    return cmap[role.chapter_key]


def _task_status_map(team_name: str) -> dict[str, dict[str, Any]]:
    """Build task_id → task dict map using direct Python API."""
    store = TaskStore(team_name)
    tasks = store.list_tasks()
    result: dict[str, dict[str, Any]] = {}
    for task in tasks:
        result[task.id] = {
            "id": task.id,
            "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
            "owner": task.owner,
            "metadata": task.metadata,
        }
    return result


def _derive_resume_task_map(team_name: str, run_id: str) -> dict[str, str]:
    """Recover role → task_id mapping from existing tasks using Python API."""
    store = TaskStore(team_name)
    tasks = store.list_tasks()
    discovered: dict[str, str] = {}
    role_names = {r.name for r in ROLE_SPECS}
    for task in tasks:
        owner = task.owner or ""
        if owner not in role_names:
            continue
        meta = task.metadata or {}
        meta_run_id = str(meta.get("run_id", ""))
        if not meta_run_id or meta_run_id == run_id:
            discovered[owner] = task.id
    return {k: v for k, v in discovered.items() if v}


def _chapter_progress(team_name: str) -> dict[str, dict[str, int]]:
    """Get per-chapter task progress using Python API."""
    store = TaskStore(team_name)
    tasks = store.list_tasks()
    progress: dict[str, dict[str, int]] = {}
    for task in tasks:
        meta = task.metadata or {}
        chapter_key = str(meta.get("chapter_key", "unassigned"))
        status = task.status.value if hasattr(task.status, 'value') else str(task.status)
        if chapter_key not in progress:
            progress[chapter_key] = {"pending": 0, "in_progress": 0, "blocked": 0, "completed": 0}
        progress[chapter_key][status] = progress[chapter_key].get(status, 0) + 1
    return progress


def _is_task_terminal(status: str) -> bool:
    return status == "completed"


def _startup_commands_text(state: RuntimeState) -> str:
    """Return the full mandatory startup command sequence."""
    agent_exe = state["agent_command"][0] if state["agent_command"] else "openclaw"
    return textwrap.dedent(f"""\
        # ── Mandatory startup commands ──────────────────────────────
        # 1. System dependencies
        sudo apt-get install -y git tmux

        # 2. Python project dependencies (inside project root)
        cd /root/claw-team && pipenv install --dev

        # 3. Ensure ClawTeam data directory
        mkdir -p ~/.clawteam

        # 4. Verify agent CLI
        which {agent_exe}

        # 5. Verify MCP server starts
        pipenv run clawteam-mcp --help

        # 6. Verify ClawTeam config
        clawteam config show

        # 7. Run the orchestrator
        cd /root/claw-team && pipenv run python examples/nic_porting_swarm_runtime.py \\
            --driver-repo /path/to/your/driver-repo \\
            --linux-driver-path drivers/net/ethernet/intel/ixgbe \\
            --freebsd-target-path sys/dev/ixgbe
        # ────────────────────────────────────────────────────────────
    """)


def node_preflight(state: RuntimeState) -> RuntimeState:
    """Comprehensive preflight: verify all prerequisites before execution."""
    missing: list[str] = []
    fixes: list[str] = []

    # --- executables ---
    for exe in ["git", "clawteam"]:
        if shutil.which(exe) is None:
            missing.append(exe)
            fixes.append(f"sudo apt-get install -y {exe}")

    if state["backend"] == "tmux" and shutil.which("tmux") is None:
        missing.append("tmux")
        fixes.append("sudo apt-get install -y tmux")

    if not state["agent_command"]:
        raise RuntimeError("agent-command is empty")
    agent_exe = state["agent_command"][0]
    if shutil.which(agent_exe) is None:
        missing.append(agent_exe)
        fixes.append(f"# Install the agent CLI: {agent_exe}")

    # --- driver repo ---
    repo_path = Path(state["driver_repo"])
    if not repo_path.exists():
        missing.append(f"driver-repo ({state['driver_repo']})")
        fixes.append(f"git clone <upstream-url> {state['driver_repo']}")

    # --- ClawTeam data dir ---
    data_dir = Path.home() / ".clawteam"
    if not data_dir.exists():
        missing.append("~/.clawteam directory")
        fixes.append("mkdir -p ~/.clawteam")

    # --- Python deps ---
    try:
        import langgraph  # noqa: F401
    except ImportError:
        missing.append("langgraph Python package")
        fixes.append("pipenv install langgraph")

    if missing:
        banner = "\n".join(
            [
                "",
                "=" * 60,
                " PREFLIGHT FAILED — missing prerequisites",
                "=" * 60,
                "",
            ]
            + [f"  ✗ {m}" for m in missing]
            + [
                "",
                "Fix commands:",
            ]
            + [f"  $ {f}" for f in fixes]
            + [
                "",
                "Full startup sequence:",
                _startup_commands_text(state),
            ]
        )
        raise RuntimeError(banner)

    load_checkpoint_if_exists(state)
    state["observations"].append("Preflight checks passed")
    persist_checkpoint(state)
    return state


def node_bootstrap_team(state: RuntimeState) -> RuntimeState:
    """Create team via direct Python API. Idempotent."""
    team_name = state["team_name"]
    existing = TeamManager.get_team(team_name)
    if existing is not None:
        state["observations"].append(f"Team already exists: {team_name}")
    else:
        TeamManager.create_team(
            name=team_name,
            leader_name="orchestrator",
            leader_id=f"orchestrator-{state['run_id']}",
            description=state["goal"],
        )
        state["observations"].append(f"Team created: {team_name}")
    persist_checkpoint(state)
    return state


def node_generate_chapters(state: RuntimeState) -> RuntimeState:
    if not state["chapters"]:
        state["chapters"] = build_chapters(
            goal=state["goal"],
            linux_driver_path=state["linux_driver_path"],
            freebsd_target_path=state["freebsd_target_path"],
        )
        state["observations"].append("Generated chapter plan automatically")
    else:
        state["observations"].append("Using chapter plan from checkpoint")

    persist_checkpoint(state)
    return state


def node_reconcile_tasks(state: RuntimeState) -> RuntimeState:
    team = state["team_name"]

    store = TaskStore(team)

    if state["resume"] and not state["role_to_task_id"]:
        state["role_to_task_id"] = _derive_resume_task_map(team, state["run_id"])
        if state["role_to_task_id"]:
            state["observations"].append("Recovered role-to-task mapping from existing tasks")

    for role in ROLE_SPECS:
        if role.name in state["role_to_task_id"]:
            continue

        chapter = _chapter_for_role(role)
        blocked_ids = [state["role_to_task_id"][dep] for dep in role.depends_on if dep in state["role_to_task_id"]]

        metadata = {
            "run_id": state["run_id"],
            "role": role.name,
            "chapter_key": chapter.key,
            "chapter_index": chapter.index,
            "chapter_title": chapter.title,
            "chapter_objective": chapter.objective,
            "governance_policy": "strict_phase_metadata",
            "created_at": _utc_now(),
        }

        task = store.create(
            subject=role.subject,
            description=(
                f"Role={role.name}; Chapter={chapter.title}; "
                "Policy=seam-first,minimal-touch,incremental gates"
            ),
            owner=role.name,
            priority=_priority_enum(role.priority),
            blocked_by=blocked_ids,
            metadata=metadata,
        )
        state["role_to_task_id"][role.name] = task.id

    state["observations"].append("Task graph reconciled with chapter metadata")
    persist_checkpoint(state)
    return state


def node_spawn_workers(state: RuntimeState) -> RuntimeState:
    chain = maybe_prompt_refiner()
    state["llm_enabled"] = chain is not None

    team = state["team_name"]
    task_map = _task_status_map(team)

    for role in ROLE_SPECS:
        task_id = state["role_to_task_id"].get(role.name, "")
        if not task_id:
            continue

        status = str(task_map.get(task_id, {}).get("status", "pending"))
        if _is_task_terminal(status):
            continue

        alive = is_agent_alive(team, role.name)
        if alive is True:
            if role.name not in state["spawned_agents"]:
                state["spawned_agents"].append(role.name)
            continue

        chapter = _chapter_for_role(role)
        worker_prompt = build_worker_task(
            role=role,
            chapter=chapter,
            goal=state["goal"],
            linux_driver_path=state["linux_driver_path"],
            freebsd_target_path=state["freebsd_target_path"],
            chain=chain,
        )

        cmd = ["clawteam", "spawn", state["backend"]] + state["agent_command"] + [
            "--team",
            team,
            "--agent-name",
            role.name,
            "--task",
            worker_prompt,
            "--repo",
            state["driver_repo"],
        ]

        run(cmd, cwd=state["driver_repo"], fail=True)
        if role.name not in state["spawned_agents"]:
            state["spawned_agents"].append(role.name)

    state["observations"].append("Workers spawned or reconciled")
    persist_checkpoint(state)
    return state


def node_monitor_iterations(state: RuntimeState) -> RuntimeState:
    """Poll task completion using direct Python API."""
    team = state["team_name"]
    store = TaskStore(team)
    poll = state["poll_interval"]
    timeout = state["timeout_seconds"]
    max_iter = state["max_iterations"]

    started = time.time()
    iteration = 0

    while True:
        iteration += 1
        tasks = store.list_tasks()
        total = len(tasks)
        counts: dict[str, int] = {"pending": 0, "in_progress": 0, "blocked": 0, "completed": 0}
        for task in tasks:
            status_val = task.status.value if hasattr(task.status, 'value') else str(task.status)
            counts[status_val] = counts.get(status_val, 0) + 1

        chapter_counts = _chapter_progress(team)

        # --- dead-agent detection ---
        dead_agents: list[str] = []
        for role in ROLE_SPECS:
            if role.name in state["spawned_agents"]:
                alive = is_agent_alive(team, role.name)
                if alive is False:
                    dead_agents.append(role.name)
        if dead_agents:
            event_note = f"Dead agents detected: {dead_agents}"
            state["observations"].append(event_note)

        event = {
            "iteration": iteration,
            "elapsed_seconds": int(time.time() - started),
            "counts": counts,
            "chapter_counts": chapter_counts,
        }
        state["iteration_events"].append(event)

        if counts.get("completed", 0) == total and total > 0:
            state["observations"].append("All tasks completed")
            break

        if iteration >= max_iter:
            state["observations"].append("Reached max iterations before completion")
            break

        if int(time.time() - started) >= timeout:
            state["observations"].append("Reached timeout before completion")
            break

        persist_checkpoint(state)
        time.sleep(poll)

    persist_checkpoint(state)
    return state


def node_package_patches(state: RuntimeState) -> RuntimeState:
    if not state["package_patches"]:
        state["observations"].append("Patch packaging skipped by configuration")
        return state

    ws_mgr = WorkspaceManager.try_create(Path(state["driver_repo"]))
    if ws_mgr is None:
        state["observations"].append("Patch packaging skipped: not a git repository")
        return state

    workspaces = ws_mgr.list_workspaces(state["team_name"])
    package_root = Path(state["output_dir"]).resolve() / "patches"
    package_root.mkdir(parents=True, exist_ok=True)

    for ws in workspaces:
        role_dir = package_root / ws.agent_name
        role_dir.mkdir(parents=True, exist_ok=True)

        diff_path = role_dir / f"{ws.agent_name}.patch"
        log_path = role_dir / f"{ws.agent_name}.log"

        diff_proc = run(
            [
                "git",
                "--no-pager",
                "diff",
                "--binary",
                f"{ws.base_branch}..{ws.branch_name}",
            ],
            cwd=state["driver_repo"],
            fail=False,
        )
        diff_path.write_text(diff_proc.stdout or "", encoding="utf-8")

        log_proc = run(
            [
                "git",
                "--no-pager",
                "log",
                "--oneline",
                f"{ws.base_branch}..{ws.branch_name}",
            ],
            cwd=state["driver_repo"],
            fail=False,
        )
        log_path.write_text(log_proc.stdout or "", encoding="utf-8")

        state["packaging_outputs"].append(
            {
                "agent": ws.agent_name,
                "branch": ws.branch_name,
                "patch": str(diff_path),
                "log": str(log_path),
            }
        )

    tar_path = Path(state["output_dir"]).resolve() / "patches.tar.gz"
    with tarfile.open(tar_path, mode="w:gz") as tar:
        tar.add(package_root, arcname="patches")

    state["packaging_outputs"].append({"archive": str(tar_path)})
    state["observations"].append("Packaged role patch sets")
    persist_checkpoint(state)
    return state


def node_cleanup(state: RuntimeState) -> RuntimeState:
    if not state["auto_cleanup"]:
        state["observations"].append("Auto-cleanup skipped")
        return state

    ws_mgr = WorkspaceManager.try_create(Path(state["driver_repo"]))
    if ws_mgr is not None:
        try:
            ws_mgr.cleanup_team(state["team_name"])
            state["observations"].append("Workspace cleanup done")
        except Exception as exc:
            state["observations"].append(f"Workspace cleanup failed: {exc}")

    if state["cleanup_team"]:
        try:
            TeamManager.cleanup(state["team_name"])
            state["observations"].append("Team cleanup done")
        except Exception as exc:
            state["observations"].append(f"Team cleanup failed: {exc}")

    persist_checkpoint(state)
    return state


def node_write_artifacts(state: RuntimeState) -> RuntimeState:
    out_dir = Path(state["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_json = out_dir / "runtime_summary.json"
    summary_md = out_dir / "runtime_summary.md"

    payload = {
        "team_name": state["team_name"],
        "goal": state["goal"],
        "run_id": state["run_id"],
        "driver_repo": state["driver_repo"],
        "linux_driver_path": state["linux_driver_path"],
        "freebsd_target_path": state["freebsd_target_path"],
        "backend": state["backend"],
        "agent_command": state["agent_command"],
        "llm_enabled": state["llm_enabled"],
        "resume": state["resume"],
        "role_to_task_id": state["role_to_task_id"],
        "spawned_agents": state["spawned_agents"],
        "chapters": state["chapters"],
        "iteration_events": state["iteration_events"],
        "packaging_outputs": state["packaging_outputs"],
        "observations": state["observations"],
        "generated_at_epoch": int(time.time()),
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# NIC Porting Swarm Runtime Summary")
    lines.append("")
    lines.append(f"Team: {state['team_name']}")
    lines.append(f"Run ID: {state['run_id']}")
    lines.append(f"Backend: {state['backend']}")
    lines.append(f"Agent command: {' '.join(state['agent_command'])}")
    lines.append(f"LLM refinement: {'enabled' if state['llm_enabled'] else 'disabled'}")
    lines.append(f"Resume mode: {'on' if state['resume'] else 'off'}")
    lines.append("")

    lines.append("## Chapters")
    lines.append("")
    for chapter in state["chapters"]:
        lines.append(f"- {chapter['index']}. {chapter['title']} [{chapter['status']}]")
    lines.append("")

    lines.append("## Role To Task")
    lines.append("")
    for role, task_id in state["role_to_task_id"].items():
        lines.append(f"- {role}: {task_id}")
    lines.append("")

    lines.append("## Iteration Events")
    lines.append("")
    for event in state["iteration_events"]:
        c = event["counts"]
        lines.append(
            "- Iteration "
            + str(event["iteration"])
            + ": elapsed="
            + str(event["elapsed_seconds"])
            + "s, pending="
            + str(c.get("pending", 0))
            + ", in_progress="
            + str(c.get("in_progress", 0))
            + ", blocked="
            + str(c.get("blocked", 0))
            + ", completed="
            + str(c.get("completed", 0))
        )
    lines.append("")

    lines.append("## Patch Packaging")
    lines.append("")
    if state["packaging_outputs"]:
        for item in state["packaging_outputs"]:
            if "archive" in item:
                lines.append(f"- Archive: {item['archive']}")
            else:
                lines.append(
                    f"- Agent={item.get('agent', '')}, branch={item.get('branch', '')}, "
                    f"patch={item.get('patch', '')}, log={item.get('log', '')}"
                )
    else:
        lines.append("- No packaged patches")
    lines.append("")

    lines.append("## Observations")
    lines.append("")
    for obs in state["observations"]:
        lines.append(f"- {obs}")

    summary_md.write_text("\n".join(lines), encoding="utf-8")
    state["observations"].append(f"Wrote {summary_json}")
    state["observations"].append(f"Wrote {summary_md}")
    persist_checkpoint(state)
    return state


def node_finish(state: RuntimeState) -> RuntimeState:
    return state


def build_graph() -> Any:
    graph = StateGraph(RuntimeState)
    graph.add_node("preflight", node_preflight)
    graph.add_node("bootstrap_team", node_bootstrap_team)
    graph.add_node("generate_chapters", node_generate_chapters)
    graph.add_node("reconcile_tasks", node_reconcile_tasks)
    graph.add_node("spawn_workers", node_spawn_workers)
    graph.add_node("monitor_iterations", node_monitor_iterations)
    graph.add_node("package_patches", node_package_patches)
    graph.add_node("cleanup", node_cleanup)
    graph.add_node("write_artifacts", node_write_artifacts)
    graph.add_node("finish", node_finish)

    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "bootstrap_team")
    graph.add_edge("bootstrap_team", "generate_chapters")
    graph.add_edge("generate_chapters", "reconcile_tasks")
    graph.add_edge("reconcile_tasks", "spawn_workers")
    graph.add_edge("spawn_workers", "monitor_iterations")
    graph.add_edge("monitor_iterations", "package_patches")
    graph.add_edge("package_patches", "cleanup")
    graph.add_edge("cleanup", "write_artifacts")
    graph.add_edge("write_artifacts", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-orchestrate NIC porting swarm with chapter governance, resume checkpoints, "
            "patch packaging, and optional cleanup"
        )
    )
    parser.add_argument("--team", default="nic-port-runtime", help="ClawTeam team name")
    parser.add_argument("--goal", required=True, help="Global mission goal")
    parser.add_argument("--run-id", default="", help="Run identifier (auto-generated if omitted)")
    parser.add_argument("--resume", action="store_true", help="Resume from existing checkpoint and team/task state")
    parser.add_argument("--driver-repo", required=True, help="Path to driver repository")
    parser.add_argument("--linux-driver-path", required=True, help="Linux driver source path")
    parser.add_argument("--freebsd-target-path", required=True, help="FreeBSD target source path")
    parser.add_argument("--backend", choices=["tmux", "subprocess"], default="tmux")
    parser.add_argument(
        "--agent-command",
        nargs="+",
        default=["openclaw"],
        help="Worker CLI command, for example openclaw or claude",
    )
    parser.add_argument("--poll-interval", type=int, default=20, help="Monitor poll interval in seconds")
    parser.add_argument("--timeout-seconds", type=int, default=3600, help="Max monitor runtime")
    parser.add_argument("--max-iterations", type=int, default=120, help="Max monitor iterations")
    parser.add_argument("--output-dir", default="artifacts/nic_porting_runtime")
    parser.add_argument(
        "--package-patches",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Package per-role patch and commit logs",
    )
    parser.add_argument(
        "--auto-cleanup",
        action="store_true",
        help="Cleanup workspaces after packaging",
    )
    parser.add_argument(
        "--cleanup-team",
        action="store_true",
        help="Also delete team state (implies --auto-cleanup behavior for team artifacts)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = args.run_id.strip() or datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    checkpoint_path = out_dir / "runtime_checkpoint.json"

    state: RuntimeState = {
        "team_name": args.team,
        "goal": args.goal,
        "run_id": run_id,
        "resume": bool(args.resume),
        "driver_repo": str(Path(args.driver_repo).resolve()),
        "linux_driver_path": args.linux_driver_path,
        "freebsd_target_path": args.freebsd_target_path,
        "backend": args.backend,
        "agent_command": list(args.agent_command),
        "output_dir": str(out_dir),
        "poll_interval": args.poll_interval,
        "timeout_seconds": args.timeout_seconds,
        "max_iterations": args.max_iterations,
        "package_patches": bool(args.package_patches),
        "auto_cleanup": bool(args.auto_cleanup or args.cleanup_team),
        "cleanup_team": bool(args.cleanup_team),
        "role_to_task_id": {},
        "spawned_agents": [],
        "chapters": [],
        "iteration_events": [],
        "packaging_outputs": [],
        "observations": [],
        "llm_enabled": False,
        "checkpoint_path": str(checkpoint_path),
    }

    workflow = build_graph()
    try:
        final_state = workflow.invoke(state)
    except Exception as exc:
        print(f"Runtime failure: {exc}", file=sys.stderr)
        return 1

    final_out_dir = Path(final_state["output_dir"]).resolve()
    print("Swarm runtime orchestration completed")
    print(f"- {final_out_dir / 'runtime_summary.json'}")
    print(f"- {final_out_dir / 'runtime_summary.md'}")
    print(f"- {final_out_dir / 'runtime_checkpoint.json'}")
    if final_state["package_patches"]:
        print(f"- {final_out_dir / 'patches.tar.gz'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
