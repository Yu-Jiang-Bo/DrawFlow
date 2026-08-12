"""Validation helpers for a V2 Illustrator execution payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


class V2TemplateRendererError(ValueError):
    """Raised before Illustrator is invoked for an invalid V2 render runtime."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def normalize_preview_execution_fields(
    render_task: Mapping[str, Any],
    *,
    output_key: str | None,
    preview_png: Path | str | None,
    layout_warning_file: Path | str | None,
) -> tuple[str, str, str]:
    """Normalize and validate the optional single-output preview fields."""

    selected_output_key = str(output_key or "").strip()
    preview_path = str(preview_png or "").strip()
    warning_path = str(layout_warning_file or "").strip()
    if preview_path and not selected_output_key:
        raise V2TemplateRendererError(
            "preview_output_key_missing",
            "A V2 preview must select exactly one render output.",
            path="$.output_key",
        )
    if selected_output_key and selected_output_key not in _output_keys(render_task):
        raise V2TemplateRendererError(
            "output_key_unknown",
            "The selected V2 render output is not present in this task.",
            path="$.output_key",
        )
    return selected_output_key, preview_path, warning_path


def split_pipe_part(value: str, raw_index: Any) -> str:
    """Return one non-empty trimmed pipe segment using the shared V2 rule."""

    parts = [part.strip() for part in str(value or "").split("|") if part.strip()]
    try:
        index = int(raw_index or 0)
    except (TypeError, ValueError):
        index = 0
    if index < 0 or index >= len(parts):
        return ""
    return parts[index]


def _output_keys(render_task: Mapping[str, Any]) -> set[str]:
    return {
        str(output.get("key") or "")
        for output in render_task.get("outputs", [])
        if isinstance(output, Mapping)
    }


__all__ = [
    "V2TemplateRendererError",
    "normalize_preview_execution_fields",
    "split_pipe_part",
]
