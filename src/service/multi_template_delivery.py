"""Apply collector results to a parent record without performing any rendering."""

from __future__ import annotations

from typing import Any, Mapping

from .multi_template_output import MultiTemplateOutputError, MultiTemplateOutputResult


def apply_delivery_result(record: dict[str, Any], result: MultiTemplateOutputResult) -> None:
    if result.kind != "primary_output":
        raise ValueError("multi-template delivery only accepts a complete primary output")
    metadata = dict(record.get("multi_template") or {})
    previous = dict(metadata.get("output") or {})
    current = result.to_dict()
    if previous and previous != current:
        history = [dict(item) for item in metadata.get("output_history") or [] if isinstance(item, Mapping)]
        history.append(previous)
        metadata["output_history"] = history
    metadata["output"] = current
    metadata.pop("output_error", None)
    record["multi_template"] = metadata
    outputs = dict(record.get("outputs") or {})
    outputs["primary_output"] = str(result.path)
    outputs.pop("partial_output", None)
    outputs["output_file_count"] = result.file_count
    record["outputs"] = outputs


def clear_incomplete_delivery(record: dict[str, Any]) -> None:
    metadata = dict(record.get("multi_template") or {})
    metadata.pop("output", None)
    metadata.pop("output_history", None)
    metadata.pop("output_error", None)
    record["multi_template"] = metadata
    outputs = dict(record.get("outputs") or {})
    outputs.pop("primary_output", None)
    outputs.pop("partial_output", None)
    outputs.pop("output_file_count", None)
    record["outputs"] = outputs


def apply_delivery_error(record: dict[str, Any], error: MultiTemplateOutputError) -> dict[str, Any]:
    metadata = dict(record.get("multi_template") or {})
    metadata["output_error"] = {"code": error.code, "message": str(error)}
    record["multi_template"] = metadata
    outputs = dict(record.get("outputs") or {})
    outputs.pop("primary_output", None)
    outputs.pop("partial_output", None)
    record["outputs"] = outputs
    return {
        "status": "interrupted",
        "error": "多模板成品打包失败，未生成可下载文件，请稍后继续此批次。",
        "error_code": error.code,
        "progress": {
            "current": finished_count(metadata),
            "total": len(metadata.get("template_checkpoints") or []),
            "stage": "interrupted",
        },
    }


def finished_count(metadata: Mapping[str, Any]) -> int:
    return sum(
        item.get("status") in {"succeeded", "failed", "canary_failed"}
        for item in metadata.get("template_checkpoints") or []
        if isinstance(item, Mapping)
    )


__all__ = ["apply_delivery_error", "apply_delivery_result", "clear_incomplete_delivery"]
