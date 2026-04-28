#!/usr/bin/env bash
# ClawTeam user-level installer.
#
# Installs the PyPI package into ~/.clawteam/.venv and links ~/.local/bin/clawteam.

set -euo pipefail

CLAWTEAM_HOME="${CLAWTEAM_HOME:-$HOME/.clawteam}"
VENV_PATH="${CLAWTEAM_HOME}/.venv"
BIN_DIR="${HOME}/.local/bin"
PYTHON_BIN="${PYTHON_BIN:-}"

log() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

python_version_ok() {
  local bin="$1"
  "$bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

try_python_bin() {
  local bin="$1"
  [ -n "$bin" ] || return 1
  command -v "$bin" >/dev/null 2>&1 || return 1
  python_version_ok "$bin" || return 1
  command -v "$bin"
}

detect_python_bin() {
  if [ -n "$PYTHON_BIN" ]; then
    try_python_bin "$PYTHON_BIN" && return 0
    log "Requested PYTHON_BIN=$PYTHON_BIN is not Python 3.10+"
  fi
  for candidate in python3.12 python3.11 python3.10 python3; do
    try_python_bin "$candidate" && return 0
  done
  return 1
}

if ! PYTHON_BIN="$(detect_python_bin)"; then
  fail "Python 3.10+ is required to install ClawTeam"
fi

log "Using Python: $("$PYTHON_BIN" --version 2>&1)"
mkdir -p "$CLAWTEAM_HOME" "$BIN_DIR"

if [ ! -x "${VENV_PATH}/bin/python" ]; then
  log "Creating virtual environment at ${VENV_PATH}"
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

log "Installing latest clawteam from PyPI"
"${VENV_PATH}/bin/pip" install --upgrade pip >/dev/null
"${VENV_PATH}/bin/pip" install --upgrade clawteam

ln -sf "${VENV_PATH}/bin/clawteam" "${BIN_DIR}/clawteam"
log "Linked clawteam -> ${BIN_DIR}/clawteam"

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) log "Add ${BIN_DIR} to PATH to use clawteam in every shell." ;;
esac

log "ClawTeam is ready."
