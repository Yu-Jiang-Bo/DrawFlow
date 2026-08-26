"""Fresh-session recovery gate used after an exhausted Illustrator COM retry."""

from __future__ import annotations

from typing import Callable

from ..renderer.illustrator_bridge import IllustratorBridge


class FreshIllustratorSessionRecovery:
    """Verify that a new Illustrator automation session can be created safely."""

    def __init__(self, checker: Callable[[], bool] | None = None) -> None:
        self._checker = checker or _check_fresh_illustrator_session

    def check(self) -> bool:
        try:
            return bool(self._checker())
        except Exception:
            return False


def _check_fresh_illustrator_session() -> bool:
    return IllustratorBridge(
        visible=False,
        fresh_instance=True,
        quit_after=True,
    ).check_fresh_session()


__all__ = ["FreshIllustratorSessionRecovery"]
