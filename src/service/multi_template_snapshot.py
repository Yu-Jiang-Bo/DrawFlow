"""Serializable template-resolution snapshots and business-safe issues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class TemplateResolutionError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TemplateSnapshot:
    source: str
    template_id: str
    pipeline: str
    version: str
    template_sha256: str
    template_dir: str
    template_ai: str
    template_config: str
    template_rules_config: str
    required_fonts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "template_id": self.template_id,
            "pipeline": self.pipeline,
            "version": self.version,
            "template_sha256": self.template_sha256,
            "template_dir": self.template_dir,
            "template_ai": self.template_ai,
            "template_config": self.template_config,
            "template_rules_config": self.template_rules_config,
            "required_fonts": list(self.required_fonts),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TemplateSnapshot":
        return cls(
            str(payload.get("source") or ""),
            str(payload.get("template_id") or ""),
            str(payload.get("pipeline") or ""),
            str(payload.get("version") or ""),
            str(payload.get("template_sha256") or ""),
            str(payload.get("template_dir") or ""),
            str(payload.get("template_ai") or ""),
            str(payload.get("template_config") or ""),
            str(payload.get("template_rules_config") or ""),
            tuple(str(item) for item in payload.get("required_fonts") or []),
        )


@dataclass(frozen=True)
class TemplateResolutionIssue:
    template_id: str
    code: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return {
            "template_id": self.template_id,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class TemplateResolutionBatch:
    snapshots: tuple[TemplateSnapshot, ...]
    issues: tuple[TemplateResolutionIssue, ...]

    def by_template_id(self) -> dict[str, TemplateSnapshot]:
        return {snapshot.template_id: snapshot for snapshot in self.snapshots}


__all__ = [
    "TemplateResolutionBatch",
    "TemplateResolutionError",
    "TemplateResolutionIssue",
    "TemplateSnapshot",
]
