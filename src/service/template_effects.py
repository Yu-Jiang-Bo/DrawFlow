"""Normalize, validate, and compile declarative template text effects."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any, Dict, Mapping, Sequence


SELECTOR_TYPES = {"whole", "split"}
ACTION_TYPES = {
    "set_fill_color",
    "set_font_size",
    "set_tracking",
    "set_horizontal_scale",
    "set_vertical_scale",
    "set_baseline_shift",
}
NUMERIC_ACTION_TYPES = ACTION_TYPES - {"set_fill_color"}
POSITION_MODES = {"all", "odd", "even"}
SELECTION_FIELDS = {"font", "design", "style", "color"}
NAMED_COLORS = {
    "black", "white", "red", "blue", "gold",
    "黑色", "白色", "红色", "蓝色", "金色",
}
HEX_COLOR_RE = re.compile(r"^#?[0-9a-f]{6}$", re.IGNORECASE)


class TemplateEffectError(ValueError):
    pass


def normalize_template_effects(rules: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """Return the canonical effects list, migrating the retired color schema."""

    raw_effects = rules.get("effects")
    if isinstance(raw_effects, list):
        return [deepcopy(dict(item)) for item in raw_effects if isinstance(item, Mapping)]
    legacy_styles = rules.get("text_sequence_styles")
    if not isinstance(legacy_styles, list):
        return []
    effects: list[Dict[str, Any]] = []
    for index, style in enumerate(legacy_styles, start=1):
        if not isinstance(style, Mapping):
            continue
        values = [
            str(style.get("odd_color") or "").strip(),
            str(style.get("even_color") or "").strip(),
        ]
        effects.append(
            {
                "id": f"legacy-alternating-color-{index}",
                "stage": "text",
                "target": {
                    "field": str(style.get("field") or "text").strip(),
                    "name": str(style.get("target") or "").strip(),
                },
                "selector": {
                    "type": "split",
                    "delimiter": str(style.get("delimiter") or ""),
                    "positions": "all",
                    "trim": False,
                },
                "actions": [
                    {
                        "type": "set_fill_color",
                        "value": {"type": "cycle", "values": values},
                    }
                ],
            }
        )
    return effects


def compile_text_effects(
    text: str,
    field: str,
    target: str,
    rules: Mapping[str, Any],
    selections: Mapping[str, str] | None = None,
) -> list[Dict[str, Any]]:
    """Compile matching declarative effects into renderer-ready range actions."""

    compiled: list[Dict[str, Any]] = []
    for effect in normalize_template_effects(rules):
        effect_target = effect.get("target")
        if not isinstance(effect_target, Mapping):
            continue
        if str(effect_target.get("field") or "text") != field:
            continue
        if str(effect_target.get("name") or "") != target:
            continue
        if not _condition_matches(effect.get("when"), selections or {}):
            continue
        segments = _select_segments(text, effect.get("selector"))
        for action in effect.get("actions", []):
            if not isinstance(action, Mapping):
                continue
            action_type = str(action.get("type") or "")
            if action_type not in ACTION_TYPES:
                raise TemplateEffectError(f"Unsupported text effect action: {action_type or 'empty'}")
            ranges = []
            for segment_index, start, length in segments:
                value = _resolve_action_value(action.get("value"), segment_index)
                if value in (None, ""):
                    continue
                ranges.append({"start": start, "length": length, "value": value})
            if ranges:
                compiled.append({"type": action_type, "ranges": ranges})
    return compiled


def validate_template_effects(
    value: Any,
    bindings: Any,
    slot_mappings: Sequence[Mapping[str, Any]],
    text_targets: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Validate the safe declarative DSL before a template can be enabled."""

    if value in (None, []):
        return []
    if not isinstance(value, list):
        return ["Template effects must be a list."]
    errors: list[str] = []
    bound_fields = set(bindings) if isinstance(bindings, Mapping) else set()
    for index, effect in enumerate(value, start=1):
        prefix = f"Template effect {index}"
        if not isinstance(effect, Mapping):
            errors.append(f"{prefix} must be an object.")
            continue
        if str(effect.get("stage") or "text") != "text":
            errors.append(f"{prefix} uses an unsupported stage.")
        target = effect.get("target")
        if not isinstance(target, Mapping):
            errors.append(f"{prefix} requires a target object.")
            continue
        field = str(target.get("field") or "text").strip()
        name = str(target.get("name") or "").strip()
        if field not in bound_fields:
            errors.append(f"{prefix} requires a bound field: {field}")
        if not name:
            errors.append(f"{prefix} requires a template text target.")
        elif not _has_executable_target(field, name, bound_fields, slot_mappings, text_targets):
            errors.append(f"{prefix} must match an executable text mapping: {field} -> {name}")
        errors.extend(_validate_selector(effect.get("selector"), prefix))
        errors.extend(_validate_actions(effect.get("actions"), prefix))
        errors.extend(_validate_condition(effect.get("when"), prefix))
    return errors


def _select_segments(text: str, raw_selector: Any) -> list[tuple[int, int, int]]:
    selector = raw_selector if isinstance(raw_selector, Mapping) else {}
    selector_type = str(selector.get("type") or "whole")
    if selector_type == "whole":
        return [(0, 0, len(text))]
    if selector_type != "split":
        raise TemplateEffectError(f"Unsupported text effect selector: {selector_type}")
    delimiter = str(selector.get("delimiter") or "")
    if not delimiter:
        return []
    positions = str(selector.get("positions") or "all")
    trim = selector.get("trim") is True
    segments: list[tuple[int, int, int]] = []
    cursor = 0
    for index, raw_part in enumerate(text.split(delimiter), start=1):
        left_trim = len(raw_part) - len(raw_part.lstrip()) if trim else 0
        part = raw_part.strip() if trim else raw_part
        if _position_matches(index, positions):
            segments.append((index - 1, cursor + left_trim, len(part)))
        cursor += len(raw_part) + len(delimiter)
    return segments


def _position_matches(index: int, positions: str) -> bool:
    if positions == "odd":
        return index % 2 == 1
    if positions == "even":
        return index % 2 == 0
    return True


def _resolve_action_value(raw_value: Any, segment_index: int) -> Any:
    if not isinstance(raw_value, Mapping):
        raise TemplateEffectError("Text effect action value must be a literal or cycle object")
    value_type = str(raw_value.get("type") or "literal")
    if value_type == "cycle":
        values = raw_value.get("values")
        if not isinstance(values, list) or not values:
            return None
        return values[segment_index % len(values)]
    if value_type != "literal":
        raise TemplateEffectError(f"Unsupported text effect value type: {value_type}")
    return raw_value.get("value")


def _condition_matches(raw_condition: Any, selections: Mapping[str, str]) -> bool:
    if not isinstance(raw_condition, Mapping):
        return True
    expected = raw_condition.get("selections")
    if not isinstance(expected, Mapping):
        return True
    for key, allowed in expected.items():
        values = allowed if isinstance(allowed, list) else [allowed]
        if selections.get(str(key), "") not in {str(item) for item in values}:
            return False
    return True


def _has_executable_target(
    field: str,
    name: str,
    bound_fields: set[str],
    slot_mappings: Sequence[Mapping[str, Any]],
    text_targets: Sequence[Mapping[str, Any]],
) -> bool:
    if any(
        str(item.get("field") or item.get("source") or "").strip() == field
        and str(item.get("slot") or item.get("name") or "").strip() == name
        for item in slot_mappings
    ):
        return True
    return (
        field == "text"
        and len(bound_fields) == 1
        and len(text_targets) == 1
        and str(text_targets[0].get("name") or "").strip() == name
    )


def _validate_selector(raw_selector: Any, prefix: str) -> list[str]:
    if not isinstance(raw_selector, Mapping):
        return [f"{prefix} requires a selector object."]
    errors: list[str] = []
    selector_type = str(raw_selector.get("type") or "whole")
    if selector_type not in SELECTOR_TYPES:
        errors.append(f"{prefix} uses an unsupported selector: {selector_type}")
    if selector_type == "split" and not str(raw_selector.get("delimiter") or ""):
        errors.append(f"{prefix} split selector requires a delimiter.")
    positions = str(raw_selector.get("positions") or "all")
    if positions not in POSITION_MODES:
        errors.append(f"{prefix} uses unsupported positions: {positions}")
    if "indices" in raw_selector:
        errors.append(f"{prefix} contains unsupported selector keys: indices")
    return errors


def _validate_actions(raw_actions: Any, prefix: str) -> list[str]:
    if not isinstance(raw_actions, list) or not raw_actions:
        return [f"{prefix} requires at least one action."]
    errors: list[str] = []
    for action_index, action in enumerate(raw_actions, start=1):
        action_prefix = f"{prefix} action {action_index}"
        if not isinstance(action, Mapping):
            errors.append(f"{action_prefix} must be an object.")
            continue
        action_type = str(action.get("type") or "")
        if action_type not in ACTION_TYPES:
            errors.append(f"{action_prefix} is unsupported: {action_type or 'empty'}")
            continue
        raw_value = action.get("value")
        if not isinstance(raw_value, Mapping):
            errors.append(f"{action_prefix} value must be a literal or cycle object.")
            continue
        value_type = str(raw_value.get("type") or "literal")
        if value_type not in {"literal", "cycle"}:
            errors.append(f"{action_prefix} uses an unsupported value type: {value_type}")
            continue
        values = _action_values(raw_value)
        if not values or any(item in (None, "") for item in values):
            errors.append(f"{action_prefix} requires a value.")
        elif action_type in NUMERIC_ACTION_TYPES and any(not _is_number(item) for item in values):
            errors.append(f"{action_prefix} requires numeric values.")
        elif action_type == "set_fill_color" and any(not _is_color(item) for item in values):
            errors.append(f"{action_prefix} requires a named color or 6-digit hex color.")
    return errors


def _action_values(raw_value: Any) -> list[Any]:
    if not isinstance(raw_value, Mapping):
        return [raw_value]
    value_type = str(raw_value.get("type") or "literal")
    if value_type == "cycle":
        values = raw_value.get("values")
        return values if isinstance(values, list) else []
    if value_type != "literal":
        return []
    return [raw_value.get("value")]


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_color(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in NAMED_COLORS or HEX_COLOR_RE.fullmatch(text) is not None


def _validate_condition(raw_condition: Any, prefix: str) -> list[str]:
    if raw_condition in (None, {}):
        return []
    if not isinstance(raw_condition, Mapping):
        return [f"{prefix} condition must be an object."]
    if set(raw_condition) - {"selections"}:
        return [f"{prefix} condition contains unsupported keys."]
    selections = raw_condition.get("selections")
    if selections is not None and not isinstance(selections, Mapping):
        return [f"{prefix} selections condition must be an object."]
    if not selections:
        return [f"{prefix} selections condition cannot be empty."]
    errors: list[str] = []
    for key, allowed in selections.items():
        if str(key) not in SELECTION_FIELDS:
            errors.append(f"{prefix} uses an unsupported selection field: {key}")
            continue
        values = allowed if isinstance(allowed, list) else [allowed]
        if not values or any(not str(item or "").strip() for item in values):
            errors.append(f"{prefix} selection condition requires at least one option value: {key}")
    return errors
