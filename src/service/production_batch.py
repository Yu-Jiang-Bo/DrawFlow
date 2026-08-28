"""Shared Illustrator batch execution for production outputs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..renderer.illustrator_bridge import (
    IllustratorBridge,
    IllustratorBridgeError,
    RETRYABLE_COM_HRESULTS,
    format_com_recovery_message,
)


PRODUCTION_BATCH_COM_RETRY_ATTEMPTS = 3
PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS = 3.0
PRODUCTION_BATCH_CHUNK_DELAY_SECONDS = 1.0


def render_production_batch_files(batch_files: Iterable[Path], visible: bool) -> None:
    """Render production batch task files through one reusable Illustrator session."""

    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        render_production_batch_files_with_bridge(bridge, batch_files, visible=visible)
    finally:
        bridge.close()


def render_production_batch_sequence(
    batch_groups: Sequence[Iterable[Path]],
    visible: bool,
    after_group: Callable[[int], None] | None = None,
) -> None:
    """Run ordered batch groups in one reusable Illustrator session."""

    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        render_production_batch_sequence_with_bridge(
            bridge,
            batch_groups,
            visible=visible,
            after_group=after_group,
        )
    finally:
        bridge.close()


def render_production_batch_files_with_bridge(
    bridge: IllustratorBridge,
    batch_files: Iterable[Path],
    *,
    visible: bool,
) -> None:
    """Render one job's task files through a bridge owned by the caller.

    The ordinary single-template entrypoint owns and closes its bridge.  A
    multi-template parent instead passes one bridge for all child jobs, so this
    helper deliberately never closes the caller's lifecycle.  A retryable
    chunk may still reset only that caller-owned bridge before its local retry.
    """

    bridge.visible = visible
    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    for batch_file in batch_files:
        _render_production_batch_chunk(bridge, script, Path(batch_file))
        time.sleep(PRODUCTION_BATCH_CHUNK_DELAY_SECONDS)


def render_production_batch_sequence_with_bridge(
    bridge: IllustratorBridge,
    batch_groups: Sequence[Iterable[Path]],
    *,
    visible: bool,
    after_group: Callable[[int], None] | None = None,
) -> None:
    """Run ordered task-file groups without changing the owner's COM lifetime."""

    for index, batch_files in enumerate(batch_groups):
        render_production_batch_files_with_bridge(bridge, batch_files, visible=visible)
        if after_group is not None:
            after_group(index)


def _render_production_batch_chunk(bridge: IllustratorBridge, script: Path, task_file: Path) -> None:
    for attempt in range(PRODUCTION_BATCH_COM_RETRY_ATTEMPTS):
        try:
            bridge.render(script, task_file)
            return
        except IllustratorBridgeError as exc:
            if attempt + 1 >= PRODUCTION_BATCH_COM_RETRY_ATTEMPTS or not _is_retryable_com_failure(exc):
                if _is_retryable_com_failure(exc):
                    raise IllustratorBridgeError(
                        format_com_recovery_message(exc, retries=attempt),
                        failure_scope="system",
                    ) from exc
                raise
            bridge.reset()
            time.sleep(PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS)


def _is_retryable_com_failure(exc: IllustratorBridgeError) -> bool:
    return any(code in str(exc) for code in RETRYABLE_COM_HRESULTS)


__all__ = [
    "render_production_batch_files",
    "render_production_batch_sequence",
    "render_production_batch_files_with_bridge",
    "render_production_batch_sequence_with_bridge",
]
