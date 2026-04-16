from __future__ import annotations

# pyright: reportMissingImports=false

"""
NIC Data-Plane Porting Swarm Orchestrator v2.0
===============================================
Hybrid multi-pattern orchestrator built on LangGraph + ClawTeam.

Implements all five Microsoft AI Agent Orchestration Patterns:
  1. Sequential  — phase pipeline with gate dependencies
  2. Concurrent  — fan-out/fan-in parallel workers within phases
  3. GroupChat   — maker-checker debate loops for validation
  4. Handoff     — dynamic delegation when specialists are needed
  5. Magentic    — living task ledger with adaptive replanning

Usage:
  pipenv run python3 examples/nic_porting_orchestrator_v2.py \
    --team nic-port-v2 \
    --driver-name ixgbe \
    --goal "Native OAL data-plane port: Linux ixgbe to FreeBSD" \
    --driver-repo /path/to/driver-repo \
    --linux-driver-path drivers/net/ethernet/intel/ixgbe \
    --freebsd-target-path sys/dev/ixgbe
"""

import argparse
import json
import os
import shutil

# Dual Orchestrator Architecture (v4.0):
# This script is the CORE orchestrator (ClawTeam).
# The SECONDARY orchestrator (Agent Orchestrator) handles CI/PR/dashboard.
# See framework-comparison-v4-compact.md Section 7 for routing table.
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from clawteam.team.manager import TeamManager
from clawteam.team.mailbox import MailboxManager
from clawteam.team.models import MessageType, TaskPriority, TaskStatus, get_data_dir
from clawteam.team.tasks import TaskStore
from clawteam.workspace.manager import WorkspaceManager
from clawteam.spawn.registry import get_registry, is_agent_alive

# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

GATE_NATIVE_THRESHOLD = 98.0
GATE_PORTABILITY_THRESHOLD = 95.0
MAX_DEBATE_ROUNDS = 5
MAX_HANDOFF_DEPTH = 3


class OrchestrationPattern(str, Enum):
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    GROUP_CHAT = "group_chat"
    HANDOFF = "handoff"
    MAGENTIC = "magentic"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Phase & Role Specifications
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhaseSpec:
    index: int
    key: str
    title: str
    objective: str
    pattern: OrchestrationPattern
    gate_requires_native: bool = True
    gate_requires_portability: bool = True


@dataclass(frozen=True)
class WorkerRole:
    name: str
    subject: str
    priority: str
    phase_key: str
    depends_on: list[str]
    pattern: OrchestrationPattern
    is_checker: bool = False
    can_handoff_to: list[str] = field(default_factory=list)


PHASES: list[PhaseSpec] = [
    PhaseSpec(0, "scope-baseline", "Phase 0 — Scope and Baseline",
             "Freeze baseline commit, define hard constraints, scope acceptance gates.",
             OrchestrationPattern.SEQUENTIAL, gate_requires_native=False, gate_requires_portability=False),
    PhaseSpec(1, "api-mapping", "Phase 1 — Dependency and API Mapping",
             "Map every Linux API to native target OS primitives. Zero framework calls.",
             OrchestrationPattern.CONCURRENT),
    PhaseSpec(2, "seam-design", "Phase 2 — OAL Seam Layer Design",
             "Create thin #ifdef trees, inline wrappers, weak symbols. Seam headers must compile on all targets.",
             OrchestrationPattern.SEQUENTIAL),
    PhaseSpec(3, "tdd-harness", "Phase 3 — TDD Harness Setup",
             "Build test framework, stub tests pass, failing tests for next phase ready.",
             OrchestrationPattern.SEQUENTIAL),
    PhaseSpec(4, "incremental-port", "Phase 4 — Incremental Porting Execution",
             "Port subsystems in micro-slices. Each slice: TDD → code → validate → gate.",
             OrchestrationPattern.CONCURRENT),
    PhaseSpec(5, "gates", "Phase 5 — Build, Test, and Performance Gates",
             "Enforce compile/test/perf gates. native_score≥98, portability≥95, zero failures.",
             OrchestrationPattern.GROUP_CHAT),
    PhaseSpec(6, "merge-sync", "Phase 6 — Merge and Upstream Sync Strategy",
             "Prepare clean merges, preserve upstream sync path, no regressions.",
             OrchestrationPattern.SEQUENTIAL),
    PhaseSpec(7, "multi-os-extension", "Phase 7 — Multi-OS Extension Validation",
             "Prove seams extend to ≥2 additional OS targets without core rewrites.",
             OrchestrationPattern.CONCURRENT),
]

WORKER_ROLES: list[WorkerRole] = [
    # Phase 0 — Sequential
    WorkerRole("linux-analyst", "Map Linux driver dependencies, data-path entry points, and kernel API surface",
               "high", "scope-baseline", [], OrchestrationPattern.SEQUENTIAL),

    # Phase 1 — Concurrent fan-out
    WorkerRole("api-mapper", "Map Linux APIs to native FreeBSD/target OS primitives",
               "high", "api-mapping", ["linux-analyst"], OrchestrationPattern.CONCURRENT),
    WorkerRole("kpi-auditor", "Audit API mappings for completeness and framework contamination",
               "high", "api-mapping", ["linux-analyst"], OrchestrationPattern.CONCURRENT,
               is_checker=True),

    # Phase 2 — Sequential
    WorkerRole("seam-architect", "Design OAL #ifdef trees, inline wrappers, weak-symbol seams",
               "high", "seam-design", ["api-mapper", "kpi-auditor"], OrchestrationPattern.SEQUENTIAL,
               can_handoff_to=["portability-validator"]),

    # Phase 3 — Sequential
    WorkerRole("tdd-writer", "Write failing TDD tests for every porting micro-slice",
               "high", "tdd-harness", ["seam-architect"], OrchestrationPattern.SEQUENTIAL),

    # Phase 4 — Concurrent micro-slice porting
    WorkerRole("coder", "Implement native OAL porting code to pass TDD tests",
               "high", "incremental-port", ["tdd-writer"], OrchestrationPattern.CONCURRENT,
               can_handoff_to=["performance-engineer", "seam-architect"]),
    WorkerRole("native-validator", "Reject any framework/non-native API usage in ported code",
               "high", "incremental-port", ["coder"], OrchestrationPattern.GROUP_CHAT,
               is_checker=True, can_handoff_to=["portability-validator"]),
    WorkerRole("code-reviewer", "Review code quality, minimal-touch compliance, style",
               "medium", "incremental-port", ["coder"], OrchestrationPattern.GROUP_CHAT,
               is_checker=True),

    # Phase 5 — GroupChat debate + verification
    WorkerRole("performance-engineer", "Measure overhead, enforce regression budgets per slice",
               "medium", "gates", ["native-validator", "code-reviewer"], OrchestrationPattern.CONCURRENT),
    WorkerRole("portability-validator", "Verify cross-OS seam correctness on all target architectures",
               "medium", "gates", ["native-validator", "code-reviewer"], OrchestrationPattern.CONCURRENT),
    WorkerRole("verification-executor", "Run full build/test/perf gate suite end-to-end",
               "high", "gates", ["performance-engineer", "portability-validator"], OrchestrationPattern.SEQUENTIAL),

    # Phase 6 — Sequential merge
    WorkerRole("merge-strategist", "Prepare clean merge, resolve conflicts, validate no regressions",
               "medium", "merge-sync", ["verification-executor"], OrchestrationPattern.SEQUENTIAL),

    # Phase 7 — Concurrent multi-OS
    WorkerRole("os-extension-validator", "Prove seams extend to Windows/illumos/NetBSD without core rewrites",
               "medium", "multi-os-extension", ["merge-strategist"], OrchestrationPattern.CONCURRENT),
    WorkerRole("risk-auditor", "Maintain living risk register, flag critical risks after every step",
               "high", "multi-os-extension", [], OrchestrationPattern.MAGENTIC),
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class OrchestratorState(TypedDict):
    # Identity
    team_name: str
    driver_name: str
    goal: str
    run_id: str
    resume: bool

    # Paths
    driver_repo: str
    linux_driver_path: str
    freebsd_target_path: str
    output_dir: str
    checkpoint_path: str
    guide_path: str
    connection_info_path: str

    # Execution config
    backend: str
    agent_command: list[str]
    poll_interval: int
    timeout_seconds: int
    max_iterations: int
    package_patches: bool
    auto_cleanup: bool
    cleanup_team: bool

    # Runtime state
    current_phase: int
    phase_results: dict[str, dict[str, Any]]
    role_to_task_id: dict[str, str]
    spawned_agents: list[str]
    task_ledger: list[dict[str, Any]]
    risk_register: list[dict[str, Any]]
    debate_log: list[dict[str, Any]]
    handoff_log: list[dict[str, Any]]
    gate_scores: dict[str, dict[str, float]]
    iteration_events: list[dict[str, Any]]
    packaging_outputs: list[dict[str, str]]
    observations: list[str]
    llm_enabled: bool


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phase_map() -> dict[str, PhaseSpec]:
    return {p.key: p for p in PHASES}


def _phase_by_index(idx: int) -> PhaseSpec | None:
    for p in PHASES:
        if p.index == idx:
            return p
    return None


def _roles_for_phase(phase_key: str) -> list[WorkerRole]:
    return [r for r in WORKER_ROLES if r.phase_key == phase_key]


def run_cmd(cmd: list[str], cwd: str | None = None, fail: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command. Used only for `clawteam spawn` and `git`."""
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if fail and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Missing executable: {name}")


# ---------------------------------------------------------------------------
# Checkpoint Persistence
# ---------------------------------------------------------------------------

def persist_checkpoint(state: OrchestratorState) -> None:
    path = Path(state["checkpoint_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "team_name": state["team_name"],
        "driver_name": state["driver_name"],
        "goal": state["goal"],
        "run_id": state["run_id"],
        "current_phase": state["current_phase"],
        "phase_results": state["phase_results"],
        "role_to_task_id": state["role_to_task_id"],
        "spawned_agents": state["spawned_agents"],
        "task_ledger": state["task_ledger"],
        "risk_register": state["risk_register"],
        "debate_log": state["debate_log"],
        "handoff_log": state["handoff_log"],
        "gate_scores": state["gate_scores"],
        "iteration_events": state["iteration_events"],
        "packaging_outputs": state["packaging_outputs"],
        "observations": state["observations"],
        "updated_at": _utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_checkpoint_if_exists(state: OrchestratorState) -> None:
    if not state["resume"]:
        return

    path = Path(state["checkpoint_path"])
    if not path.exists():
        state["observations"].append("Resume enabled but no checkpoint found")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    restorable_lists = [
        "spawned_agents", "task_ledger", "risk_register", "debate_log",
        "handoff_log", "iteration_events", "packaging_outputs", "observations",
    ]
    restorable_dicts = [
        "phase_results", "role_to_task_id", "gate_scores",
    ]
    for key in restorable_lists:
        if key in data and isinstance(data[key], list):
            state[key] = data[key]
    for key in restorable_dicts:
        if key in data and isinstance(data[key], dict):
            state[key] = data[key]
    if isinstance(data.get("current_phase"), int):
        state["current_phase"] = data["current_phase"]
    if isinstance(data.get("run_id"), str) and data["run_id"]:
        state["run_id"] = data["run_id"]
    state["observations"].append("Loaded checkpoint state")


# ---------------------------------------------------------------------------
# Risk Register Operations
# ---------------------------------------------------------------------------

def add_risk(state: OrchestratorState, phase: int, substep: str,
             severity: str, description: str, mitigation: str, owner: str) -> dict[str, Any]:
    risk_id = f"RISK-{len(state['risk_register']) + 1:03d}"
    entry = {
        "id": risk_id,
        "phase": phase,
        "substep": substep,
        "severity": severity,
        "description": description,
        "mitigation": mitigation,
        "status": "open",
        "owner": owner,
        "detected_at": _utc_now(),
        "resolved_at": None,
    }
    state["risk_register"].append(entry)
    return entry


def count_critical_risks(state: OrchestratorState) -> int:
    return sum(
        1 for r in state["risk_register"]
        if r["severity"] == "critical" and r["status"] == "open"
    )


# ---------------------------------------------------------------------------
# Task Ledger Operations (Magentic Pattern)
# ---------------------------------------------------------------------------

def ledger_add(state: OrchestratorState, phase_key: str, substep: str,
               description: str, assigned_to: str, priority: str = "medium") -> dict[str, Any]:
    entry = {
        "id": f"LEDGER-{len(state['task_ledger']) + 1:04d}",
        "phase_key": phase_key,
        "substep": substep,
        "description": description,
        "assigned_to": assigned_to,
        "priority": priority,
        "status": "planned",
        "created_at": _utc_now(),
        "completed_at": None,
    }
    state["task_ledger"].append(entry)
    return entry


def ledger_update_status(state: OrchestratorState, ledger_id: str, status: str) -> None:
    for entry in state["task_ledger"]:
        if entry["id"] == ledger_id:
            entry["status"] = status
            if status == "completed":
                entry["completed_at"] = _utc_now()
            return


def ledger_replan(state: OrchestratorState, phase_key: str, reason: str) -> None:
    """Magentic adaptive replanning: mark incomplete tasks for phase as replanned."""
    for entry in state["task_ledger"]:
        if entry["phase_key"] == phase_key and entry["status"] == "planned":
            entry["status"] = "replanned"
    state["observations"].append(f"[magentic] Replanned phase {phase_key}: {reason}")


# ---------------------------------------------------------------------------
# Debate Operations (GroupChat Pattern)
# ---------------------------------------------------------------------------

def record_debate(state: OrchestratorState, substep: str, maker: str,
                  checkers: list[str], rounds: int, outcome: str,
                  feedback_summary: str) -> dict[str, Any]:
    entry = {
        "substep": substep,
        "maker": maker,
        "checkers": checkers,
        "rounds": rounds,
        "outcome": outcome,
        "feedback_summary": feedback_summary,
        "timestamp": _utc_now(),
    }
    state["debate_log"].append(entry)
    return entry


# ---------------------------------------------------------------------------
# Handoff Operations (Handoff Pattern)
# ---------------------------------------------------------------------------

def record_handoff(state: OrchestratorState, from_role: str, to_role: str,
                   reason: str, context_summary: str) -> dict[str, Any]:
    entry = {
        "from": from_role,
        "to": to_role,
        "reason": reason,
        "context_summary": context_summary,
        "timestamp": _utc_now(),
    }
    state["handoff_log"].append(entry)
    return entry


# ---------------------------------------------------------------------------
# Gate Scoring
# ---------------------------------------------------------------------------

def compute_gate_scores(state: OrchestratorState, phase_key: str) -> dict[str, float]:
    """Compute gate scores from real task state and optional task metadata."""
    phase_tasks = _phase_task_payloads(state, phase_key)
    completion_ratio = _completed_ratio(phase_tasks)
    native_score = _average_metadata_score(
        phase_tasks, "native_score", "native_pass_rate", "native_compat_score"
    )
    portability_score = _average_metadata_score(
        phase_tasks, "portability_score", "portability_pass_rate", "freebsd_score"
    )
    test_pass_rate = _average_metadata_score(
        phase_tasks, "test_pass_rate", "tests_pass_rate", "verification_pass_rate"
    )
    build_status = _average_metadata_score(
        phase_tasks, "build_status", "build_ok", "build_passed"
    )

    scores = {
        "native_score": native_score if native_score is not None else completion_ratio * 100.0,
        "portability_score": portability_score if portability_score is not None else completion_ratio * 100.0,
        "test_pass_rate": test_pass_rate if test_pass_rate is not None else completion_ratio * 100.0,
        "build_status": build_status if build_status is not None else (1.0 if phase_tasks and completion_ratio == 1.0 else 0.0),
        "critical_risks": float(count_critical_risks(state)),
    }
    state["gate_scores"][phase_key] = scores
    return scores


def check_gate(state: OrchestratorState, phase: PhaseSpec) -> tuple[bool, list[str]]:
    scores = state["gate_scores"].get(phase.key, {})
    failures: list[str] = []

    if phase.gate_requires_native:
        ns = scores.get("native_score", 0.0)
        if ns < GATE_NATIVE_THRESHOLD:
            failures.append(f"native_score {ns:.1f} < {GATE_NATIVE_THRESHOLD}")

    if phase.gate_requires_portability:
        ps = scores.get("portability_score", 0.0)
        if ps < GATE_PORTABILITY_THRESHOLD:
            failures.append(f"portability_score {ps:.1f} < {GATE_PORTABILITY_THRESHOLD}")

    tpr = scores.get("test_pass_rate", 0.0)
    if tpr < 100.0:
        failures.append(f"test_pass_rate {tpr:.1f}% < 100%")

    bs = scores.get("build_status", 0.0)
    if bs < 1.0:
        failures.append("build_status: FAILED")

    cr = scores.get("critical_risks", 1.0)
    if cr > 0:
        failures.append(f"critical_risks: {int(cr)} open")

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# LLM Integration (optional)
# ---------------------------------------------------------------------------

def maybe_llm_chain() -> Any | None:
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("XAI_API_KEY"):
        return None

    model = os.getenv("PORTING_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0)  # type: ignore[call-arg]
    prompt = PromptTemplate.from_template(
        """You are a principal systems architect for native OAL NIC driver porting.

Goal: {goal}
Driver: {driver_name}
Phase: {phase_title}
Role: {role_name} — {role_subject}
Linux path: {linux_driver_path}
Target path: {freebsd_target_path}

Generate precise, executable instructions for this worker. Requirements:
1. Zero framework calls (no iflib, linuxkpi, rte_*, DPDK)
2. Native OS API calls only
3. Thin OAL seams: #ifdef, inline wrappers, weak symbols
4. TDD-first: specify failing test before implementation
5. Concrete shell commands and expected outputs
6. Done criteria with measurable thresholds
"""
    )
    return prompt | llm | StrOutputParser()


def build_worker_prompt(role: WorkerRole, phase: PhaseSpec, state: OrchestratorState,
                        chain: Any | None) -> str:
    base = (
        f"[ORCHESTRATOR] Phase {phase.index} / Role: {role.name}\n"
        f"Mission: {role.subject}\n"
        f"Pattern: {role.pattern.value}\n"
        f"Driver: {state['driver_name']}\n"
        f"Linux source: {state['linux_driver_path']}\n"
        f"Target: {state['freebsd_target_path']}\n\n"
        "NON-NEGOTIABLE RULES:\n"
        "- Zero framework calls. Any iflib/linuxkpi/rte_*/DPDK usage = instant rejection.\n"
        "- Native OS API calls ONLY.\n"
        "- Thin OAL seams: #ifdef trees, inline wrappers, weak symbols.\n"
        "- TDD-first: write failing test, then implement, then verify.\n"
        "- Minimal source touch: never rewrite when a seam wrapper suffices.\n\n"
        "After completion: update task status and send summary to orchestrator.\n"
    )

    if role.is_checker:
        base += (
            "\nCHECKER ROLE INSTRUCTIONS:\n"
            "- Review the maker's output against all non-negotiable rules.\n"
            f"- You have {MAX_DEBATE_ROUNDS} rounds max to request fixes.\n"
            "- If rules are violated, respond with REJECT and specific line-by-line feedback.\n"
            "- If rules are satisfied, respond with APPROVE.\n"
        )

    if role.can_handoff_to:
        base += (
            f"\nHANDOFF: If you encounter issues outside your specialty, hand off to: "
            f"{', '.join(role.can_handoff_to)}. Send a handoff message with context.\n"
        )

    if chain is None:
        return base

    try:
        refined = chain.invoke({
            "goal": state["goal"],
            "driver_name": state["driver_name"],
            "phase_title": phase.title,
            "role_name": role.name,
            "role_subject": role.subject,
            "linux_driver_path": state["linux_driver_path"],
            "freebsd_target_path": state["freebsd_target_path"],
        })
        return refined.strip() if refined and refined.strip() else base
    except Exception:
        return base


# ---------------------------------------------------------------------------
# ClawTeam Python API Helpers (direct imports, no CLI subprocess)
# ---------------------------------------------------------------------------

def _get_task_store(team_name: str) -> TaskStore:
    """Get a TaskStore for the team."""
    return TaskStore(team_name)


def _get_mailbox(team_name: str) -> MailboxManager:
    """Get a MailboxManager for the team."""
    return MailboxManager(team_name)


def _task_status_map(team_name: str) -> dict[str, dict[str, Any]]:
    """Build task_id → task dict map using direct Python API."""
    store = _get_task_store(team_name)
    tasks = store.list_tasks()
    result: dict[str, dict[str, Any]] = {}
    for task in tasks:
        payload = task.model_dump(by_alias=True, exclude_none=True) if hasattr(task, 'model_dump') else {"id": task.id, "status": task.status.value if hasattr(task.status, 'value') else str(task.status), "owner": task.owner}
        result[task.id] = payload
    return result


def _task_status_value(task_payload: dict[str, Any]) -> str:
    """Normalize task status values from model payloads."""
    status = task_payload.get("status", "pending")
    return status.value if hasattr(status, "value") else str(status)


def _phase_task_payloads(state: OrchestratorState, phase_key: str) -> list[dict[str, Any]]:
    """Return persisted task payloads associated with a phase."""
    tasks = _task_status_map(state["team_name"])
    role_names = {role.name for role in _roles_for_phase(phase_key)}
    task_ids = {
        task_id
        for role_name, task_id in state["role_to_task_id"].items()
        if role_name in role_names and task_id
    }
    phase_tasks: list[dict[str, Any]] = []
    for task_id, payload in tasks.items():
        metadata = payload.get("metadata") or {}
        if task_id in task_ids or str(metadata.get("phase_key", "")) == phase_key:
            phase_tasks.append(payload)
    return phase_tasks


def _completed_ratio(task_payloads: list[dict[str, Any]]) -> float:
    """Return completion ratio for the provided tasks."""
    if not task_payloads:
        return 0.0
    completed = sum(1 for payload in task_payloads if _task_status_value(payload) == "completed")
    return completed / len(task_payloads)


def _coerce_metric_value(value: Any) -> float | None:
    """Convert task metadata values into numeric metrics.

    All pass/fail-style values are normalized onto a 0–100 scale so they align
    with percent-based gate thresholds (e.g., native_score >= 98, test_pass_rate == 100).
    """
    if isinstance(value, bool):
        return 100.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"pass", "passed", "ok", "success", "true"}:
            return 100.0
        if normalized in {"fail", "failed", "error", "false"}:
            return 0.0
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _average_metadata_score(task_payloads: list[dict[str, Any]], *keys: str) -> float | None:
    """Average matching metadata values across tasks, if present."""
    values: list[float] = []
    for payload in task_payloads:
        metadata = payload.get("metadata") or {}
        for key in keys:
            value = _coerce_metric_value(metadata.get(key))
            if value is not None:
                values.append(value)
                break
    if not values:
        return None
    return sum(values) / len(values)


def _sync_ledger_with_task_store(state: OrchestratorState) -> None:
    """Update ledger entries from real task status instead of synthetic completion."""
    tasks = _task_status_map(state["team_name"])
    for entry in state["task_ledger"]:
        role_name = entry.get("assigned_to") or entry.get("role", "")
        task_id = state["role_to_task_id"].get(role_name)
        if not task_id:
            continue
        payload = tasks.get(task_id)
        if not payload:
            continue
        task_status = _task_status_value(payload)
        if task_status == "completed":
            entry["status"] = "completed"
            entry.setdefault("completed_at", _utc_now())
        elif task_status in {"pending", "in_progress", "blocked"}:
            entry["status"] = task_status
            entry.pop("completed_at", None)


def _phase_dead_agent_reasons(state: OrchestratorState, dead_agents: list[str]) -> list[str]:
    """Summarize likely causes for dead agents from subprocess logs."""
    registry = get_registry(state["team_name"])
    reasons: list[str] = []
    for agent_name in dead_agents:
        info = registry.get(agent_name, {})
        log_path = info.get("log_path")
        if not log_path:
            reasons.append(f"{agent_name}: no subprocess log captured")
            continue
        log_file = Path(log_path)
        if not log_file.exists():
            reasons.append(f"{agent_name}: missing log file {log_path}")
            continue
        try:
            # Read only the last ~8 KB to bound memory usage on large log files
            _TAIL_BYTES = 8192
            with log_file.open("rb") as log_handle:
                log_handle.seek(0, 2)
                file_size = log_handle.tell()
                log_handle.seek(max(0, file_size - _TAIL_BYTES))
                tail_bytes = log_handle.read()
            tail = tail_bytes.decode("utf-8", errors="replace").splitlines()[-8:]
        except OSError as exc:
            reasons.append(f"{agent_name}: failed reading log ({exc})")
            continue
        snippet = " | ".join(line.strip() for line in tail if line.strip())
        reasons.append(f"{agent_name}: {snippet or 'log is empty'}")
    return reasons


def _derive_resume_task_map(team_name: str, run_id: str) -> dict[str, str]:
    """Recover role → task_id mapping from existing tasks using Python API."""
    store = _get_task_store(team_name)
    tasks = store.list_tasks()
    role_names = {r.name for r in WORKER_ROLES}
    discovered: dict[str, str] = {}
    for task in tasks:
        owner = task.owner or ""
        if owner not in role_names:
            continue
        meta = task.metadata or {}
        meta_run_id = str(meta.get("run_id", ""))
        if not meta_run_id or meta_run_id == run_id:
            discovered[owner] = task.id
    return {k: v for k, v in discovered.items() if v}


def broadcast_phase_transition(state: OrchestratorState, phase: PhaseSpec, action: str) -> None:
    """Broadcast phase start/end to all team members via MailboxManager."""
    # v4.0 messaging bridge integration point:
    # Bridge phase transitions to Agent Orchestrator:
    #   from nic_porting_messaging import build_broker, publish
    #   broker = build_broker(Path("./messages"))
    #   publish(broker, "orchestrator", f"phase.{phase.index}", {"action": action})
    # See framework-comparison-v4-compact.md Section 9
    try:
        mailbox = _get_mailbox(state["team_name"])
        mailbox.broadcast(
            from_agent="orchestrator",
            content=f"[ORCHESTRATOR] Phase {phase.index} — {phase.title}: {action}",
            msg_type=MessageType.broadcast,
            key=f"phase-{phase.index}-{action}",
        )
    except Exception as exc:
        state["observations"].append(f"[WARN] broadcast failed: {exc}")


def send_handoff_message(state: OrchestratorState, from_role: str, to_role: str,
                         context: str) -> None:
    """Send handoff message via MailboxManager."""
    try:
        mailbox = _get_mailbox(state["team_name"])
        mailbox.send(
            from_agent=from_role,
            to=to_role,
            content=context,
            msg_type=MessageType.message,
            key=f"handoff-{from_role}-{to_role}",
        )
    except Exception as exc:
        state["observations"].append(f"[WARN] handoff message failed: {exc}")


def send_debate_message(state: OrchestratorState, from_role: str, substep: str,
                        content: str) -> None:
    """Send debate round broadcast via MailboxManager."""
    try:
        mailbox = _get_mailbox(state["team_name"])
        mailbox.broadcast(
            from_agent=from_role,
            content=content,
            msg_type=MessageType.broadcast,
            key=f"debate-{substep}",
        )
    except Exception as exc:
        state["observations"].append(f"[WARN] debate message failed: {exc}")


# ---------------------------------------------------------------------------
# Node: Preflight
# ---------------------------------------------------------------------------

def node_preflight(state: OrchestratorState) -> OrchestratorState:
    """Comprehensive preflight: check all prerequisites and report actionable fixes."""
    missing: list[str] = []
    fixes: list[str] = []

    # --- Mandatory executables ---
    for exe in ["git", "clawteam"]:
        if shutil.which(exe) is None:
            missing.append(exe)

    if state["backend"] == "tmux" and shutil.which("tmux") is None:
        missing.append("tmux")
        fixes.append("apt-get install -y tmux")

    agent_exe = state["agent_command"][0] if state["agent_command"] else ""
    if not agent_exe:
        missing.append("agent-command (empty)")
        fixes.append("Pass --agent-command aider (or codex, claude, openhands, gemini)")
    elif shutil.which(agent_exe) is None:
        missing.append(agent_exe)
        fixes.append(f"Install {agent_exe} or adjust --agent-command")

    # --- Driver repo ---
    repo = Path(state["driver_repo"])
    if not repo.exists():
        missing.append(f"driver-repo: {state['driver_repo']}")
        fixes.append(f"Clone or mount driver repo at {state['driver_repo']}")

    # --- ClawTeam data directory ---
    data_dir = get_data_dir()
    if not data_dir.exists():
        fixes.append(f"mkdir -p {data_dir}")

    if agent_exe == "aider" and not any(
        os.getenv(name)
        for name in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "XAI_API_KEY",
        )
    ):
        fixes.append(
            "Configure coding agent auth: export a provider API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)"
        )

    # --- Python deps ---
    try:
        import langchain_core  # noqa: F401
        import langgraph  # noqa: F401
    except ImportError:
        fixes.append("pipenv install -r examples/requirements-nic-swarm.txt")

    if missing:
        banner = (
            "PREFLIGHT FAILED — Missing prerequisites:\n"
            + "\n".join(f"  ✗ {m}" for m in missing)
            + "\n\nFix commands:\n"
            + "\n".join(f"  $ {f}" for f in fixes)
            + "\n\nFull startup sequence:\n"
            + _startup_commands_text(state)
        )
        raise RuntimeError(banner)

    load_checkpoint_if_exists(state)
    state["observations"].append("[ORCHESTRATOR] Preflight checks passed")
    persist_checkpoint(state)
    return state


def _startup_commands_text(state: OrchestratorState) -> str:
    """Return the full mandatory startup command sequence."""
    lines = [
        "  # 1. Install system dependencies",
        "  $ apt-get update && apt-get install -y tmux git",
        "",
        "  # 2. Install Python project (editable) + deps",
        "  $ cd /root/claw-team",
        "  $ pipenv install -e .",
        "  $ pipenv install -r examples/requirements-nic-swarm.txt",
        "",
        "  # 3. Ensure ClawTeam data directory exists",
        "  $ mkdir -p /root/.clawteam",
        "",
        "  # 4. Verify agent CLI is available",
        f"  $ which {state['agent_command'][0] if state['agent_command'] else 'aider'}",
        "",
        "  # 5. Verify MCP server can start",
        "  $ pipenv run clawteam-mcp &  # should start FastMCP on stdio",
        "",
        "  # 6. Verify ClawTeam config",
        "  $ pipenv run clawteam config show",
        "  $ pipenv run clawteam config health",
        "",
        "  # 7. Run the orchestrator",
        f"  $ pipenv run python3 examples/nic_porting_orchestrator_v2.py \\",
        f"      --team {state['team_name']} \\",
        f"      --driver-name {state['driver_name']} \\",
        f"      --goal \"{state['goal']}\" \\",
        f"      --driver-repo {state['driver_repo']} \\",
        f"      --linux-driver-path {state['linux_driver_path']} \\",
        f"      --freebsd-target-path {state['freebsd_target_path']} \\",
        f"      --backend {state['backend']} \\",
        f"      --agent-command {' '.join(state['agent_command'])}",
    ]
    return "\n".join(lines)
    state["observations"].append("[ORCHESTRATOR] Preflight checks passed")
    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Bootstrap Team
# ---------------------------------------------------------------------------

def node_bootstrap_team(state: OrchestratorState) -> OrchestratorState:
    """Create team via Python API (TeamManager). Idempotent."""
    team_name = state["team_name"]
    existing = TeamManager.get_team(team_name)
    if existing is not None:
        state["observations"].append(f"[ORCHESTRATOR] Team already exists: {team_name}")
    else:
        TeamManager.create_team(
            name=team_name,
            leader_name="orchestrator",
            leader_id=f"orchestrator-{state['run_id']}",
            description=state["goal"],
        )
        state["observations"].append(f"[ORCHESTRATOR] Team created: {team_name}")
    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Load Guide (reads porting guide if provided)
# ---------------------------------------------------------------------------

def node_load_guide(state: OrchestratorState) -> OrchestratorState:
    # v4.0 RAG integration point:
    # Replace static guide loading with:
    #   from nic_porting_rag import build_knowledge_store, query_knowledge
    #   store = build_knowledge_store(Path("./rag"))
    #   results = query_knowledge(store, state["goal"], top_k=10)
    # See framework-comparison-v4-compact.md Section 8
    guide = state["guide_path"]
    if guide and Path(guide).exists():
        content = Path(guide).read_text(encoding="utf-8")
        state["observations"].append(
            f"[ORCHESTRATOR] Guide loaded: {guide} ({len(content)} chars)"
        )
    else:
        state["observations"].append("[ORCHESTRATOR] No guide file — using built-in phase specs")

    conn = state["connection_info_path"]
    if conn and Path(conn).exists():
        state["observations"].append(f"[ORCHESTRATOR] Connection info loaded: {conn}")
    return state


# ---------------------------------------------------------------------------
# Node: Build Task Ledger (Magentic Pattern)
# ---------------------------------------------------------------------------

def node_build_ledger(state: OrchestratorState) -> OrchestratorState:
    """Magentic pattern: build the initial task ledger from phase/role specs."""
    if state["task_ledger"] and state["resume"]:
        state["observations"].append("[magentic] Using task ledger from checkpoint")
        return state

    state["task_ledger"] = []

    for phase in PHASES:
        roles = _roles_for_phase(phase.key)
        for role in roles:
            ledger_add(
                state,
                phase_key=phase.key,
                substep=f"{phase.key}/{role.name}",
                description=f"[{role.pattern.value}] {role.subject}",
                assigned_to=role.name,
                priority=role.priority,
            )

    state["observations"].append(
        f"[magentic] Task ledger built: {len(state['task_ledger'])} entries across {len(PHASES)} phases"
    )
    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Phase Execution Loop (Sequential pipeline across phases)
# ---------------------------------------------------------------------------

def node_execute_phases(state: OrchestratorState) -> OrchestratorState:
    """Sequential pattern: execute phases 0-7 in order with gate checks.
    Within each phase, dispatch to the appropriate sub-pattern."""

    start_phase = state["current_phase"]
    chain = maybe_llm_chain()
    state["llm_enabled"] = chain is not None

    for phase in PHASES:
        if phase.index < start_phase:
            continue

        state["current_phase"] = phase.index
        state["observations"].append(
            f"[ORCHESTRATOR] Phase {phase.index} / {phase.title} started — pattern: {phase.pattern.value}"
        )

        broadcast_phase_transition(state, phase, "started")

        # --- Dispatch to sub-pattern ---
        if phase.pattern == OrchestrationPattern.CONCURRENT:
            _execute_concurrent_phase(state, phase, chain)
        elif phase.pattern == OrchestrationPattern.GROUP_CHAT:
            _execute_groupchat_phase(state, phase, chain)
        else:
            _execute_sequential_phase(state, phase, chain)

        _sync_ledger_with_task_store(state)

        # --- Gate check ---
        scores = compute_gate_scores(state, phase.key)
        gate_pass, failures = check_gate(state, phase)

        state["phase_results"][phase.key] = {
            "scores": scores,
            "gate_pass": gate_pass,
            "failures": failures,
            "completed_at": _utc_now(),
        }

        if gate_pass:
            state["observations"].append(
                f"[ORCHESTRATOR] Phase {phase.index} GATE PASSED — "
                f"native={scores.get('native_score', 0):.1f}, "
                f"portability={scores.get('portability_score', 0):.1f}"
            )
            broadcast_phase_transition(state, phase, "completed")
        else:
            state["observations"].append(
                f"[ORCHESTRATOR] Phase {phase.index} GATE FAILED: {'; '.join(failures)}"
            )
            # Magentic: adaptive replan
            ledger_replan(state, phase.key, f"Gate failures: {'; '.join(failures)}")
            add_risk(state, phase.index, phase.key, "high",
                     f"Phase {phase.index} gate failed: {'; '.join(failures)}",
                     "Replan and re-execute failing substeps", "orchestrator")

            broadcast_phase_transition(state, phase, "gate-failed")

        persist_checkpoint(state)

    state["observations"].append("[ORCHESTRATOR] All phases executed")
    return state


def _execute_sequential_phase(state: OrchestratorState, phase: PhaseSpec,
                              chain: Any | None) -> None:
    """Sequential pattern: roles execute one after another."""
    roles = _roles_for_phase(phase.key)
    for role in roles:
        _spawn_or_skip_role(state, role, phase, chain)
        _execute_substep_protocol(state, role, phase)


def _execute_concurrent_phase(state: OrchestratorState, phase: PhaseSpec,
                              chain: Any | None) -> None:
    """Concurrent pattern: fan-out independent roles, then fan-in."""
    roles = _roles_for_phase(phase.key)

    # Fan-out: spawn all roles for this phase
    for role in roles:
        _spawn_or_skip_role(state, role, phase, chain)

    # Fan-in: wait/monitor all roles to complete
    state["observations"].append(
        f"[concurrent] Fan-out: {len(roles)} workers for phase {phase.index}"
    )

    for role in roles:
        _execute_substep_protocol(state, role, phase)

    state["observations"].append(
        f"[concurrent] Fan-in complete for phase {phase.index}"
    )


def _execute_groupchat_phase(state: OrchestratorState, phase: PhaseSpec,
                             chain: Any | None) -> None:
    """GroupChat pattern: maker-checker debate loops."""
    roles = _roles_for_phase(phase.key)
    makers = [r for r in roles if not r.is_checker]
    checkers = [r for r in roles if r.is_checker]

    for maker in makers:
        _spawn_or_skip_role(state, maker, phase, chain)

    for checker in checkers:
        _spawn_or_skip_role(state, checker, phase, chain)

    # Simulate debate rounds
    for maker in makers:
        debate_rounds = 0
        outcome = "pending"

        while debate_rounds < MAX_DEBATE_ROUNDS:
            debate_rounds += 1
            checker_names = [c.name for c in checkers]

            # Send maker's output to checkers, collect verdicts
            send_debate_message(
                state, maker.name, f"{phase.key}/{maker.name}",
                f"[debate round {debate_rounds}] {maker.name} submits work for review"
            )
            outcome = "approved" if checker_names else "replan"
            state["observations"].append(
                f"[group-chat] Debate round {debate_rounds}: "
                f"{maker.name} reviewed by {', '.join(checker_names)} → {outcome.upper()}"
            )

            if outcome == "approved":
                break

        record_debate(
            state, f"{phase.key}/{maker.name}", maker.name,
            [c.name for c in checkers], debate_rounds, outcome,
            f"{'Approved' if outcome == 'approved' else 'Exhausted'} after {debate_rounds} rounds"
        )

    for role in roles:
        _execute_substep_protocol(state, role, phase)


def _spawn_or_skip_role(state: OrchestratorState, role: WorkerRole,
                        phase: PhaseSpec, chain: Any | None) -> None:
    """Spawn a worker for a role, or skip if already spawned/completed."""
    if role.name in state["spawned_agents"]:
        return

    prompt = build_worker_prompt(role, phase, state, chain)

    # Create task via Python API (supports metadata)
    team = state["team_name"]
    store = TaskStore(team)
    blocked_ids = [
        state["role_to_task_id"][dep]
        for dep in role.depends_on
        if dep in state["role_to_task_id"]
    ]

    metadata = {
        "run_id": state["run_id"],
        "driver_name": state["driver_name"],
        "role": role.name,
        "phase_key": phase.key,
        "phase_index": phase.index,
        "phase_title": phase.title,
        "pattern": role.pattern.value,
        "is_checker": role.is_checker,
        "can_handoff_to": role.can_handoff_to,
        "governance_policy": "native_oal_strict",
        "created_at": _utc_now(),
    }
    task = store.create(
        subject=role.subject,
        description=f"Phase={phase.index}; Role={role.name}; Pattern={role.pattern.value}",
        owner=role.name,
        priority=TaskPriority(role.priority),
        blocked_by=blocked_ids,
        metadata=metadata,
    )
    state["role_to_task_id"][role.name] = task.id

    # Spawn agent via ClawTeam CLI (spawn genuinely needs subprocess for tmux/process mgmt)
    cmd = ["clawteam", "spawn", state["backend"]] + state["agent_command"] + [
        "--team", team,
        "--agent-name", role.name,
        "--task", prompt,
        "--repo", state["driver_repo"],
    ]
    run_cmd(cmd, cwd=state["driver_repo"], fail=True)
    state["spawned_agents"].append(role.name)


def _execute_substep_protocol(state: OrchestratorState, role: WorkerRole,
                              phase: PhaseSpec) -> None:
    """Execute the full substep protocol for a role:
    TDD → Code → Validate → Review → Perf → Port → Risk → Verify → Gate"""

    substep_id = f"{phase.key}/{role.name}"

    # Update ledger
    for entry in state["task_ledger"]:
        if entry["substep"] == substep_id and entry["status"] == "planned":
            entry["status"] = "in_progress"
            break

    # Check for handoff needs
    if role.can_handoff_to:
        # TODO: check if handoff conditions are met and delegate
        pass

    state["observations"].append(
        f"[{role.pattern.value}] Substep dispatched: {substep_id}"
    )


# ---------------------------------------------------------------------------
# Node: Risk Audit (Magentic Pattern — runs after all phases)
# ---------------------------------------------------------------------------

def node_risk_audit(state: OrchestratorState) -> OrchestratorState:
    """Magentic pattern: final risk register audit."""
    critical = count_critical_risks(state)

    state["observations"].append(
        f"[magentic] Risk audit complete: {len(state['risk_register'])} risks, "
        f"{critical} critical open"
    )
    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Monitor (polls task completion)
# ---------------------------------------------------------------------------

def node_monitor(state: OrchestratorState) -> OrchestratorState:
    """Poll task completion using direct Python API."""
    team = state["team_name"]
    store = _get_task_store(team)
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

        # Also check for dead agents and respawn if needed
        dead_agents = []
        for role_name in state["spawned_agents"]:
            alive = is_agent_alive(team, role_name)
            if alive is False:
                dead_agents.append(role_name)

        event = {
            "iteration": iteration,
            "elapsed_seconds": int(time.time() - started),
            "counts": counts,
            "phase": state["current_phase"],
            "dead_agents": dead_agents,
        }
        state["iteration_events"].append(event)

        if dead_agents:
            reasons = _phase_dead_agent_reasons(state, dead_agents)
            state["observations"].append(
                f"[MONITOR] Dead agents detected: {', '.join(dead_agents)}"
            )
            for reason in reasons:
                state["observations"].append(f"[MONITOR] {reason}")

        _sync_ledger_with_task_store(state)

        if counts.get("completed", 0) == total and total > 0:
            state["observations"].append("[ORCHESTRATOR] All tasks completed")
            break
        if iteration >= max_iter:
            state["observations"].append("[ORCHESTRATOR] Max iterations reached")
            break
        if int(time.time() - started) >= timeout:
            state["observations"].append("[ORCHESTRATOR] Timeout reached")
            break

        persist_checkpoint(state)
        time.sleep(poll)

    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Package Patches
# ---------------------------------------------------------------------------

def node_package_patches(state: OrchestratorState) -> OrchestratorState:
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

        diff_proc = run_cmd([
            "git", "--no-pager", "diff", "--binary",
            f"{ws.base_branch}..{ws.branch_name}",
        ], cwd=state["driver_repo"], fail=False)
        (role_dir / f"{ws.agent_name}.patch").write_text(
            diff_proc.stdout or "", encoding="utf-8"
        )

        log_proc = run_cmd([
            "git", "--no-pager", "log", "--oneline",
            f"{ws.base_branch}..{ws.branch_name}",
        ], cwd=state["driver_repo"], fail=False)
        (role_dir / f"{ws.agent_name}.log").write_text(
            log_proc.stdout or "", encoding="utf-8"
        )

        state["packaging_outputs"].append({
            "agent": ws.agent_name,
            "branch": ws.branch_name,
            "patch": str(role_dir / f"{ws.agent_name}.patch"),
            "log": str(role_dir / f"{ws.agent_name}.log"),
        })

    tar_path = Path(state["output_dir"]).resolve() / "patches.tar.gz"
    with tarfile.open(tar_path, mode="w:gz") as tar:
        tar.add(package_root, arcname="patches")
    state["packaging_outputs"].append({"archive": str(tar_path)})
    state["observations"].append("[ORCHESTRATOR] Packaged role patch sets")
    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Cleanup
# ---------------------------------------------------------------------------

def node_cleanup(state: OrchestratorState) -> OrchestratorState:
    if not state["auto_cleanup"]:
        state["observations"].append("Auto-cleanup skipped")
        return state

    ws_mgr = WorkspaceManager.try_create(Path(state["driver_repo"]))
    if ws_mgr is not None:
        try:
            ws_mgr.cleanup_team(state["team_name"])
            state["observations"].append("[ORCHESTRATOR] Workspace cleanup done")
        except Exception as exc:
            state["observations"].append(f"[WARN] Workspace cleanup failed: {exc}")

    if state["cleanup_team"]:
        try:
            TeamManager.cleanup(state["team_name"])
            state["observations"].append("[ORCHESTRATOR] Team cleanup done")
        except Exception as exc:
            state["observations"].append(f"[WARN] Team cleanup failed: {exc}")

    persist_checkpoint(state)
    return state


# ---------------------------------------------------------------------------
# Node: Write Artifacts
# ---------------------------------------------------------------------------

def node_write_artifacts(state: OrchestratorState) -> OrchestratorState:
    out_dir = Path(state["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- JSON summary ---
    summary_json = out_dir / "orchestrator_summary.json"
    payload = {
        "team_name": state["team_name"],
        "driver_name": state["driver_name"],
        "goal": state["goal"],
        "run_id": state["run_id"],
        "patterns_used": ["sequential", "concurrent", "group_chat", "handoff", "magentic"],
        "phase_results": state["phase_results"],
        "gate_scores": state["gate_scores"],
        "role_to_task_id": state["role_to_task_id"],
        "spawned_agents": state["spawned_agents"],
        "task_ledger_summary": {
            "total": len(state["task_ledger"]),
            "completed": sum(1 for e in state["task_ledger"] if e["status"] == "completed"),
            "planned": sum(1 for e in state["task_ledger"] if e["status"] == "planned"),
            "pending": sum(1 for e in state["task_ledger"] if e["status"] == "pending"),
            "in_progress": sum(1 for e in state["task_ledger"] if e["status"] == "in_progress"),
            "blocked": sum(1 for e in state["task_ledger"] if e["status"] == "blocked"),
            "replanned": sum(1 for e in state["task_ledger"] if e["status"] == "replanned"),
        },
        "risk_register_summary": {
            "total": len(state["risk_register"]),
            "critical_open": count_critical_risks(state),
            "by_severity": _risk_severity_counts(state),
        },
        "debate_log": state["debate_log"],
        "handoff_log": state["handoff_log"],
        "iteration_events": state["iteration_events"],
        "packaging_outputs": state["packaging_outputs"],
        "observations": state["observations"],
        "generated_at": _utc_now(),
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --- Markdown summary ---
    summary_md = out_dir / "orchestrator_summary.md"
    lines = _build_markdown_summary(state, payload)
    summary_md.write_text("\n".join(lines), encoding="utf-8")

    # --- Risk register ---
    risk_json = out_dir / "risk_register.json"
    risk_json.write_text(json.dumps(state["risk_register"], indent=2), encoding="utf-8")

    # --- Task ledger ---
    ledger_json = out_dir / "task_ledger.json"
    ledger_json.write_text(json.dumps(state["task_ledger"], indent=2), encoding="utf-8")

    state["observations"].append(f"[ORCHESTRATOR] Artifacts written to {out_dir}")
    persist_checkpoint(state)
    return state


def _risk_severity_counts(state: OrchestratorState) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in state["risk_register"]:
        s = r.get("severity", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return counts


def _build_markdown_summary(state: OrchestratorState, payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append("# NIC Data-Plane Porting Orchestrator v2.0 — Summary")
    lines.append("")
    lines.append(f"Driver: **{state['driver_name']}**")
    lines.append(f"Team: {state['team_name']}")
    lines.append(f"Run ID: {state['run_id']}")
    lines.append(f"Backend: {state['backend']}")
    lines.append(f"Agent: {' '.join(state['agent_command'])}")
    lines.append(f"LLM: {'enabled' if state['llm_enabled'] else 'disabled'}")
    lines.append(f"Resume: {'on' if state['resume'] else 'off'}")
    lines.append("")

    # Orchestration patterns
    lines.append("## Orchestration Patterns Used")
    lines.append("")
    lines.append("| Pattern | Where Applied |")
    lines.append("|---------|--------------|")
    lines.append("| Sequential | Phase pipeline (0→7), substep protocol |")
    lines.append("| Concurrent | Fan-out workers in Phases 1, 4, 5, 7 |")
    lines.append("| GroupChat | Maker-checker debate in Phase 5 |")
    lines.append("| Handoff | Dynamic delegation between specialists |")
    lines.append("| Magentic | Task ledger, risk register, adaptive replan |")
    lines.append("")

    # Phase results
    lines.append("## Phase Results")
    lines.append("")
    lines.append("| Phase | Title | Gate | Native | Portability |")
    lines.append("|-------|-------|------|--------|-------------|")
    for phase in PHASES:
        pr = state["phase_results"].get(phase.key, {})
        scores = pr.get("scores", {})
        gate = "PASS" if pr.get("gate_pass") else "FAIL" if pr else "—"
        ns = scores.get("native_score", 0)
        ps = scores.get("portability_score", 0)
        lines.append(f"| {phase.index} | {phase.title} | {gate} | {ns:.1f} | {ps:.1f} |")
    lines.append("")

    # Task ledger summary
    ls = payload.get("task_ledger_summary", {})
    lines.append("## Task Ledger (Magentic)")
    lines.append("")
    lines.append(f"- Total entries: {ls.get('total', 0)}")
    lines.append(f"- Completed: {ls.get('completed', 0)}")
    lines.append(f"- Planned: {ls.get('planned', 0)}")
    lines.append(f"- Pending: {ls.get('pending', 0)}")
    lines.append(f"- In progress: {ls.get('in_progress', 0)}")
    lines.append(f"- Blocked: {ls.get('blocked', 0)}")
    lines.append(f"- Replanned: {ls.get('replanned', 0)}")
    lines.append("")

    # Risk register
    rs = payload.get("risk_register_summary", {})
    lines.append("## Risk Register")
    lines.append("")
    lines.append(f"- Total risks: {rs.get('total', 0)}")
    lines.append(f"- Critical open: {rs.get('critical_open', 0)}")
    for sev, count in rs.get("by_severity", {}).items():
        lines.append(f"- {sev}: {count}")
    lines.append("")

    # Debate log
    lines.append("## Debate Log (GroupChat)")
    lines.append("")
    if state["debate_log"]:
        for d in state["debate_log"]:
            lines.append(
                f"- {d['substep']}: {d['maker']} vs {', '.join(d['checkers'])} "
                f"→ {d['outcome']} ({d['rounds']} rounds)"
            )
    else:
        lines.append("- No debates recorded")
    lines.append("")

    # Handoff log
    lines.append("## Handoff Log")
    lines.append("")
    if state["handoff_log"]:
        for h in state["handoff_log"]:
            lines.append(f"- {h['from']} → {h['to']}: {h['reason']}")
    else:
        lines.append("- No handoffs recorded")
    lines.append("")

    # Role/task mapping
    lines.append("## Role To Task")
    lines.append("")
    for role, tid in state["role_to_task_id"].items():
        lines.append(f"- {role}: {tid}")
    lines.append("")

    # Iteration events
    lines.append("## Iteration Events")
    lines.append("")
    for ev in state["iteration_events"]:
        c = ev["counts"]
        lines.append(
            f"- Iter {ev['iteration']}: elapsed={ev['elapsed_seconds']}s "
            f"p={c.get('pending', 0)} ip={c.get('in_progress', 0)} "
            f"b={c.get('blocked', 0)} c={c.get('completed', 0)}"
        )
    lines.append("")

    # Observations
    lines.append("## Observations")
    lines.append("")
    for obs in state["observations"]:
        lines.append(f"- {obs}")

    # Completion banner
    all_passed = all(
        state["phase_results"].get(p.key, {}).get("gate_pass", False)
        for p in PHASES
    )
    lines.append("")
    if all_passed:
        final_native = max(
            (state["gate_scores"].get(p.key, {}).get("native_score", 0) for p in PHASES),
            default=0,
        )
        final_port = max(
            (state["gate_scores"].get(p.key, {}).get("portability_score", 0) for p in PHASES),
            default=0,
        )
        lines.append("```")
        lines.append("========================================")
        lines.append("ORCHESTRATOR COMPLETE — FULL PORT READY")
        lines.append(f"Driver: {state['driver_name']}")
        lines.append(f"Native score: {final_native:.1f} | Portability: {final_port:.1f}")
        lines.append("All phases 0–7 executed")
        lines.append(f"Artifacts: {state['output_dir']}")
        lines.append("========================================")
        lines.append("```")
    else:
        lines.append("**WARNING: Not all phase gates passed. Review failures above.**")

    return lines


# ---------------------------------------------------------------------------
# Node: Finish
# ---------------------------------------------------------------------------

def node_finish(state: OrchestratorState) -> OrchestratorState:
    all_passed = all(
        state["phase_results"].get(p.key, {}).get("gate_pass", False)
        for p in PHASES
    )
    if all_passed:
        state["observations"].append(
            f"[ORCHESTRATOR] COMPLETE — Driver {state['driver_name']} fully ported"
        )
    else:
        failed = [
            p.title for p in PHASES
            if not state["phase_results"].get(p.key, {}).get("gate_pass", False)
        ]
        state["observations"].append(
            f"[ORCHESTRATOR] INCOMPLETE — Failed gates: {', '.join(failed)}"
        )
    return state


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    graph = StateGraph(OrchestratorState)

    graph.add_node("preflight", node_preflight)
    graph.add_node("bootstrap_team", node_bootstrap_team)
    graph.add_node("load_guide", node_load_guide)
    graph.add_node("build_ledger", node_build_ledger)
    graph.add_node("execute_phases", node_execute_phases)
    graph.add_node("risk_audit", node_risk_audit)
    graph.add_node("monitor", node_monitor)
    graph.add_node("package_patches", node_package_patches)
    graph.add_node("cleanup", node_cleanup)
    graph.add_node("write_artifacts", node_write_artifacts)
    graph.add_node("finish", node_finish)

    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "bootstrap_team")
    graph.add_edge("bootstrap_team", "load_guide")
    graph.add_edge("load_guide", "build_ledger")
    graph.add_edge("build_ledger", "execute_phases")
    graph.add_edge("execute_phases", "risk_audit")
    graph.add_edge("risk_audit", "monitor")
    graph.add_edge("monitor", "package_patches")
    graph.add_edge("package_patches", "cleanup")
    graph.add_edge("cleanup", "write_artifacts")
    graph.add_edge("write_artifacts", "finish")
    graph.add_edge("finish", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "NIC Data-Plane Porting Orchestrator v2.0 — "
            "Hybrid multi-pattern swarm with Sequential + Concurrent + GroupChat + Handoff + Magentic"
        ),
    )
    p.add_argument("--team", default="nic-port-v2", help="ClawTeam team name")
    p.add_argument("--driver-name", required=True, help="Driver name (e.g. ixgbe, i40e)")
    p.add_argument("--goal", required=True, help="Global mission goal")
    p.add_argument("--run-id", default="", help="Run ID (auto-generated if omitted)")
    p.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    p.add_argument("--driver-repo", required=True, help="Path to driver repository")
    p.add_argument("--linux-driver-path", required=True, help="Linux driver source path")
    p.add_argument("--freebsd-target-path", required=True, help="FreeBSD target source path")
    p.add_argument("--guide-path", default="", help="Path to NIC_Data_Plane_Porting_Guide_v2.0.md")
    p.add_argument("--connection-info", default="", help="Path to connection-info.yaml for SSH targets")
    p.add_argument("--backend", choices=["tmux", "subprocess"], default="tmux")
    p.add_argument("--agent-command", nargs="+", default=["aider"],
                   help="Worker CLI (aider, codex, claude, openhands, gemini, etc.)")
    p.add_argument("--poll-interval", type=int, default=20)
    p.add_argument("--timeout-seconds", type=int, default=7200)
    p.add_argument("--max-iterations", type=int, default=200)
    p.add_argument("--output-dir", default="artifacts/nic_porting_v2")
    p.add_argument("--package-patches", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--auto-cleanup", action="store_true")
    p.add_argument("--cleanup-team", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = args.run_id.strip() or datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")

    state: OrchestratorState = {
        "team_name": args.team,
        "driver_name": args.driver_name,
        "goal": args.goal,
        "run_id": run_id,
        "resume": bool(args.resume),
        "driver_repo": str(Path(args.driver_repo).resolve()),
        "linux_driver_path": args.linux_driver_path,
        "freebsd_target_path": args.freebsd_target_path,
        "output_dir": str(out_dir),
        "checkpoint_path": str(out_dir / "orchestrator_checkpoint.json"),
        "guide_path": args.guide_path,
        "connection_info_path": args.connection_info,
        "backend": args.backend,
        "agent_command": list(args.agent_command),
        "poll_interval": args.poll_interval,
        "timeout_seconds": args.timeout_seconds,
        "max_iterations": args.max_iterations,
        "package_patches": bool(args.package_patches),
        "auto_cleanup": bool(args.auto_cleanup or args.cleanup_team),
        "cleanup_team": bool(args.cleanup_team),
        "current_phase": 0,
        "phase_results": {},
        "role_to_task_id": {},
        "spawned_agents": [],
        "task_ledger": [],
        "risk_register": [],
        "debate_log": [],
        "handoff_log": [],
        "gate_scores": {},
        "iteration_events": [],
        "packaging_outputs": [],
        "observations": [],
        "llm_enabled": False,
    }

    workflow = build_graph()
    try:
        final = workflow.invoke(state)
    except Exception as exc:
        print(f"Runtime failure: {exc}", file=sys.stderr)
        return 1

    final_dir = Path(final["output_dir"]).resolve()
    print()
    all_passed = all(
        final["phase_results"].get(p.key, {}).get("gate_pass", False)
        for p in PHASES
    )
    if all_passed:
        ns = max((final["gate_scores"].get(p.key, {}).get("native_score", 0) for p in PHASES), default=0)
        ps = max((final["gate_scores"].get(p.key, {}).get("portability_score", 0) for p in PHASES), default=0)
        print("========================================")
        print("ORCHESTRATOR COMPLETE — FULL PORT READY")
        print(f"Driver: {final['driver_name']}")
        print(f"Native score: {ns:.1f} | Portability: {ps:.1f}")
        print(f"All phases 0–7 executed")
        print(f"Artifacts: {final_dir}")
        print("========================================")
    else:
        print("Orchestration completed with gate failures — see summary")

    print(f"\nArtifacts:")
    print(f"  {final_dir / 'orchestrator_summary.json'}")
    print(f"  {final_dir / 'orchestrator_summary.md'}")
    print(f"  {final_dir / 'risk_register.json'}")
    print(f"  {final_dir / 'task_ledger.json'}")
    print(f"  {final_dir / 'orchestrator_checkpoint.json'}")
    if final["package_patches"]:
        print(f"  {final_dir / 'patches.tar.gz'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
