from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph


class SwarmState(TypedDict):
    team_name: str
    goal: str
    driver_repo: str
    linux_driver_path: str
    freebsd_target_path: str
    chapters: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    observations: list[str]
    llm_refinement: str
    done: bool
    output_dir: str


def run(cmd: list[str], cwd: str | None = None, fail: bool = True) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if fail and proc.returncode != 0:
        raise RuntimeError(
            "Command failed: " + " ".join(cmd) + "\nstdout:\n" + proc.stdout + "\nstderr:\n" + proc.stderr
        )
    return proc.stdout.strip()


def ensure_dependencies() -> None:
    for exe in ["clawteam", "git"]:
        out = subprocess.run(["bash", "-lc", f"command -v {exe}"], text=True, capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"Missing dependency: {exe}")


def maybe_llm_chain() -> Any | None:
    # Optional LLM enhancement. The workflow still runs without this.
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("PORTING_MODEL", "gpt-4o")
    llm = ChatOpenAI(model=model, temperature=0)
    tmpl = PromptTemplate.from_template(
        """
You are a principal systems architect for NIC driver portability.
Goal: {goal}
Linux source path: {linux_driver_path}
FreeBSD target path: {freebsd_target_path}

Generate concise chaptered next actions with strict minimal-touch seam-first policy.
Return plain text with chapters and bullet steps.
"""
    )
    return tmpl | llm | StrOutputParser()


def node_bootstrap(state: SwarmState) -> SwarmState:
    ensure_dependencies()

    team = state["team_name"]
    goal = state["goal"]

    run(["clawteam", "team", "spawn-team", team, "-d", goal, "-n", "orchestrator"], fail=False)

    task_specs = [
        ("Map Linux driver dependencies", "linux-analyst", "high"),
        ("Design FreeBSD KPI shim interfaces", "kpi-mapper", "high"),
        ("Create seam layer wrappers and inline adapters", "seam-architect", "high"),
        ("Implement incremental port slices", "porting-engineer", "high"),
        ("Build test and performance gates", "build-ci", "medium"),
        ("Validate zero-overhead and regressions", "perf-verifier", "medium"),
        ("Review integration and extension path", "integration-reviewer", "medium"),
    ]

    created = []
    for subject, owner, prio in task_specs:
        out = run(
            [
                "clawteam",
                "--json",
                "task",
                "create",
                team,
                subject,
                "-o",
                owner,
                "--priority",
                prio,
            ],
            fail=False,
        )
        if out:
            try:
                created.append(json.loads(out))
            except json.JSONDecodeError:
                pass

    state["tasks"] = created
    state["observations"] = state.get("observations", []) + [
        f"Team bootstrapped: {team}",
        "Initial chapter tasks created",
    ]
    return state


def node_design_chapters(state: SwarmState) -> SwarmState:
    chapter_titles = [
        "Chapter 1 - Scope and Baseline",
        "Chapter 2 - Dependency and KPI Mapping",
        "Chapter 3 - Seam Layer Design",
        "Chapter 4 - Incremental Porting Execution",
        "Chapter 5 - Build Test and Performance Gates",
        "Chapter 6 - Merge Strategy and Upstream Sync",
        "Chapter 7 - Future Target Extension",
    ]

    chapters: list[dict[str, Any]] = []
    for i, title in enumerate(chapter_titles, start=1):
        chapters.append(
            {
                "index": i,
                "title": title,
                "status": "planned",
                "subtasks": [],
            }
        )

    chapters[0]["subtasks"] = [
        "Freeze Linux driver baseline commit",
        "List kernel APIs and DMA/interrupt touchpoints",
        "Define acceptance KPIs and performance budget",
    ]
    chapters[1]["subtasks"] = [
        "Map Linux primitives to LinuxKPI/iflib wrappers",
        "Isolate non-portable paths behind seam headers",
        "Produce KPI mapping matrix",
    ]
    chapters[2]["subtasks"] = [
        "Create include/port/seams.h",
        "Implement inline wrappers for netdev, pci, dma",
        "Add weak symbol fallback hooks where platform-specific",
    ]
    chapters[3]["subtasks"] = [
        "Port one subsystem at a time: probe -> txrx -> interrupt",
        "Keep Linux source changes minimal and tracked",
        "Validate each micro-slice before next",
    ]
    chapters[4]["subtasks"] = [
        "Add compile gates for Linux and FreeBSD",
        "Run unit/smoke tests per iteration",
        "Track perf deltas and fail above threshold",
    ]
    chapters[5]["subtasks"] = [
        "Prepare merge queue by subsystem",
        "Document divergence from upstream Linux",
        "Define rebase procedure for upstream sync",
    ]
    chapters[6]["subtasks"] = [
        "Define new target onboarding through shim extension only",
        "Provide template for additional OS KPI adapters",
        "Lock policy: no broad edits in core Linux logic",
    ]

    state["chapters"] = chapters
    state["observations"] = state.get("observations", []) + ["Chapter plan created"]
    return state


def node_llm_enrichment(state: SwarmState) -> SwarmState:
    chain = maybe_llm_chain()
    if chain is None:
        state["observations"] = state.get("observations", []) + [
            "OPENAI_API_KEY not set; skipped LLM enrichment"
        ]
        return state

    text = chain.invoke(
        {
            "goal": state["goal"],
            "linux_driver_path": state["linux_driver_path"],
            "freebsd_target_path": state["freebsd_target_path"],
        }
    )

    state["observations"] = state.get("observations", []) + ["LLM chapter refinement generated"]
    state["llm_refinement"] = text
    return state


def node_emit_artifacts(state: SwarmState) -> SwarmState:
    out_dir = Path(state["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    plan_path = out_dir / "transition_plan.json"
    md_path = out_dir / "transition_plan.md"

    payload = {
        "team_name": state["team_name"],
        "goal": state["goal"],
        "driver_repo": state["driver_repo"],
        "linux_driver_path": state["linux_driver_path"],
        "freebsd_target_path": state["freebsd_target_path"],
        "chapters": state.get("chapters", []),
        "tasks": state.get("tasks", []),
        "observations": state.get("observations", []),
        "generated_at_epoch": int(time.time()),
    }

    plan_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = []
    lines.append("# NIC Driver Porting Transition Plan")
    lines.append("")
    lines.append(f"Team: {state['team_name']}")
    lines.append(f"Goal: {state['goal']}")
    lines.append("")
    lines.append("## Chapters")
    lines.append("")

    for ch in state.get("chapters", []):
        lines.append(f"### {ch['title']}")
        for st in ch.get("subtasks", []):
            lines.append(f"- {st}")
        lines.append("")

    if state.get("llm_refinement"):
        lines.append("## LLM Refinement")
        lines.append("")
        lines.append(str(state["llm_refinement"]))
        lines.append("")

    lines.append("## Observations")
    lines.append("")
    for obs in state.get("observations", []):
        lines.append(f"- {obs}")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    state["observations"] = state.get("observations", []) + [
        f"Wrote {plan_path}",
        f"Wrote {md_path}",
    ]
    state["done"] = True
    return state


def node_finish(state: SwarmState) -> SwarmState:
    return state


def build_graph() -> Any:
    g = StateGraph(SwarmState)
    g.add_node("bootstrap", node_bootstrap)
    g.add_node("design_chapters", node_design_chapters)
    g.add_node("llm_enrichment", node_llm_enrichment)
    g.add_node("emit_artifacts", node_emit_artifacts)
    g.add_node("finish", node_finish)

    g.set_entry_point("bootstrap")
    g.add_edge("bootstrap", "design_chapters")
    g.add_edge("design_chapters", "llm_enrichment")
    g.add_edge("llm_enrichment", "emit_artifacts")
    g.add_edge("emit_artifacts", "finish")
    g.add_edge("finish", END)

    return g.compile()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NIC porting swarm planner with ClawTeam + LangGraph")
    p.add_argument("--team", default="nic-port-team", help="ClawTeam team name")
    p.add_argument("--goal", required=True, help="Overall mission goal")
    p.add_argument("--driver-repo", required=True, help="Linux driver repository path")
    p.add_argument("--linux-driver-path", required=True, help="Linux driver source path within repo")
    p.add_argument("--freebsd-target-path", required=True, help="FreeBSD target tree path")
    p.add_argument("--output-dir", default="artifacts/nic_porting", help="Output artifact directory")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not Path(args.driver_repo).exists():
        print(f"driver-repo does not exist: {args.driver_repo}", file=sys.stderr)
        return 2

    graph = build_graph()
    initial: SwarmState = {
        "team_name": args.team,
        "goal": args.goal,
        "driver_repo": str(Path(args.driver_repo).resolve()),
        "linux_driver_path": args.linux_driver_path,
        "freebsd_target_path": args.freebsd_target_path,
        "tasks": [],
        "chapters": [],
        "observations": [],
        "llm_refinement": "",
        "done": False,
        "output_dir": args.output_dir,
    }

    final_state = graph.invoke(initial)

    print("Swarm orchestration planning completed")
    print("Artifacts:")
    print(f"- {Path(args.output_dir).resolve() / 'transition_plan.json'}")
    print(f"- {Path(args.output_dir).resolve() / 'transition_plan.md'}")

    if final_state.get("llm_refinement"):
        print("LLM refinement: enabled")
    else:
        print("LLM refinement: skipped (set OPENAI_API_KEY to enable)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
