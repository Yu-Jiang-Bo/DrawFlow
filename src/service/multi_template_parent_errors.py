"""Shared business errors for multi-template parent task orchestration."""

from __future__ import annotations


class MultiTemplateRenderError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


__all__ = ["MultiTemplateRenderError"]
