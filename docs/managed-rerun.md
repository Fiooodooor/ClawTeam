# Managed Rerun Runbook for NIC Orchestrator v2

This runbook captures a repeatable, one-command flow for controlled reruns of the orchestrator.
It includes cleanup, checkpoint reset, launch, monitoring, stuck-agent handling, and final reporting.

## What this solves

- Prevents stale OpenClaw session lock issues from prior runs.
- Ensures the project virtual environment is used (instead of system Python).
- Resets orchestrator state to a clean phase-0 start.
- Produces a consistent final summary for compare-across-reruns analysis.

## One-command automation

Use:

```bash
cd /root/claw-team
chmod +x scripts/managed_rerun.sh
scripts/managed_rerun.sh
```

This executes all 7 managed steps in sequence.

## The 7 managed steps (expanded)

### 1) Activate and validate Python environment

The script uses `ROOT_DIR/.venv` by default and validates required modules.

Why: previous failures happened when background runs used `/usr/bin/python3` instead of the venv.

### 2) Kill lingering orchestrator and agent processes

It terminates stale `nic_porting_orchestrator_v2.py` and `openclaw` processes.

Why: stale worker loops can survive and interfere with fresh runs.

### 3) Clean stale runtime files

It removes:

- `~/.openclaw/agents/main/sessions/*.jsonl`
- `~/.openclaw/agents/main/sessions/*.lock`
- `~/.clawteam/teams/<team>/agent-logs/*.log`
- `~/.clawteam/teams/<team>/spawn-registry.json`

Why: stale session and lock files can cause OpenClaw lock contention and session reuse bugs.

### 4) Reset orchestrator checkpoint

If `orchestrator_checkpoint.json` exists, it resets:

- `current_phase = 0`
- clears `iteration_events`
- clears `spawned_agents`
- clears `phase_results`
- resets `task_ledger` statuses to `planned`

Why: without reset, `--resume` can jump to later phases and preserve stale task state.

### 5) Launch orchestrator

The script launches:

```bash
python3 examples/nic_porting_orchestrator_v2.py \
  --team ... \
  --driver-name ... \
  --goal ... \
  --driver-repo ... \
  --linux-driver-path ... \
  --freebsd-target-path ... \
  --backend subprocess \
  --agent-command openclaw agent \
  --timeout-seconds 3600 \
  --max-iterations 150 \
  --output-dir ... \
  --resume
```

Why: this is the known-good command pattern for this workflow.

### 6) Monitor progress loop

At each poll interval, it prints:

- active `openclaw` process count
- total agent log bytes
- checkpoint last iteration and elapsed time
- stagnant-rounds count (log size unchanged)

Why: process count alone is insufficient; log growth and checkpoint heartbeat indicate real progress.

### 7) Final summary extraction

At the end, it prints:

- task ledger status counts
- per-agent status lines
- tail of `orchestrator_summary.md`

Why: gives a quick compare baseline for each rerun.

## Script file

- `scripts/managed_rerun.sh`

## Configuration (env vars)

Defaults are tuned for your current ixgbe rerun setup.

```bash
ROOT_DIR=/root/claw-team
VENV_DIR=/root/claw-team/.venv
TEAM=nic-port-v2-rerun7
DRIVER_NAME=ixgbe
GOAL="Port Linux ixgbe driver to FreeBSD using native OAL seam layer with zero runtime overhead"
DRIVER_REPO=/root/claw-team/artifacts/ethernet-linux-ixgbe-live
LINUX_DRIVER_PATH=src
FREEBSD_TARGET_PATH=freebsd/src
BACKEND=subprocess
AGENT_COMMAND="openclaw agent"
TIMEOUT_SECONDS=3600
MAX_ITERATIONS=150
OUTPUT_DIR=/root/claw-team/artifacts/nic_porting_v2_rerun7
POLL_SECONDS=30
FORCE_KILL_STUCK=0
```

Override per run as needed.

## Usage examples

### Default run

```bash
cd /root/claw-team
scripts/managed_rerun.sh
```

### Run with faster polling and forced residual process cleanup

```bash
cd /root/claw-team
POLL_SECONDS=15 FORCE_KILL_STUCK=1 scripts/managed_rerun.sh
```

### Run without resume and without monitor (fire-and-return)

```bash
cd /root/claw-team
scripts/managed_rerun.sh --no-resume --no-monitor
```

### Change team and output directory

```bash
cd /root/claw-team
TEAM=nic-port-v2-rerun8 OUTPUT_DIR=/root/claw-team/artifacts/nic_porting_v2_rerun8 scripts/managed_rerun.sh
```

## Reiterated operator guidance

- Always run from venv-backed shell context.
- Always clean OpenClaw sessions and lock files before rerun.
- Always reset checkpoint if using `--resume` with rerun semantics.
- Track both checkpoint iteration movement and log-byte growth.
- If a worker is clearly stuck in idle loop after run completion, use `FORCE_KILL_STUCK=1`.

## Expected outputs

The script prints progress continuously and generates/updates:

- `artifacts/nic_porting_v2_rerun7/orchestrator_checkpoint.json`
- `artifacts/nic_porting_v2_rerun7/orchestrator_summary.md`
- `artifacts/nic_porting_v2_rerun7/orchestrator_summary.json`
- `artifacts/nic_porting_v2_rerun7/task_ledger.json`
- `artifacts/nic_porting_v2_rerun7/risk_register.json`

## Troubleshooting quick checks

```bash
# Is the right python used?
source /root/claw-team/.venv/bin/activate
which python3

# Are sessions cleaned?
ls ~/.openclaw/agents/main/sessions/*.lock 2>/dev/null | wc -l

# Are agents still running?
pgrep -af openclaw

# Is checkpoint moving?
python3 - <<'PY'
import json
cp = '/root/claw-team/artifacts/nic_porting_v2_rerun7/orchestrator_checkpoint.json'
d = json.load(open(cp))
ev = d.get('iteration_events', [])
print(ev[-1] if ev else 'no events')
PY
```
