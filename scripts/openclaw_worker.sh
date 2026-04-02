#!/bin/bash
# =============================================================================
# OpenClaw non-interactive worker wrapper (v2.0 - audit remediation edition)
# =============================================================================
# Arguments:
#   $1 - team name
#   $2 - recipient
#   $3 - task content
#   $4 - (optional) parent agent ID for model inheritance
# =============================================================================

TEAM_NAME="$1"
RECIPIENT="$2"
TASK_CONTENT="$3"
PARENT_AGENT="${4:-}"

# -----------------------------------------------------------------------------
# 1. Force-load environment variables (audit remediation: env-loss bug fix)
# -----------------------------------------------------------------------------
# Load several possible .env locations
ENV_FILES=(
    "$HOME/.openclaw/.env"
    "$HOME/.openclaw/workspace/.env"
    "$HOME/.env"
    "./.env"
)

for ENV_FILE in "${ENV_FILES[@]}"; do
    if [ -f "$ENV_FILE" ]; then
        # Safe loading: skip comments and export line-by-line
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip empty lines and comments
            [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
            # Export env var
            export "$line" 2>/dev/null || true
        done < "$ENV_FILE"
    fi
done

# -----------------------------------------------------------------------------
# 2. Dynamic model inheritance (audit remediation: hard-coded config fix)
# -----------------------------------------------------------------------------
# Read current leader model settings
CURRENT_MODEL="${OPENCLAW_CURRENT_MODEL:-}"
CURRENT_PROVIDER="${OPENCLAW_CURRENT_PROVIDER:-}"

# If not found, try fallback inference from current session env
if [ -z "$CURRENT_MODEL" ]; then
    # Read OPENCLAW_MODEL if present
    CURRENT_MODEL="${OPENCLAW_MODEL:-}"
fi

# Build openclaw agent args
AGENT_CMD_ARGS=""

# Dynamically choose worker agent
if [ -n "$PARENT_AGENT" ]; then
    # If parent agent is provided, reuse the same config
    AGENT_CMD_ARGS="--agent $PARENT_AGENT"
else
    # Default to doubao, overridable via env var
    AGENT_CMD_ARGS="--agent ${OPENCLAW_WORKER_AGENT:-doubao}"
fi

# Pass model config to child agent if available
if [ -n "$CURRENT_MODEL" ]; then
    AGENT_CMD_ARGS="$AGENT_CMD_ARGS --model $CURRENT_MODEL"
fi

# -----------------------------------------------------------------------------
# 3. Execute task (disable cache, force real-time request)
# -----------------------------------------------------------------------------
# Set paths
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/bin"
export OPENCLAW_CONFIG_PATH="$HOME/.openclaw/openclaw.json"
export OPENCLAW_WORKSPACE="$HOME/.openclaw/workspace"

# Write execution log
LOG_FILE="/tmp/worker_$(date +%Y%m%d_%H%M%S).log"
echo "=== Worker Execution Log ===" > "$LOG_FILE"
echo "Time: $(date)" >> "$LOG_FILE"
echo "Team: $TEAM_NAME" >> "$LOG_FILE"
echo "Recipient: $RECIPIENT" >> "$LOG_FILE"
echo "Agent Args: $AGENT_CMD_ARGS" >> "$LOG_FILE"
echo "Environment Check:" >> "$LOG_FILE"
echo "  TAVILY_API_KEY: ${TAVILY_API_KEY:+set (${#TAVILY_API_KEY} chars)}" >> "$LOG_FILE"
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:+set (${#OPENAI_API_KEY} chars)}" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

# Execute task (attempt no-cache semantics for real-time behavior)
# Note: openclaw agent may not support --no-cache in all versions.
RESULT=$(openclaw agent --local $AGENT_CMD_ARGS \
    --message "$TASK_CONTENT" \
    --thinking off \
    --timeout 120 \
    2>&1 | tee -a "$LOG_FILE")

# Check whether cache was used (audit-critical check)
if echo "$RESULT" | grep -qi "cache"; then
    echo "WARNING: cache usage detected; this may violate real-time data requirements" >> "$LOG_FILE"
fi

# -----------------------------------------------------------------------------
# 4. Send result to inbox
# -----------------------------------------------------------------------------
# Resolve clawteam binary: prefer CLAWTEAM_BIN env var, then PATH; fail fast if not found
CLAWTEAM_CMD="${CLAWTEAM_BIN:-$(command -v clawteam 2>/dev/null)}"
if [[ -z "$CLAWTEAM_CMD" ]]; then
    echo "ERROR: 'clawteam' not found on PATH and CLAWTEAM_BIN is not set. Please install clawteam or set CLAWTEAM_BIN." >&2
    exit 1
fi
SEND_RESULT=$("$CLAWTEAM_CMD" inbox send "$TEAM_NAME" "$RECIPIENT" "$RESULT" 2>&1)
echo "Send result: $SEND_RESULT" >> "$LOG_FILE"

# 5. Clean exit
exit 0