"""Configuration, logging, and static-file policy for the local gateway."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys


LOGGER = logging.getLogger("drawflow.local_gateway")
V2_WORKBENCH_STATIC_DIR = Path(__file__).resolve().parent / "static" / "v2-workbench"

V2_STATIC_FILES = {
    "workbench.css",
    "workbench-stages.css",
    "workbench.js",
    "workbench-dom.js",
    "workbench-api.js",
    "workbench-scan-model.js",
    "workbench-form-model.js",
    "workbench-config.js",
    "workbench-content.js",
    "workbench-style-dimensions.js",
    "workbench-option-rules.js",
    "workbench-rule-evidence.js",
    "workbench-view.js",
    "workbench-stage-view.js",
    "workbench-preview-state.js",
    "workbench-preview-versions.js",
    "workbench-preview.js",
    "workbench-preview-actions.js",
    "workbench-view-tables.js",
    "workbench-validation-checks.js",
    "workbench-validation-targets.js",
    "workbench-validation-navigation.js",
    "workbench-validation-blockers.js",
    "workbench-structure-tree.js",
    "workbench-draft-actions.js",
    "workbench-published-actions.js",
    "workbench-scan-actions.js",
}


def _normalized_log_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def safe_static_name(value: str) -> str:
    name = Path(value).name
    return name if name == value and name in V2_STATIC_FILES else ""


def default_central_url() -> str:
    configured = os.environ.get("DRAWFLOW_CENTRAL_URL", "").strip()
    if configured:
        return configured
    for path in client_config_candidates():
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                central_url = str(data.get("central_url") or "").strip()
                if central_url:
                    return central_url
        except Exception:
            continue
    return "http://127.0.0.1:8765"


def client_config_candidates() -> list[Path]:
    candidates = [Path.cwd() / "drawflow-client.json"]
    if getattr(sys, "frozen", False):
        candidates.insert(
            0,
            Path(sys.executable).resolve().with_name("drawflow-client.json"),
        )
    return candidates


def configure_local_logging(data_dir: Path) -> None:
    log_path = data_dir / "logs" / "drawflow-client.log"
    fallback_log_path = log_path.with_name(f"drawflow-client-{os.getpid()}.log")
    normalized_log_paths = {
        _normalized_log_path(log_path),
        _normalized_log_path(fallback_log_path),
    }
    if any(
        _normalized_log_path(getattr(handler, "baseFilename", "")) in normalized_log_paths
        for handler in LOGGER.handlers
        if getattr(handler, "baseFilename", "")
    ):
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        # A previously started client can briefly retain the shared log file on
        # Windows. Logging must not prevent a new local gateway from starting.
        try:
            handler = logging.FileHandler(
                fallback_log_path,
                encoding="utf-8",
            )
        except OSError:
            if not any(
                isinstance(existing, logging.NullHandler) for existing in LOGGER.handlers
            ):
                LOGGER.addHandler(logging.NullHandler())
            LOGGER.setLevel(logging.INFO)
            LOGGER.propagate = False
            return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


__all__ = [
    "LOGGER",
    "V2_WORKBENCH_STATIC_DIR",
    "client_config_candidates",
    "configure_local_logging",
    "default_central_url",
    "safe_static_name",
]
