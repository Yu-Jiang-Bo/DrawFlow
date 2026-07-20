#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

ENV_FILE="${DRAWFLOW_ENV_FILE:-$PROJECT_ROOT/drawflow.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

VENV_DIR="${DRAWFLOW_VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON="${DRAWFLOW_PYTHON:-$VENV_DIR/bin/python}"
HOST="${DRAWFLOW_HOST:-0.0.0.0}"
PORT="${DRAWFLOW_PORT:-8765}"
DATA_DIR="${DRAWFLOW_DATA_DIR:-$PROJECT_ROOT/drawflow-data}"
LOG_DIR="${DRAWFLOW_LOG_DIR:-$PROJECT_ROOT/output/logs}"
PID_FILE="${DRAWFLOW_PID_FILE:-$LOG_DIR/drawflow.pid}"

export DRAWFLOW_HOST="$HOST"
export DRAWFLOW_PORT="$PORT"
export DRAWFLOW_DATA_DIR="$DATA_DIR"
export DRAWFLOW_LOG_DIR="$LOG_DIR"
export DRAWFLOW_PID_FILE="$PID_FILE"

require_python() {
  if [[ ! -x "$PYTHON" ]]; then
    echo "DrawFlow Python environment is missing: $PYTHON" >&2
    echo "Run deploy/linux/install.sh first." >&2
    exit 1
  fi
}

port_in_use() {
  if ! command -v ss >/dev/null 2>&1; then
    return 1
  fi
  ss -ltnH | awk -v port=":$PORT" '$4 ~ port "$" { found=1 } END { exit found ? 0 : 1 }'
}

is_drawflow_pid() {
  local pid="$1"
  [[ -r "/proc/$pid/cmdline" ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -Fq 'src.service.http_server'
}

ensure_runtime_dirs() {
  mkdir -p "$DATA_DIR" "$LOG_DIR"
}
