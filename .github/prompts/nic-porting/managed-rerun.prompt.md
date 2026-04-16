---
name: managed-rerun
description: "Execute a managed rerun of the NIC porting orchestrator with cleanup, reset, launch, monitoring, and summary."
argument-hint: "Team name, driver, target OS, and any overrides (e.g. max iterations, timeout)"
agent: nic-porting-orchestrator
tools: ['execute/runInTerminal', 'search', 'search/codebase']
---
Perform a managed rerun of the NIC porting orchestrator for:

${input:Team name, driver, and any parameter overrides}

## Rerun Protocol
Execute these steps in strict sequence. Stop and report if any step fails.

### Step 1 — Environment Validation
Confirm the Python venv, clawteam CLI, and orchestrator script are available.

### Step 2 — Kill Stale Processes
Terminate any running orchestrator and agent processes for the target team.
Equivalent to: `scripts/clawteam-manage.sh kill`

### Step 3 — Clean Runtime State
Remove stale session files, lock files, and agent logs.
Equivalent to: `scripts/clawteam-manage.sh clean`

### Step 4 — Reset Checkpoint
Reset the orchestrator checkpoint to phase 0 with all tasks set to planned.
Equivalent to: `scripts/clawteam-manage.sh reset`

### Step 5 — Launch Orchestrator
Start the orchestrator in background with configured parameters.
Equivalent to: `scripts/clawteam-manage.sh rerun`

### Step 6 — Monitor Progress
Poll status at 30-second intervals. Report phase transitions and task completions.
Watch for stagnation (no progress for 5 minutes).
Equivalent to: `scripts/clawteam-manage.sh watch`

### Step 7 — Produce Summary
When done or timed out, generate the final summary with task completion rates,
gate scores, and any open risks.
Equivalent to: `scripts/clawteam-manage.sh summary`

## Environment Variables
Override defaults by specifying in the input:
- TEAM (default: nic-port-v2-rerun7)
- DRIVER_NAME (default: ixgbe)
- MAX_ITERATIONS (default: 150)
- TIMEOUT_SECONDS (default: 3600)
- OUTPUT_DIR (default: artifacts/nic_porting_v2_rerun7)

## Failure Handling
- If kill/clean/reset fails: stop and report the error.
- If the orchestrator fails to start: check venv and script paths.
- If monitoring detects stagnation: run diagnostics (ready tasks, checkpoint state).
- If gate scores are below thresholds after completion: flag for manual review.
