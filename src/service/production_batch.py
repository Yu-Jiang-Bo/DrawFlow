"""Shared Illustrator batch execution for production outputs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError, format_com_recovery_message


PRODUCTION_BATCH_COM_RETRY_ATTEMPTS = 3
PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS = 3.0
PRODUCTION_BATCH_CHUNK_DELAY_SECONDS = 1.0
PRODUCTION_BATCH_MAX_CHUNKS_PER_SESSION = 4
PRODUCTION_BATCH_INTERNAL_ERROR_RETRY_ATTEMPTS = 1
ILLUSTRATOR_INTERNAL_AUTOMATION_ERROR = "1095724867 ('AOoC')"


def render_production_batch_files(batch_files: Iterable[Path], visible: bool) -> None:
    """Render production batch task files through one reusable Illustrator session."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        _render_production_batch_chunks(bridge, script, batch_files)
    finally:
        bridge.close()


def render_production_batch_sequence(
    batch_groups: Sequence[Iterable[Path]],
    visible: bool,
    after_group: Callable[[int], None] | None = None,
) -> None:
    """Run ordered batch groups in one reusable Illustrator session."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        chunks_in_session = 0
        for index, batch_files in enumerate(batch_groups):
            chunks_in_session = _render_production_batch_chunks(
                bridge,
                script,
                batch_files,
                chunks_in_session=chunks_in_session,
            )
            if after_group is not None:
                after_group(index)
    finally:
        bridge.close()


def _render_production_batch_chunks(
    bridge: IllustratorBridge,
    script: Path,
    batch_files: Iterable[Path],
    *,
    chunks_in_session: int = 0,
) -> int:
    for batch_file in batch_files:
        if chunks_in_session >= PRODUCTION_BATCH_MAX_CHUNKS_PER_SESSION:
            bridge.reset()
            chunks_in_session = 0
        session_recreated = _render_production_batch_chunk(bridge, script, Path(batch_file))
        if session_recreated:
            chunks_in_session = 0
        chunks_in_session += 1
        time.sleep(PRODUCTION_BATCH_CHUNK_DELAY_SECONDS)
    return chunks_in_session


def _render_production_batch_chunk(bridge: IllustratorBridge, script: Path, task_file: Path) -> bool:
    com_retries = 0
    internal_error_retries = 0
    session_recreated = False
    while True:
        try:
            bridge.render(script, task_file)
            return session_recreated
        except IllustratorBridgeError as exc:
            if _is_retryable_com_failure(exc):
                if com_retries + 1 >= PRODUCTION_BATCH_COM_RETRY_ATTEMPTS:
                    raise IllustratorBridgeError(format_com_recovery_message(exc, retries=com_retries)) from exc
                com_retries += 1
            elif _is_retryable_illustrator_internal_failure(exc):
                if internal_error_retries >= PRODUCTION_BATCH_INTERNAL_ERROR_RETRY_ATTEMPTS:
                    raise
                internal_error_retries += 1
            else:
                raise
            bridge.reset()
            session_recreated = True
            time.sleep(PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS)


def _is_retryable_com_failure(exc: IllustratorBridgeError) -> bool:
    return "-2147417851" in str(exc) or "-2147023170" in str(exc)


def _is_retryable_illustrator_internal_failure(exc: IllustratorBridgeError) -> bool:
    return ILLUSTRATOR_INTERNAL_AUTOMATION_ERROR in str(exc)


__all__ = [
    "render_production_batch_files",
    "render_production_batch_sequence",
]
