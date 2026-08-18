"""Shared Illustrator batch execution for production outputs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from ..renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError, format_com_recovery_message


PRODUCTION_BATCH_COM_RETRY_ATTEMPTS = 3
PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS = 3.0
PRODUCTION_BATCH_CHUNK_DELAY_SECONDS = 1.0


def render_production_batch_files(batch_files: Iterable[Path], visible: bool) -> None:
    """Render production batch task files through one reusable Illustrator session."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        for batch_file in batch_files:
            _render_production_batch_chunk(bridge, script, Path(batch_file))
            time.sleep(PRODUCTION_BATCH_CHUNK_DELAY_SECONDS)
    finally:
        bridge.close()


def _render_production_batch_chunk(bridge: IllustratorBridge, script: Path, task_file: Path) -> None:
    for attempt in range(PRODUCTION_BATCH_COM_RETRY_ATTEMPTS):
        try:
            bridge.render(script, task_file)
            return
        except IllustratorBridgeError as exc:
            if attempt + 1 >= PRODUCTION_BATCH_COM_RETRY_ATTEMPTS or not _is_retryable_com_failure(exc):
                if _is_retryable_com_failure(exc):
                    raise IllustratorBridgeError(format_com_recovery_message(exc, retries=attempt)) from exc
                raise
            bridge.reset()
            time.sleep(PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS)


def _is_retryable_com_failure(exc: IllustratorBridgeError) -> bool:
    return "-2147417851" in str(exc) or "-2147023170" in str(exc)


__all__ = [
    "render_production_batch_files",
]
