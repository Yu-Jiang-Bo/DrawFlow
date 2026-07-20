#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ ! -s "$PID_FILE" ]]; then
  echo "DrawFlow PID file not found: $PID_FILE"
  exit 0
fi

pid="$(cat "$PID_FILE")"
if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "DrawFlow process is not running."
  exit 0
fi

if ! is_drawflow_pid "$pid"; then
  echo "PID file does not identify a DrawFlow process; refusing to stop PID $pid." >&2
  exit 1
fi

kill -TERM "$pid"
for _ in {1..20}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Stopped DrawFlow PID $pid."
    exit 0
  fi
  sleep 0.5
done

echo "DrawFlow did not stop after 10 seconds; refusing to force-kill it." >&2
exit 1
