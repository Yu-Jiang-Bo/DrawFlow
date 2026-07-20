#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ -s "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null && is_drawflow_pid "$pid"; then
    echo "DrawFlow running: PID=$pid URL=http://$HOST:$PORT"
    exit 0
  fi
fi

if port_in_use; then
  echo "Port $PORT is occupied by another process; DrawFlow PID is not known." >&2
  exit 2
fi

echo "DrawFlow is not running."
exit 1
