#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
require_python
ensure_runtime_dirs

if port_in_use; then
  echo "Port $PORT is already in use. DrawFlow will not stop another service." >&2
  exit 1
fi

echo "Starting DrawFlow central service on http://$HOST:$PORT"
cd "$PROJECT_ROOT"
exec "$PYTHON" -u -m src.service.http_server --role central --host "$HOST" --port "$PORT"
