"""Shared deterministic rule semantics used by validation and rendering."""

from __future__ import annotations

from typing import Any, Mapping, Tuple


def resolve_mapped_text(
    value: Any,
    mapping: Mapping[str, Any],
    text_policies: Mapping[str, Any],
) -> Tuple[bool, str]:
    delimiter = str(mapping.get("delimiter") or "")
    raw_index = mapping.get("sequence_index")
    sequence_index = raw_index if isinstance(raw_index, int) and not isinstance(raw_index, bool) else 0
    text = "" if value is None else str(value)
    if not delimiter or sequence_index < 1:
        return True, text

    split_policy = text_policies.get("split", {})
    split_policy = split_policy if isinstance(split_policy, Mapping) else {}
    parts = text.split(delimiter)
    if split_policy.get("trim", True):
        parts = [part.strip() for part in parts]
    raw_max_parts = split_policy.get("max_parts")
    max_parts = (
        raw_max_parts
        if isinstance(raw_max_parts, int) and not isinstance(raw_max_parts, bool) and raw_max_parts > 0
        else 0
    )
    overflow = str(split_policy.get("overflow") or "reject")
    if max_parts > 0 and len(parts) > max_parts:
        if overflow == "reject":
            return False, ""
        parts = parts[:max_parts]
    if sequence_index <= len(parts):
        return True, parts[sequence_index - 1]
    if overflow == "empty":
        return True, ""
    return False, ""
