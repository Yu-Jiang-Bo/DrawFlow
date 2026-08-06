"""Issue helpers for V2 order preflight."""

from __future__ import annotations

from typing import Any, Dict, Mapping


def preflight_issue(
    *,
    contract: Mapping[str, Any],
    row: int,
    order_id: str,
    path: str,
    code: str,
    reason: str,
    output: Mapping[str, Any] | None = None,
    option: Mapping[str, Any] | None = None,
    raw_value: str = "",
    expected_format: str = "",
) -> Dict[str, Any]:
    template = dict(contract.get("template") or {})
    output_data = dict(output or {})
    option_data = dict(option or {})
    return {
        "row": row,
        "order_id": order_id,
        "template_id": str(template.get("template_id") or ""),
        "template_name": str(template.get("name") or ""),
        "output": str(output_data.get("key") or ""),
        "output_name": str(output_data.get("display_name") or ""),
        "option": str(option_data.get("key") or ""),
        "raw_value": raw_value,
        "expected_format": expected_format,
        "path": path,
        "code": code,
        "reason": reason,
    }


__all__ = ["preflight_issue"]
