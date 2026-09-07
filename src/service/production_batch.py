"""Shared Illustrator batch execution for production outputs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError, format_com_recovery_message


PRODUCTION_BATCH_COM_RETRY_ATTEMPTS = 3
PRODUCTION_BATCH_INTERNAL_ERROR_RETRY_ATTEMPTS = 1
PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS = 5.0
# DispatchEx returns before Illustrator has finished shutting down the previous
# private process.  A short delay is not sufficient after large outlined AI8
# batches; starting the next process too early can reject DoJavaScript calls.
PRODUCTION_BATCH_CHUNK_DELAY_SECONDS = 5.0
ILLUSTRATOR_INTERNAL_AUTOMATION_ERROR = "1095724867 ('AOoC')"


def render_production_batch_files(batch_files: Iterable[Path], visible: bool) -> None:
    """Render production batches through an isolated Illustrator instance per chunk."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    batch_paths = [Path(batch_file) for batch_file in batch_files]
    for index, batch_file in enumerate(batch_paths):
        bridge = _new_isolated_bridge(visible)
        try:
            _render_production_batch_chunk(bridge, script, batch_file)
        finally:
            bridge.close()
        if index + 1 < len(batch_paths):
            time.sleep(PRODUCTION_BATCH_CHUNK_DELAY_SECONDS)


def render_production_batch_sequence(
    batch_groups: Sequence[Iterable[Path]],
    visible: bool,
    after_group: Callable[[int], None] | None = None,
) -> None:
    """Run ordered batch groups with one private Illustrator session per chunk."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_batch.jsx"
    groups = [[Path(batch_file) for batch_file in batch_files] for batch_files in batch_groups]
    remaining_batches = sum(len(batch_files) for batch_files in groups)
    for index, batch_files in enumerate(groups):
        for batch_file in batch_files:
            bridge = _new_isolated_bridge(visible)
            try:
                _render_production_batch_chunk(bridge, script, batch_file)
            finally:
                bridge.close()
            remaining_batches -= 1
            if remaining_batches > 0:
                time.sleep(PRODUCTION_BATCH_CHUNK_DELAY_SECONDS)
        if after_group is not None:
            after_group(index)


def _new_isolated_bridge(visible: bool) -> IllustratorBridge:
    """Create one automation-only Illustrator session for a single batch."""

    return IllustratorBridge(visible=visible, fresh_instance=True, quit_after=True)


def _render_production_batch_chunk(bridge: IllustratorBridge, script: Path, task_file: Path) -> None:
    com_retries = 0
    internal_error_retries = 0
    while True:
        try:
            bridge.render(script, task_file)
            return
        except IllustratorBridgeError as exc:
            if _is_retryable_illustrator_internal_failure(exc):
                if internal_error_retries >= PRODUCTION_BATCH_INTERNAL_ERROR_RETRY_ATTEMPTS:
                    raise
                internal_error_retries += 1
            elif _is_retryable_batch_failure(exc):
                if com_retries + 1 >= PRODUCTION_BATCH_COM_RETRY_ATTEMPTS:
                    raise IllustratorBridgeError(_format_batch_recovery_message(exc, retries=com_retries)) from exc
                com_retries += 1
            else:
                raise
            bridge.reset()
            time.sleep(PRODUCTION_BATCH_COM_RETRY_DELAY_SECONDS)


def _is_retryable_batch_failure(exc: IllustratorBridgeError) -> bool:
    detail = str(exc)
    return (
        "-2147417851" in detail
        or "-2147023170" in detail
        or "an Illustrator error occurred: 248" in detail
    )


def _is_retryable_illustrator_internal_failure(exc: IllustratorBridgeError) -> bool:
    return ILLUSTRATOR_INTERNAL_AUTOMATION_ERROR in str(exc)


def _format_batch_recovery_message(exc: IllustratorBridgeError, *, retries: int) -> str:
    if "an Illustrator error occurred: 248" in str(exc):
        return (
            "Illustrator 在隔离渲染会话中重新打开模板时失败（错误 248）。"
            f"已自动新建实例重试 {retries} 次仍未恢复。"
            "请稍后重试；该失败不会影响已经生成的源订单文件。"
        )
    return format_com_recovery_message(exc, retries=retries)


__all__ = [
    "render_production_batch_files",
    "render_production_batch_sequence",
]
