"""Pure aggregate helpers for the public multi-template job contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def non_negative_float(value: Any) -> float:
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return 0.0


def canary_elapsed_totals(metadata: Mapping[str, Any]) -> dict[str, float]:
    runs = [metadata.get("canary"), *(metadata.get("canary_history") or [])]
    totals: dict[str, float] = {}
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        for group in run.get("groups") or []:
            if not isinstance(group, Mapping):
                continue
            template_id = str(group.get("template_id") or "")
            if template_id:
                totals[template_id] = totals.get(template_id, 0.0) + _interval_seconds(
                    group.get("started_at"), group.get("finished_at"),
                )
    return {template_id: round(seconds, 3) for template_id, seconds in totals.items()}


def failure_scope(value: Any) -> str:
    text = str(value or "")
    return text if text in {"template", "system"} else ""


def template_ids(summaries: list[Mapping[str, Any]], statuses: set[str]) -> list[str]:
    return [str(item["template_id"]) for item in summaries if group_state(item) in statuses]


def failure_template_ids(summaries: list[Mapping[str, Any]]) -> list[str]:
    return [
        str(item["template_id"])
        for item in summaries
        if str(item.get("status") or "") in {"failed", "canary_failed"}
    ]


def group_state(summary: Mapping[str, Any]) -> str:
    status = str(summary.get("status") or "")
    if status == "canary_running":
        return "running"
    if status in {"failed", "canary_failed"} and failure_scope(summary.get("failure_scope")) == "system":
        return "interrupted"
    return status


def group_counts(summaries: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "succeeded": len(template_ids(summaries, {"succeeded"})),
        "failed": len(template_ids(summaries, {"failed", "canary_failed"})),
        "unstarted": len(template_ids(summaries, {"pending", "ready"})),
        "interrupted": len(template_ids(summaries, {"interrupted"})),
        "running": len(template_ids(summaries, {"running"})),
    }


def failed_templates(summaries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "template_id": str(item["template_id"]),
        "failure_scope": failure_scope(item.get("failure_scope")),
        "error_code": str(item.get("error_code") or ""),
        "child_job_id": str(item.get("child_job_id") or item.get("canary_child_job_id") or ""),
        "excel_rows": list(item.get("excel_rows") or []),
    } for item in summaries if str(item.get("status") or "") in {"failed", "canary_failed"}]


def _interval_seconds(start: Any, finish: Any) -> float:
    try:
        begin = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(finish).replace("Z", "+00:00"))
        return max((end - begin).total_seconds(), 0.0)
    except (TypeError, ValueError):
        return 0.0


__all__ = ["canary_elapsed_totals", "failed_templates", "failure_scope", "failure_template_ids", "group_counts", "group_state", "non_negative_float", "template_ids"]
