#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
require_python
ensure_runtime_dirs

if [[ -s "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null && is_drawflow_pid "$old_pid"; then
    echo "DrawFlow is already running with PID $old_pid." >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if port_in_use; then
  echo "Port $PORT is already in use. DrawFlow will not stop another service." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
nohup "$PYTHON" -u -m src.service.http_server \
  --role central --host "$HOST" --port "$PORT" \
  >"$LOG_DIR/drawflow.log" 2>"$LOG_DIR/drawflow.error.log" < /dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
sleep 1

if ! kill -0 "$pid" 2>/dev/null || ! is_drawflow_pid "$pid"; then
  echo "DrawFlow failed to start. Check $LOG_DIR/drawflow.error.log" >&2
  rm -f "$PID_FILE"
  exit 1
fi

echo "Started DrawFlow central service with PID $pid on http://$HOST:$PORT"
echo "Logs: $LOG_DIR/drawflow.log and $LOG_DIR/drawflow.error.log"
