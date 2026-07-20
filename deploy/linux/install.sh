#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Python 3 and the venv package with the Linux package manager." >&2
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required." >&2
  python3 --version >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  python3 -m venv "$VENV_DIR" || {
    echo "Failed to create the virtual environment. Install python3-venv and retry." >&2
    exit 1
  }
fi

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
ensure_runtime_dirs

printf 'DrawFlow Linux install complete.\nProject: %s\nData: %s\n' "$PROJECT_ROOT" "$DATA_DIR"
