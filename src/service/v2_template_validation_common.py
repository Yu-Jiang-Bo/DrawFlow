"""Shared helpers for V2 template validation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


V2_STATUS_PASSED = "passed"
V2_STATUS_PENDING = "pending"
V2_STATUS_BLOCKED = "blocked"
STATUS_ORDER = {V2_STATUS_PASSED: 0, V2_STATUS_PENDING: 1, V2_STATUS_BLOCKED: 2}


def add_issue(
    issues: list[Dict[str, str]],
    path: str,
    check: str,
    status: str,
    code: str,
    reason: str,
) -> None:
    issues.append(
        {
            "path": path,
            "check": check,
            "status": status,
            "code": code,
            "reason": reason,
        }
    )


def add_duplicate_issues(
    values: Iterable[str],
    path: str,
    check: str,
    code: str,
    issues: list[Dict[str, str]],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        key = str(value or "").strip().casefold()
        if not key:
            continue
        if key in seen:
            duplicates.add(str(value))
        seen.add(key)
    for value in sorted(duplicates):
        add_issue(
            issues,
            path,
            check,
            V2_STATUS_BLOCKED,
            code,
            f"同一作用域内名称重复：{value}。",
        )


def add_duplicate_path_issues(
    records: Iterable[Mapping[str, str]],
    path: str,
    check: str,
    code: str,
    issues: list[Dict[str, str]],
) -> None:
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for record in records:
        name = str(record.get("name") or "").strip()
        if not name:
            continue
        scope = str(record.get("scope") or "当前作用域").strip()
        grouped.setdefault((scope.casefold(), name.casefold()), []).append(record)

    for (_scope_key, _name_key), items in grouped.items():
        if len(items) < 2:
            continue
        name = str(items[0].get("name") or "")
        scope = str(items[0].get("scope") or "当前作用域")
        layer_paths = [
            f"{item.get('layer_path')} ({item.get('json_path')})"
            for item in items
            if item.get("layer_path")
        ]
        add_issue(
            issues,
            path,
            check,
            V2_STATUS_BLOCKED,
            code,
            f"同一作用域 {scope} 内名称重复：{name}；冲突图层路径：{'; '.join(layer_paths)}。",
        )


def outputs(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in list_value(contract.get("outputs")) if isinstance(item, Mapping)]


def mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def option_has_font_evidence(option: Mapping[str, Any]) -> bool:
    if list_value(option.get("font_dependencies")):
        return True
    return any(list_value(slot.get("font_dependencies")) for slot in list_value(option.get("slots")))


def slot_suffix(value: str) -> str:
    return value[5:] if value.startswith("slot_") and len(value) > 5 else ""


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
