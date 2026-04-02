#!/usr/bin/env bash
set -euo pipefail

# Managed rerun helper for NIC orchestrator v2.
# Automates:
# 1) environment setup
# 2) stale process cleanup
# 3) session/log/registry cleanup
# 4) checkpoint reset
# 5) orchestrator launch
# 6) progress monitoring
# 7) final summary extraction

ROOT_DIR="${ROOT_DIR:-/root/claw-team}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
TEAM="${TEAM:-nic-port-v2-rerun7}"
DRIVER_NAME="${DRIVER_NAME:-ixgbe}"
GOAL="${GOAL:-Port Linux ixgbe driver to FreeBSD using native OAL seam layer with zero runtime overhead}"
DRIVER_REPO="${DRIVER_REPO:-$ROOT_DIR/artifacts/ethernet-linux-ixgbe-live}"
LINUX_DRIVER_PATH="${LINUX_DRIVER_PATH:-src}"
FREEBSD_TARGET_PATH="${FREEBSD_TARGET_PATH:-freebsd/src}"
BACKEND="${BACKEND:-subprocess}"
AGENT_COMMAND="${AGENT_COMMAND:-openclaw agent}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-3600}"
MAX_ITERATIONS="${MAX_ITERATIONS:-150}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/artifacts/nic_porting_v2_rerun7}"
POLL_SECONDS="${POLL_SECONDS:-30}"
FORCE_KILL_STUCK="${FORCE_KILL_STUCK:-0}"

checkpoint_path="$OUTPUT_DIR/orchestrator_checkpoint.json"
sessions_dir="${HOME}/.openclaw/agents/main/sessions"
team_data_dir="${HOME}/.clawteam/teams/$TEAM"
agent_logs_dir="$team_data_dir/agent-logs"
spawn_registry="$team_data_dir/spawn-registry.json"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing command: $1" >&2
    exit 1
  fi
}

print_header() {
  echo
  echo "=== $1 ==="
}

step() {
  echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

# Parse minimal flags while keeping env-variable support.
RESUME=1
MONITOR=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-resume)
      RESUME=0
      shift
      ;;
    --no-monitor)
      MONITOR=0
      shift
      ;;
    --force-kill-stuck)
      FORCE_KILL_STUCK=1
      shift
      ;;
    -h|--help)
      cat <<'HELP'
Usage: scripts/managed_rerun.sh [options]

Options:
  --no-resume         Run without orchestrator --resume flag.
  --no-monitor        Launch and return immediately.
  --force-kill-stuck  Kill remaining openclaw processes after max iterations.
  -h, --help          Show this help.

Configuration is controlled via env vars:
  ROOT_DIR, VENV_DIR, TEAM, DRIVER_NAME, GOAL, DRIVER_REPO,
  LINUX_DRIVER_PATH, FREEBSD_TARGET_PATH, BACKEND, AGENT_COMMAND,
  TIMEOUT_SECONDS, MAX_ITERATIONS, OUTPUT_DIR, POLL_SECONDS,
  FORCE_KILL_STUCK
HELP
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

print_header "Managed Rerun Start"
require_cmd python3
require_cmd pgrep
require_cmd pkill
require_cmd awk
require_cmd wc

if [[ ! -d "$ROOT_DIR" ]]; then
  echo "ERROR: ROOT_DIR does not exist: $ROOT_DIR" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/examples/nic_porting_orchestrator_v2.py" ]]; then
  echo "ERROR: orchestrator script not found in $ROOT_DIR/examples" >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "ERROR: VENV_DIR does not exist: $VENV_DIR" >&2
  exit 1
fi

step "1/7 Activate environment"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python3 - <<'PY'
mods = ["jsonpointer", "langchain_core"]
missing = []
for m in mods:
  try:
    __import__(m)
  except Exception:
    missing.append(m)
if missing:
  raise SystemExit("Missing python modules: " + ", ".join(missing))
print("Python environment check: OK")
PY

step "2/7 Kill lingering orchestrator/agent processes"
pkill -f "nic_porting_orchestrator_v2.py" 2>/dev/null || true
pkill -f openclaw 2>/dev/null || true

step "3/7 Clean sessions/logs/registry"
mkdir -p "$sessions_dir" "$agent_logs_dir" "$OUTPUT_DIR"
rm -f "$sessions_dir"/*.jsonl "$sessions_dir"/*.lock 2>/dev/null || true
rm -f "$agent_logs_dir"/*.log 2>/dev/null || true
rm -f "$spawn_registry" 2>/dev/null || true

step "4/7 Reset checkpoint"
if [[ -f "$checkpoint_path" ]]; then
  python3 - <<PY
import json
cp = r"$checkpoint_path"
with open(cp, "r", encoding="utf-8") as f:
    d = json.load(f)
d["current_phase"] = 0
d["iteration_events"] = []
d["spawned_agents"] = []
d["phase_results"] = {}
for e in d.get("task_ledger", []):
    e["status"] = "planned"
    e.pop("completed_at", None)
with open(cp, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2)
print("Checkpoint reset complete")
PY
else
  step "Checkpoint not found yet; launch will create it"
fi

step "5/7 Launch orchestrator"
read -r -a agent_command_array <<< "$AGENT_COMMAND"
cmd=(
  python3 "$ROOT_DIR/examples/nic_porting_orchestrator_v2.py"
  --team "$TEAM"
  --driver-name "$DRIVER_NAME"
  --goal "$GOAL"
  --driver-repo "$DRIVER_REPO"
  --linux-driver-path "$LINUX_DRIVER_PATH"
  --freebsd-target-path "$FREEBSD_TARGET_PATH"
  --backend "$BACKEND"
  --agent-command "${agent_command_array[@]}"
  --timeout-seconds "$TIMEOUT_SECONDS"
  --max-iterations "$MAX_ITERATIONS"
  --output-dir "$OUTPUT_DIR"
)

if [[ "$RESUME" -eq 1 ]]; then
  cmd+=(--resume)
fi

(
  cd "$ROOT_DIR"
  "${cmd[@]}"
) &
orchestrator_pid=$!
step "Orchestrator PID: $orchestrator_pid"

if [[ "$MONITOR" -eq 0 ]]; then
  step "Monitoring disabled (--no-monitor)."
  exit 0
fi

step "6/7 Monitor progress"
last_log_total=0
stagnant_rounds=0

while kill -0 "$orchestrator_pid" 2>/dev/null; do
  sleep "$POLL_SECONDS"

  proc_count="0"
  if pgrep -c openclaw >/dev/null 2>&1; then
    proc_count="$(pgrep -c openclaw)"
  fi

  log_total="0"
  if compgen -G "$agent_logs_dir/*.log" >/dev/null; then
    log_total="$(wc -c "$agent_logs_dir"/*.log | awk 'END{print $1}')"
  fi

  iter_info="none"
  if [[ -f "$checkpoint_path" ]]; then
    iter_info="$(python3 - <<PY
import json
cp = r"$checkpoint_path"
try:
    d = json.load(open(cp, "r", encoding="utf-8"))
    ev = d.get("iteration_events", [])
    if ev:
        x = ev[-1]
        print(f"iter={x.get('iteration')} elapsed={x.get('elapsed_seconds')}s")
    else:
        print("iter=none")
except Exception:
    print("iter=unreadable")
PY
)"
  fi

  if [[ "$log_total" == "$last_log_total" ]]; then
    stagnant_rounds=$((stagnant_rounds + 1))
  else
    stagnant_rounds=0
    last_log_total="$log_total"
  fi

  step "progress: openclaw_procs=$proc_count logs_total_bytes=$log_total $iter_info stagnant_rounds=$stagnant_rounds"
done

step "Orchestrator process exited"

if [[ "$FORCE_KILL_STUCK" -eq 1 ]]; then
  # Optional cleanup if a worker loop remains active after orchestrator exits.
  pkill -f openclaw 2>/dev/null || true
  step "force-kill enabled: terminated residual openclaw processes"
fi

step "7/7 Print final summary"
summary_md="$OUTPUT_DIR/orchestrator_summary.md"
task_ledger="$OUTPUT_DIR/task_ledger.json"

if [[ -f "$task_ledger" ]]; then
  python3 - <<PY
import json
p = r"$task_ledger"
tl = json.load(open(p, "r", encoding="utf-8"))
counts = {}
for e in tl:
    counts[e.get("status", "unknown")] = counts.get(e.get("status", "unknown"), 0) + 1
print("Task ledger counts:", counts)
for e in tl:
    print(f" - {e.get('assigned_to','?'):25} {e.get('status','?'):12} phase={e.get('phase_key','?')}")
PY
else
  echo "Task ledger not found: $task_ledger"
fi

if [[ -f "$summary_md" ]]; then
  echo
  echo "Summary file: $summary_md"
  echo "Tail (last 20 lines):"
  tail -20 "$summary_md"
else
  echo "Summary file not found: $summary_md"
fi

print_header "Managed Rerun Complete"
