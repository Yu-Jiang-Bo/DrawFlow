"""Derive per-source-row canary metrics from immutable dry-run task plans."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .multi_template_order import TemplateOrderGroup


class PlanMetricsError(ValueError):
    """A dry-run plan cannot be safely attributed to original order rows."""


def planned_row_metrics(
    group: TemplateOrderGroup,
    record: Mapping[str, Any],
) -> dict[str, dict[str, int]]:
    """Map an existing dry-run plan back to original Excel rows.

    V2 returns its expanded-unit summary through its private fixed-snapshot
    entry point. Legacy pipelines expose the same information in their
    generated task JSON; this function only reads those task plans and never
    opens the user workbook or runs Illustrator.
    """

    v2_metrics = _mapping(record.get("_preflight_row_metrics"))
    if v2_metrics:
        return _remap_local_metrics(group, v2_metrics)
    return _legacy_task_metrics(group, _task_documents(_mapping(record.get("outputs"))))


def _remap_local_metrics(
    group: TemplateOrderGroup,
    local_metrics: Mapping[str, Any],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for local_row, row in enumerate(group.rows, start=1):
        metric = _mapping(local_metrics.get(str(local_row)) or local_metrics.get(local_row))
        result[str(row.excel_row)] = _validated_metric(metric)
    return result


def _legacy_task_metrics(
    group: TemplateOrderGroup,
    documents: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    buckets: dict[int, dict[str, Any]] = {
        row.excel_row: {"planned_output_units": 0, "text_values": set()}
        for row in group.rows
    }
    seen: set[tuple[Any, ...]] = set()
    found = False
    for document in documents:
        for item in _native_task_items(document):
            row = _task_row(group, item)
            if row is None:
                raise PlanMetricsError("task row cannot be mapped")
            identity = _task_item_identity(row, item)
            if identity in seen:
                continue
            seen.add(identity)
            found = True
            bucket = buckets[row.excel_row]
            bucket["planned_output_units"] += 1
            bucket["text_values"].update(_task_text_values(item))
    if not found:
        raise PlanMetricsError("no native task items")
    return {
        str(row.excel_row): _validated_metric({
            "planned_output_units": buckets[row.excel_row]["planned_output_units"],
            "variable_text_length": sum(len(value) for _slot, value in buckets[row.excel_row]["text_values"]),
        })
        for row in group.rows
    }


def _task_documents(outputs: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    pending = _task_paths(outputs)
    visited: set[Path] = set()
    documents: list[Mapping[str, Any]] = []
    while pending:
        path = pending.pop(0)
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise PlanMetricsError("invalid task path") from exc
        if resolved in visited:
            continue
        visited.add(resolved)
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise PlanMetricsError("unreadable task plan") from exc
        if not isinstance(payload, Mapping):
            raise PlanMetricsError("invalid task plan")
        documents.append(payload)
        if str(payload.get("type") or "") == "render_batch":
            for entry in payload.get("tasks", []):
                if isinstance(entry, Mapping) and str(entry.get("task_file") or "").strip():
                    pending.append(Path(str(entry["task_file"])))
    if not documents:
        raise PlanMetricsError("task plan missing")
    return tuple(documents)


def _task_paths(outputs: Mapping[str, Any]) -> list[Path]:
    values: list[Any] = [outputs.get("render_task")]
    task_files = outputs.get("render_task_files")
    if isinstance(task_files, list):
        values.extend(task_files)
    paths = [Path(str(value)) for value in values if str(value or "").strip()]
    if not paths:
        raise PlanMetricsError("task path missing")
    return paths


def _native_task_items(task: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    task_type = str(task.get("type") or "")
    if task_type == "generic_template_rules":
        for order in task.get("orders", []):
            if not isinstance(order, Mapping):
                continue
            members = order.get("layout_members")
            if isinstance(members, list):
                # A name-columns layout can deliberately combine several
                # source rows into one existing single-template effect card.
                # Allocate that shared planned card to every participating
                # original row, so canary risk remains auditable per row
                # without rejecting an otherwise valid legacy layout.
                if not members or any(not isinstance(member, Mapping) for member in members):
                    raise PlanMetricsError("invalid layout members")
                yield from members
            else:
                yield order
        return
    groups = task.get("groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            for item in group.get("items", []):
                if isinstance(item, Mapping):
                    yield item
        return
    items = task.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                yield item
        return
    if task.get("order_no") is not None and (task.get("text") is not None or task.get("variables") is not None):
        yield task


def _task_row(group: TemplateOrderGroup, item: Mapping[str, Any]):
    raw_index = item.get("row_index")
    if raw_index is not None:
        index = _positive_int(raw_index)
        if index is None:
            raise PlanMetricsError("invalid task row index") from None
        if 1 <= index <= len(group.rows):
            return group.rows[index - 1]
        raise PlanMetricsError("task row index outside group")
    order_no = str(item.get("order_no") or "").strip()
    candidates = [row for row in group.rows if row.order_no == order_no]
    detail_id = str(item.get("detail_id") or "").strip()
    if detail_id and any(_row_detail_ids(row) for row in candidates):
        candidates = [row for row in candidates if detail_id in _row_detail_ids(row)]
    return candidates[0] if len(candidates) == 1 else None


def _row_detail_ids(row: Any) -> set[str]:
    aliases = {"订单明细id", "订单明细ID", "明细id", "detail_id", "detail id", "item id", "明细号", "订单明细号", "子订单号"}
    return {
        str(value).strip()
        for header, value in row.values.items()
        if str(header).strip() in aliases and str(value or "").strip()
    }


def _task_item_identity(row: Any, item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.excel_row,
        str(item.get("order_no") or ""),
        str(item.get("detail_id") or ""),
        str(item.get("quantity_index") or "1"),
        str(item.get("copy_index") or "1"),
        str(item.get("text") or ""),
        _task_slot_identity(item),
    )


def _task_text_values(item: Mapping[str, Any]) -> set[tuple[str, str]]:
    if item.get("text") is not None:
        text = str(item.get("text") or "").strip()
        return {(_task_slot_identity(item), text)} if text else set()
    return {
        (
            str(variable.get("target") or variable.get("slot") or variable.get("field") or index),
            str(variable.get("value") or "").strip(),
        )
        for index, variable in enumerate(item.get("variables", []), start=1)
        if isinstance(variable, Mapping) and str(variable.get("value") or "").strip()
    }


def _task_slot_identity(item: Mapping[str, Any]) -> str:
    return str(
        item.get("text_type")
        or item.get("slot_key")
        or item.get("target")
        or item.get("render_kind")
        or item.get("type")
        or "text"
    )


def _validated_metric(metric: Mapping[str, Any]) -> dict[str, int]:
    planned_units = _positive_int(metric.get("planned_output_units"))
    text_length = _nonnegative_int(metric.get("variable_text_length"))
    if planned_units is None or text_length is None:
        raise PlanMetricsError("invalid row metric")
    return {"planned_output_units": planned_units, "variable_text_length": text_length}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        return None
    return int(number)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["PlanMetricsError", "planned_row_metrics"]
