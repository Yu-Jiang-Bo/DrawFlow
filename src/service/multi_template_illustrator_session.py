"""One explicitly owned Illustrator session for a multi-template parent job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from ..renderer.illustrator_bridge import IllustratorBridge
from .production_batch import (
    render_production_batch_files_with_bridge,
    render_production_batch_sequence_with_bridge,
)


BridgeFactory = Callable[..., IllustratorBridge]


class MultiTemplateIllustratorSession:
    """Keep the V2 production COM process alive until its parent task exits.

    A session is lazy: a legacy-only parent never starts Illustrator.  It owns
    only an isolated ``DispatchEx`` instance and therefore may safely close it
    when the parent ends without touching a user-opened Illustrator instance.
    """

    def __init__(self, bridge_factory: BridgeFactory = IllustratorBridge) -> None:
        self._bridge_factory = bridge_factory
        self._bridge: IllustratorBridge | None = None
        self._closed = False

    def __enter__(self) -> "MultiTemplateIllustratorSession":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def render_batch_files(self, batch_files: Iterable[Path], visible: bool) -> None:
        render_production_batch_files_with_bridge(self._ensure_bridge(), batch_files, visible=visible)

    def render_batch_sequence(
        self,
        batch_groups: Sequence[Iterable[Path]],
        visible: bool,
        after_group: Callable[[int], None],
    ) -> None:
        render_production_batch_sequence_with_bridge(
            self._ensure_bridge(),
            batch_groups,
            visible=visible,
            after_group=after_group,
        )

    def recover(self) -> bool:
        """Discard only this task's failed COM proxy before retrying its group."""

        if self._closed:
            return False
        if self._bridge is not None:
            self._bridge.reset()
        return True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None

    def _ensure_bridge(self) -> IllustratorBridge:
        if self._closed:
            raise RuntimeError("multi-template Illustrator session is closed")
        if self._bridge is None:
            self._bridge = self._bridge_factory(
                visible=False,
                fresh_instance=True,
                reuse_instance=True,
                require_fresh_instance=True,
            )
        return self._bridge


__all__ = ["MultiTemplateIllustratorSession"]
