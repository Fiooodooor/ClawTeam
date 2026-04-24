---
name: clawteam-manage
description: >
  Unified management CLI for ClawTeam NIC orchestrator runs. Use when the user asks to
  "check orchestrator status", "show run progress", "view task phases", "inspect checkpoint",
  "show ready tasks", "list pending tasks", "view phase progress", "clean stale sessions",
  "kill orchestrator", "reset checkpoint", "run managed rerun", "tail agent logs",
  "watch orchestrator", "show run summary", "inspect task board", "diagnose stuck run",
  "check stale locks", "monitor nic porting", or mentions "clawteam-manage", "managed rerun",
  "orchestrator diagnostics", "nic porting status", "rerun orchestrator". Wraps all ad-hoc
  diagnostic commands into a single script with subcommands for status, tasks, phases,
  checkpoint, clean, kill, reset, rerun, logs, watch, and summary.
---

# ClawTeam Management CLI

`scripts/clawteam-manage.sh` is a unified management script for ClawTeam NIC orchestrator runs.
It consolidates status checking, task board queries, checkpoint inspection, cleanup, process
management, and managed reruns into a single entry point.

## Prerequisites

- `clawteam` CLI installed (`pip install clawteam`)
- `python3` with access to the project venv
- `pgrep`/`pkill` available (standard Linux)
- For `rerun`: `jsonpointer` and `langchain_core` Python modules in the venv
- The orchestrator script at `$ROOT_DIR/examples/nic_porting_orchestrator_v2.py`

## Script Location

```
scripts/clawteam-manage.sh
```

## When to Use Each Command

| Situation | Command |
|-----------|---------|
| Quick health check of a running or finished orchestrator | `status` |
| See all tasks with statuses, owners, phases | `tasks` |
| See only pending tasks filtered by status | `tasks pending` |
| Find tasks that are ready to assign/run right now | `ready` |
| Per-phase progress with visual bars | `phases` |
| Deep checkpoint state: iterations, agents, task ledger | `checkpoint` |
| Raw JSON structure of a specific task | `inspect 0` |
| View end-of-run results | `summary` |
| Tail recent agent output | `logs` or `logs 50` |
| Continuously watch a running orchestrator | `watch` or `watch 10` |
| Clear stale locks/sessions before a fresh run | `clean` |
| Stop all orchestrator and agent processes | `kill` |
| Reset checkpoint back to phase 0 for re-run | `reset` |
| Full automated rerun (clean+reset+launch+monitor+summary) | `rerun` |

## Command Reference

### status — Quick overview

Shows orchestrator process state, checkpoint phase, iteration count, spawned agents,
task ledger counts, ClawTeam board counts, agent log bytes, and stale session locks.

```bash
scripts/clawteam-manage.sh status
```

### tasks — Full task board

Lists all tasks from the ClawTeam board with color-coded statuses.
Optional status filter.

```bash
scripts/clawteam-manage.sh tasks
scripts/clawteam-manage.sh tasks pending
scripts/clawteam-manage.sh tasks completed
scripts/clawteam-manage.sh tasks in_progress
```

### ready — Pending unblocked tasks

Separates pending tasks into "ready" (no blockers) and "blocked" (has `blockedBy` dependencies).

```bash
scripts/clawteam-manage.sh ready
```

### phases — Per-phase progress

Aggregates tasks by `metadata.phase_key` and shows progress bars with completion percentages.

```bash
scripts/clawteam-manage.sh phases
```

### checkpoint — Detailed checkpoint inspection

Shows `current_phase`, `phase_results` keys, spawned agent count, iteration events,
task ledger detail with per-task phase and agent assignments.

```bash
scripts/clawteam-manage.sh checkpoint
```

### inspect — Raw task JSON

Dumps the raw JSON of the Nth task from the ClawTeam board (0-indexed).

```bash
scripts/clawteam-manage.sh inspect 0
scripts/clawteam-manage.sh inspect 5
```

### summary — Final run results

Prints task ledger status counts with per-agent/phase detail, plus the tail of
`orchestrator_summary.md`.

```bash
scripts/clawteam-manage.sh summary
```

### logs — Tail agent logs

Shows the last N lines (default 30) of each agent's log file.

```bash
scripts/clawteam-manage.sh logs
scripts/clawteam-manage.sh logs 50
```

### watch — Live dashboard

Clears the terminal and refreshes `status` output at a fixed interval. Ctrl+C to stop.

```bash
scripts/clawteam-manage.sh watch
scripts/clawteam-manage.sh watch 10
```

### clean — Remove stale runtime files

Removes `*.jsonl`, `*.lock` from openclaw sessions, `*.log` from agent-logs,
and the spawn registry.

```bash
scripts/clawteam-manage.sh clean
```

### kill — Terminate processes

Kills `nic_porting_orchestrator_v2.py` and team-scoped `openclaw` processes.

```bash
scripts/clawteam-manage.sh kill
```

### reset — Reset checkpoint to phase 0

Resets `current_phase=0`, clears `iteration_events`, `spawned_agents`, `phase_results`,
and sets all task ledger entries to `planned`.

```bash
scripts/clawteam-manage.sh reset
```

### rerun — Full managed rerun

Executes all 7 steps in sequence: validate env → kill processes → clean files →
reset checkpoint → launch orchestrator → monitor progress → print summary.

```bash
scripts/clawteam-manage.sh rerun
scripts/clawteam-manage.sh rerun --no-resume
scripts/clawteam-manage.sh rerun --no-monitor
```

## Configuration via Environment Variables

All defaults can be overridden per-invocation:

```bash
TEAM=nic-port-v2-rerun8 \
OUTPUT_DIR=/root/claw-team/artifacts/nic_porting_v2_rerun8 \
scripts/clawteam-manage.sh status
```

| Variable | Default |
|----------|---------|
| `ROOT_DIR` | `/root/claw-team` |
| `VENV_DIR` | `$ROOT_DIR/.venv` |
| `TEAM` | `nic-port-v2-rerun7` |
| `DRIVER_NAME` | `ixgbe` |
| `GOAL` | Port Linux nic driver to FreeBSD... |
| `DRIVER_REPO` | `$ROOT_DIR/artifacts/ethernet-linux-ixgbe-live` |
| `LINUX_DRIVER_PATH` | `src` |
| `FREEBSD_TARGET_PATH` | `freebsd/src` |
| `BACKEND` | `subprocess` |
| `AGENT_COMMAND` | `openclaw agent` |
| `TIMEOUT_SECONDS` | `3600` |
| `MAX_ITERATIONS` | `150` |
| `OUTPUT_DIR` | `$ROOT_DIR/artifacts/nic_porting_v2_rerun7` |
| `POLL_SECONDS` | `30` |
| `FORCE_KILL_STUCK` | `0` |

## Typical Workflows

### Diagnose a stuck run

```bash
scripts/clawteam-manage.sh status      # Check processes and stagnation
scripts/clawteam-manage.sh ready       # Are there unblocked tasks?
scripts/clawteam-manage.sh phases      # Which phase is stuck?
scripts/clawteam-manage.sh logs 100    # What are agents doing?
scripts/clawteam-manage.sh checkpoint  # Is the checkpoint advancing?
```

### Clean restart

```bash
scripts/clawteam-manage.sh kill
scripts/clawteam-manage.sh clean
scripts/clawteam-manage.sh reset
scripts/clawteam-manage.sh rerun
```

### Compare across reruns

```bash
TEAM=nic-port-v2-rerun7 OUTPUT_DIR=.../rerun7 scripts/clawteam-manage.sh summary
TEAM=nic-port-v2-rerun8 OUTPUT_DIR=.../rerun8 scripts/clawteam-manage.sh summary
```

### Monitor a running orchestrator in real time

```bash
scripts/clawteam-manage.sh watch 15
```

## Relationship to Submodule Script

This script is the **root-repository counterpart** of `submodules/clawteam/scripts/managed_rerun.sh`.
It provides the same 7-step managed rerun capability, plus adds standalone diagnostic subcommands
(`status`, `tasks`, `ready`, `phases`, `checkpoint`, `inspect`, `logs`, `watch`) that the
submodule script does not offer. The `rerun` subcommand here delegates to the same orchestrator
entry point with the same arguments and environment variables.
