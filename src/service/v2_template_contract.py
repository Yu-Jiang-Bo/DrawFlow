"""V2 template whitelist contract normalization.

This module intentionally does not migrate legacy template rules. V2 drafts
must come from controlled scan data and form fields only.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, Mapping


V2_CONTRACT_SCHEMA = "custom-renderer/v2-template-contract"
V2_CONTRACT_VERSION = 1

V2_SCOPE_VALUES = {"local", "shared"}
V2_PROCESSING_PRESETS = {
    "direct_text",
    "split_by_pipe",
    "initial_with_text",
    "multi_initials",
    "path_text",
    "tail_text",
    "design_font_combo",
    "asset_replace",
}
V2_OPTION_CONTENT_PRESETS = V2_PROCESSING_PRESETS | {"mixed_slots"}
V2_SELECTABLE_OPTION_CONTENT_PRESETS = V2_OPTION_CONTENT_PRESETS - {"asset_replace"}
V2_VERIFICATION_KEYS = (
    "output",
    "fields",
    "options",
    "slots",
    "content",
    "dimensions",
    "colors",
    "preview",
)
V2_CHECK_STATUSES = {"pending", "confirmed", "blocked"}

_TOP_LEVEL_FIELDS = {
    "$schema",
    "schema_version",
    "template",
    "outputs",
    "colors",
    "field_bindings",
    "option_mappings",
    "multi_name_customization",
    "render_layout",
    "output",
    "checks",
    "preview",
    "audit",
}
_TEMPLATE_FIELDS = {"template_id", "name", "shop_name", "component_key", "scope", "component_scope_executable"}
_OUTPUT_FIELDS = {"key", "display_name", "component_key", "scope", "style", "design", "font", "order", "component_scope_executable"}
_GROUP_FIELDS = {"field", "options"}
_STYLE_OPTION_FIELDS = {"key", "label", "dimensions", "component_key", "scope", "component_scope_executable"}
_DESIGN_FONT_OPTION_FIELDS = {
    "key",
    "label",
    "slots",
    "assets",
    "font_dependencies",
    "content_preset",
    "component_key",
    "scope",
    "component_scope_executable",
}
_SLOT_FIELDS = {
    "key",
    "source_field",
    "required",
    "preset",
    "anchor",
    "tails",
    "asset_key",
    "dimension_rule",
    "font_dependencies",
    "color_binding",
    "preserve_composition",
}
_ASSET_FIELDS = {"asset_key", "slot", "supported_values", "component_key", "scope", "component_scope_executable"}
_TAIL_FIELDS = {"key", "position", "sample", "pua_base", "glyph_map"}
_DIMENSION_FIELDS = {"mode", "width_mm", "height_mm", "tolerance_mm"}
_COLOR_FIELDS = {"key", "zh_name", "space", "value", "allow_recolor"}
_OPTION_MAPPING_FIELDS = {"field", "source_value", "target", "output", "group"}
_CHECK_FIELDS = {"status", "reason"}
_PREVIEW_FIELDS = {"sample_rows", "evidence"}
_PREVIEW_EVIDENCE_FIELDS = {
    "draft_revision",
    "template_sha256",
    "scan_sha256",
    "config_sha256",
    "sample_sha256",
    "render_task_sha256",
    "preview_sha256",
    "renderer_version",
    "font_check",
    "warnings",
    "rendered_at",
    "outputs",
    "approved_by",
    "approved_at",
}
_PREVIEW_OUTPUT_FIELDS = {"key", "ai_sha256", "png_sha256"}
_AUDIT_FIELDS = {"scan_version", "template_sha256", "config_version"}
_EXECUTION_FIELD_NAMES = {
    "expression",
    "jsx_path",
    "natural_text",
    "raw_text",
    "rule_ast",
    "script",
    "special_rules_text",
}
_EXECUTION_FIELD_COMPACT_NAMES = {
    re.sub(r"[^a-z0-9]+", "", value.casefold())
    for value in _EXECUTION_FIELD_NAMES
}
_EXECUTION_TEXT_RE = re.compile(
    r"(?:\.jsx\b|<script\b|javascript:|eval\s*\(|exec\s*\(|function\s*\(|=>|[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\s*\()",
    re.I,
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_OUTPUT_MAIN_RE = re.compile(r"^Output_main$")
_OUTPUT_SIDE_RE = re.compile(r"^Output_Side([A-Z])$")
_DESIGN_RE = re.compile(r"^Design\d{2,}$")
_FONT_RE = re.compile(r"^F[1-9]\d*$")
_STYLE_RE = re.compile(r"^style[1-9]\d*$", re.I)
_SLOT_RE = re.compile(r"^slot_[A-Za-z0-9_]+$")
_ANCHOR_RE = re.compile(r"^anchor_[A-Za-z0-9_]+$")
_TAIL_RE = re.compile(r"^tail_[A-Za-z0-9_]+$")
_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_LATIN_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_PUA_MIN = 0xE000
_PUA_MAX = 0xF8FF


class V2ContractError(ValueError):
    """Raised when a V2 contract cannot be normalized."""

    def __init__(self, issues: Iterable[Mapping[str, str]]) -> None:
        self.issues = [dict(issue) for issue in issues]
        message = "; ".join(f"{issue['path']}: {issue['message']}" for issue in self.issues)
        super().__init__(message or "Invalid V2 template contract.")


def check_v2_template_contract(payload: Any) -> Dict[str, Any]:
    """Return a non-throwing contract check result."""

    try:
        contract = normalize_v2_template_contract(payload)
    except V2ContractError as exc:
        return {"ok": False, "contract": None, "errors": exc.issues}
    return {"ok": True, "contract": contract, "errors": []}


def normalize_v2_template_contract(payload: Any) -> Dict[str, Any]:
    """Normalize one V2 draft configuration or raise with all blocking issues."""

    issues: list[Dict[str, str]] = []
    source = _mapping(payload, "$", issues)
    if not source:
        _raise_if_issues(issues)
    _reject_unknown(source, _TOP_LEVEL_FIELDS, "$", issues)

    schema = str(source.get("$schema") or V2_CONTRACT_SCHEMA).strip()
    if schema != V2_CONTRACT_SCHEMA:
        _issue(issues, "$.$schema", f"Unsupported V2 contract schema: {schema}")
    version = source.get("schema_version", V2_CONTRACT_VERSION)
    if version != V2_CONTRACT_VERSION:
        _issue(issues, "$.schema_version", f"Unsupported V2 contract version: {version}")

    template = _normalize_template(source.get("template", {}), issues)
    outputs = _normalize_outputs(source.get("outputs", []), issues)
    output_keys = {item["key"] for item in outputs}
    colors = _normalize_colors(source.get("colors", []), issues)
    field_bindings = _normalize_string_map(source.get("field_bindings", {}), "$.field_bindings", issues)
    option_mappings = _normalize_option_mappings(source.get("option_mappings", []), output_keys, issues)
    multi_name_customization = _normalize_metadata_object(
        source.get("multi_name_customization", {}),
        "$.multi_name_customization",
        issues,
    )
    render_layout = _normalize_metadata_object(source.get("render_layout", {}), "$.render_layout", issues)
    output = _normalize_metadata_object(source.get("output", {}), "$.output", issues)
    _validate_output_policy(output, issues)
    checks = _normalize_checks(source.get("checks", {}), issues)
    preview = _normalize_preview(source.get("preview", {}), issues)
    audit = _normalize_audit(source.get("audit", {}), issues)

    _raise_if_issues(issues)
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": template,
        "outputs": outputs,
        "colors": colors,
        "field_bindings": field_bindings,
        "option_mappings": option_mappings,
        "multi_name_customization": multi_name_customization,
        "render_layout": render_layout,
        "output": output,
        "checks": checks,
        "preview": preview,
        "audit": audit,
    }


def _normalize_template(value: Any, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, "$.template", issues)
    _reject_unknown(data, _TEMPLATE_FIELDS, "$.template", issues)
    _internal_false(data, "component_scope_executable", "$.template.component_scope_executable", issues)
    template_id = _required_string(data, "template_id", "$.template.template_id", issues)
    if template_id and not _SAFE_ID_RE.match(template_id):
        _issue(issues, "$.template.template_id", "Template ID may only contain letters, numbers, '-' and '_'.")
    name = _required_string(data, "name", "$.template.name", issues)
    component_key = _optional_string(data, "component_key", "$.template.component_key", issues)
    scope = _scope(data.get("scope", "local"), "$.template.scope", issues)
    return {
        "template_id": template_id,
        "name": name,
        "shop_name": _optional_string(data, "shop_name", "$.template.shop_name", issues),
        "component_key": component_key,
        "scope": scope,
        "component_scope_executable": False,
    }


def _normalize_outputs(value: Any, issues: list[Dict[str, str]]) -> list[Dict[str, Any]]:
    items = _list(value, "$.outputs", issues)
    if not items:
        _issue(issues, "$.outputs", "At least one output is required.")
        return []
    outputs = [_normalize_output(item, f"$.outputs[{index}]", issues) for index, item in enumerate(items)]
    for index, output in enumerate(outputs, start=1):
        output["order"] = index
        if len(outputs) == 1 and output.get("key") == "Output_main" and not output["display_name"]:
            output["display_name"] = "主效果图"
    return outputs


def _normalize_output(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    _reject_unknown(data, _OUTPUT_FIELDS, path, issues)
    _internal_false(data, "component_scope_executable", f"{path}.component_scope_executable", issues)
    _internal_order(data, f"{path}.order", issues)
    key = _required_string(data, "key", f"{path}.key", issues)
    if key and not (_OUTPUT_MAIN_RE.match(key) or _OUTPUT_SIDE_RE.match(key)):
        _issue(issues, f"{path}.key", "Output key must be Output_main or Output_SideA/B/C...")
    scope = _scope(data.get("scope", "local"), f"{path}.scope", issues)
    return {
        "key": key,
        "display_name": _optional_string(data, "display_name", f"{path}.display_name", issues),
        "component_key": _optional_string(data, "component_key", f"{path}.component_key", issues),
        "scope": scope,
        "component_scope_executable": False,
        "style": _normalize_option_group(data.get("style", {}), "style", f"{path}.style", issues),
        "design": _normalize_option_group(data.get("design", {}), "design", f"{path}.design", issues),
        "font": _normalize_option_group(data.get("font", {}), "font", f"{path}.font", issues),
    }


def _normalize_option_group(value: Any, kind: str, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    if value in ({}, None, ""):
        return {"field": "", "options": []}
    data = _mapping(value, path, issues)
    _reject_unknown(data, _GROUP_FIELDS, path, issues)
    options = [
        _normalize_option(item, kind, f"{path}.options[{index}]", issues)
        for index, item in enumerate(_list(data.get("options", []), f"{path}.options", issues))
    ]
    return {
        "field": _optional_string(data, "field", f"{path}.field", issues),
        "options": options,
    }


def _normalize_option(value: Any, kind: str, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    allowed = _STYLE_OPTION_FIELDS if kind == "style" else _DESIGN_FONT_OPTION_FIELDS
    _reject_unknown(data, allowed, path, issues)
    _internal_false(data, "component_scope_executable", f"{path}.component_scope_executable", issues)
    key = _required_string(data, "key", f"{path}.key", issues)
    if key and kind == "style" and not _STYLE_RE.match(key):
        _issue(issues, f"{path}.key", "Style options must use style1/style2/... names.")
    if key and kind == "design" and not _DESIGN_RE.match(key):
        _issue(issues, f"{path}.key", "Design options must use full names such as Design03.")
    if key and kind == "font" and not _FONT_RE.match(key):
        _issue(issues, f"{path}.key", "Font options must keep business names such as F1 or F12.")
    normalized = {
        "key": key,
        "label": _optional_string(data, "label", f"{path}.label", issues),
        "component_key": _optional_string(data, "component_key", f"{path}.component_key", issues),
        "scope": _scope(data.get("scope", "local"), f"{path}.scope", issues),
        "component_scope_executable": False,
    }
    if kind == "style":
        normalized["dimensions"] = _normalize_dimension_rule(data.get("dimensions", {}), f"{path}.dimensions", issues)
        return normalized
    preset = _optional_string(data, "content_preset", f"{path}.content_preset", issues)
    if preset and preset not in V2_OPTION_CONTENT_PRESETS:
        _issue(issues, f"{path}.content_preset", f"Unsupported V2 processing preset: {preset}")
    normalized.update(
        {
            "content_preset": preset,
            "font_dependencies": _string_list(data.get("font_dependencies", []), f"{path}.font_dependencies", issues),
            "slots": [
                _normalize_slot(item, f"{path}.slots[{index}]", issues)
                for index, item in enumerate(_list(data.get("slots", []), f"{path}.slots", issues))
            ],
            "assets": [
                _normalize_asset(item, f"{path}.assets[{index}]", issues)
                for index, item in enumerate(_list(data.get("assets", []), f"{path}.assets", issues))
            ],
        }
    )
    return normalized


def _normalize_slot(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    _reject_unknown(data, _SLOT_FIELDS, path, issues)
    key = _required_string(data, "key", f"{path}.key", issues)
    if key and not _SLOT_RE.match(key):
        _issue(issues, f"{path}.key", "Slot names must use slot_*.")
    preset = _optional_string(data, "preset", f"{path}.preset", issues) or "direct_text"
    if preset not in V2_PROCESSING_PRESETS:
        _issue(issues, f"{path}.preset", f"Unsupported V2 processing preset: {preset}")
    anchor = _optional_string(data, "anchor", f"{path}.anchor", issues)
    if anchor and not _ANCHOR_RE.match(anchor):
        _issue(issues, f"{path}.anchor", "Anchor names must use anchor_*.")
    required = data.get("required", True)
    if not isinstance(required, bool):
        _issue(issues, f"{path}.required", "required must be true or false.")
        required = True
    source_field = _optional_string(data, "source_field", f"{path}.source_field", issues)
    if source_field and not _FIELD_RE.match(source_field):
        _issue(issues, f"{path}.source_field", "source_field must be a stable identifier.")
    return {
        "key": key,
        "source_field": source_field,
        "required": required,
        "preset": preset,
        "anchor": anchor,
        "tails": [
            _normalize_tail(item, f"{path}.tails[{index}]", issues)
            for index, item in enumerate(_list(data.get("tails", []), f"{path}.tails", issues))
        ],
        "asset_key": _optional_string(data, "asset_key", f"{path}.asset_key", issues),
        "dimension_rule": _normalize_dimension_rule(data.get("dimension_rule", {}), f"{path}.dimension_rule", issues),
        "font_dependencies": _string_list(data.get("font_dependencies", []), f"{path}.font_dependencies", issues),
        "color_binding": _optional_string(data, "color_binding", f"{path}.color_binding", issues),
        "preserve_composition": bool(data.get("preserve_composition") is True),
    }


def _normalize_asset(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    _reject_unknown(data, _ASSET_FIELDS, path, issues)
    _internal_false(data, "component_scope_executable", f"{path}.component_scope_executable", issues)
    slot = _required_string(data, "slot", f"{path}.slot", issues)
    if slot and not _SLOT_RE.match(slot):
        _issue(issues, f"{path}.slot", "Asset slot references must use slot_*.")
    return {
        "asset_key": _required_string(data, "asset_key", f"{path}.asset_key", issues),
        "slot": slot,
        "supported_values": _string_list(data.get("supported_values", []), f"{path}.supported_values", issues),
        "component_key": _optional_string(data, "component_key", f"{path}.component_key", issues),
        "scope": _scope(data.get("scope", "local"), f"{path}.scope", issues),
        "component_scope_executable": False,
    }


def _normalize_tail(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    _reject_unknown(data, _TAIL_FIELDS, path, issues)
    key = _required_string(data, "key", f"{path}.key", issues)
    if key and not _TAIL_RE.match(key):
        _issue(issues, f"{path}.key", "Tail sample names must use tail_*.")
    position = _required_string(data, "position", f"{path}.position", issues)
    if position and position not in {"first", "last"}:
        _issue(issues, f"{path}.position", "Tail position must be first or last.")
    sample = _required_string(data, "sample", f"{path}.sample", issues)
    if sample and (len(sample) != 1 or not sample.isascii() or not sample.isalpha()):
        _issue(issues, f"{path}.sample", "Tail sample must be one ASCII letter.")
    normalized: Dict[str, Any] = {
        "key": key,
        "position": position,
        "sample": sample,
    }
    if "pua_base" in data and data.get("pua_base") not in (None, ""):
        normalized["pua_base"] = _pua_codepoint(data.get("pua_base"), f"{path}.pua_base", issues, continuous_tail_base=True)
    if "glyph_map" in data and data.get("glyph_map") not in (None, ""):
        normalized["glyph_map"] = _normalize_tail_glyph_map(data.get("glyph_map"), f"{path}.glyph_map", issues)
    return normalized


def _normalize_tail_glyph_map(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, int]:
    data = _mapping(value, path, issues)
    result: Dict[str, int] = {}
    for key, raw in data.items():
        letter = str(key or "").strip().casefold()
        if len(letter) != 1 or letter not in _LATIN_LETTERS:
            _issue(issues, f"{path}.{key}", "Tail glyph map keys must be ASCII letters.")
            continue
        result[letter] = _pua_codepoint(raw, f"{path}.{key}", issues)
    missing = [letter for letter in _LATIN_LETTERS if letter not in result]
    if missing:
        _issue(issues, path, "Tail glyph map must cover A-Z.")
    return {letter: result[letter] for letter in _LATIN_LETTERS if letter in result}


def _pua_codepoint(value: Any, path: str, issues: list[Dict[str, str]], *, continuous_tail_base: bool = False) -> int:
    codepoint: int | None = None
    if isinstance(value, bool):
        codepoint = None
    elif isinstance(value, int):
        codepoint = value
    elif isinstance(value, str):
        text = value.strip().lower()
        try:
            codepoint = int(text[2:], 16) if text.startswith("0x") else int(text, 10)
        except ValueError:
            codepoint = None
    if codepoint is None:
        _issue(issues, path, "Expected a PUA codepoint integer or hex string.")
        return 0
    max_codepoint = codepoint + 25 if continuous_tail_base else codepoint
    if codepoint < _PUA_MIN or max_codepoint > _PUA_MAX:
        _issue(issues, path, "Tail glyph proof must stay inside the Unicode private-use area.")
    return codepoint


def _normalize_dimension_rule(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    if value in ({}, None, ""):
        return {}
    data = _mapping(value, path, issues)
    _reject_unknown(data, _DIMENSION_FIELDS, path, issues)
    normalized: Dict[str, Any] = {}
    mode = _optional_string(data, "mode", f"{path}.mode", issues)
    if mode:
        if mode not in {"fixed", "style", "anchor", "slot"}:
            _issue(issues, f"{path}.mode", f"Unsupported dimension mode: {mode}")
        normalized["mode"] = mode
    for field in ("width_mm", "height_mm", "tolerance_mm"):
        if field in data:
            normalized[field] = _number(data.get(field), f"{path}.{field}", issues)
    return normalized


def _normalize_colors(value: Any, issues: list[Dict[str, str]]) -> list[Dict[str, Any]]:
    colors = []
    for index, item in enumerate(_list(value, "$.colors", issues)):
        path = f"$.colors[{index}]"
        data = _mapping(item, path, issues)
        _reject_unknown(data, _COLOR_FIELDS, path, issues)
        space = _required_string(data, "space", f"{path}.space", issues).upper()
        if space and space not in {"RGB", "CMYK", "SPOT"}:
            _issue(issues, f"{path}.space", "Color space must be RGB, CMYK, or SPOT.")
        allow_recolor = data.get("allow_recolor", False)
        if not isinstance(allow_recolor, bool):
            _issue(issues, f"{path}.allow_recolor", "allow_recolor must be true or false.")
            allow_recolor = False
        colors.append(
            {
                "key": _required_string(data, "key", f"{path}.key", issues),
                "zh_name": _required_string(data, "zh_name", f"{path}.zh_name", issues),
                "space": space,
                "value": _normalize_color_value(data.get("value"), space, f"{path}.value", issues),
                "allow_recolor": allow_recolor,
            }
        )
    return colors


def _normalize_option_mappings(value: Any, output_keys: set[str], issues: list[Dict[str, str]]) -> list[Dict[str, str]]:
    mappings = []
    for index, item in enumerate(_list(value, "$.option_mappings", issues)):
        path = f"$.option_mappings[{index}]"
        data = _mapping(item, path, issues)
        _reject_unknown(data, _OPTION_MAPPING_FIELDS, path, issues)
        output = _required_string(data, "output", f"{path}.output", issues)
        if output and output_keys and output not in output_keys:
            _issue(issues, f"{path}.output", f"Unknown output key: {output}")
        group = _required_string(data, "group", f"{path}.group", issues)
        if group and group not in {"style", "design", "font", "color"}:
            _issue(issues, f"{path}.group", f"Unsupported option mapping group: {group}")
        mappings.append(
            {
                "field": _required_string(data, "field", f"{path}.field", issues),
                "source_value": _required_string(data, "source_value", f"{path}.source_value", issues),
                "target": _required_string(data, "target", f"{path}.target", issues),
                "output": output,
                "group": group,
            }
        )
    return mappings


def _normalize_checks(value: Any, issues: list[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    data = _mapping(value, "$.checks", issues) if value not in ({}, None, "") else {}
    _reject_unknown(data, set(V2_VERIFICATION_KEYS), "$.checks", issues)
    result = {key: {"status": "pending", "reason": ""} for key in V2_VERIFICATION_KEYS}
    for key, raw in data.items():
        path = f"$.checks.{key}"
        if isinstance(raw, str):
            status = raw
            reason = ""
        else:
            item = _mapping(raw, path, issues)
            _reject_unknown(item, _CHECK_FIELDS, path, issues)
            status = _optional_string(item, "status", f"{path}.status", issues) or "pending"
            reason = _optional_string(item, "reason", f"{path}.reason", issues)
        if status not in V2_CHECK_STATUSES:
            _issue(issues, path, f"Check status must be one of: {', '.join(sorted(V2_CHECK_STATUSES))}.")
            status = "pending"
        result[str(key)] = {"status": status, "reason": reason}
    return result


def _normalize_preview(value: Any, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, "$.preview", issues) if value not in ({}, None, "") else {}
    _reject_unknown(data, _PREVIEW_FIELDS, "$.preview", issues)
    evidence = _mapping(data.get("evidence", {}), "$.preview.evidence", issues) if data.get("evidence") else {}
    _reject_unknown(evidence, _PREVIEW_EVIDENCE_FIELDS, "$.preview.evidence", issues)
    sample_rows = _list(data.get("sample_rows", []), "$.preview.sample_rows", issues)
    normalized_rows = [
        _normalize_sample_row(row, f"$.preview.sample_rows[{index}]", issues)
        for index, row in enumerate(sample_rows)
    ]
    return {"sample_rows": normalized_rows, "evidence": _normalize_preview_evidence(evidence, issues)}


def _normalize_audit(value: Any, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, "$.audit", issues) if value not in ({}, None, "") else {}
    _reject_unknown(data, _AUDIT_FIELDS, "$.audit", issues)
    return {
        "scan_version": _optional_string(data, "scan_version", "$.audit.scan_version", issues),
        "template_sha256": _optional_string(data, "template_sha256", "$.audit.template_sha256", issues),
        "config_version": _non_negative_int(data.get("config_version", 0), "$.audit.config_version", issues),
    }


def _normalize_color_value(value: Any, space: str, path: str, issues: list[Dict[str, str]]) -> Any:
    if space in {"RGB", "CMYK"}:
        expected = 3 if space == "RGB" else 4
        if not isinstance(value, list) or len(value) != expected:
            _issue(issues, path, f"{space} colors require {expected} numeric channels.")
            return []
        channels = [_number(channel, f"{path}[{index}]", issues) for index, channel in enumerate(value)]
        maximum = 255 if space == "RGB" else 100
        if any(channel > maximum for channel in channels):
            _issue(issues, path, f"{space} color channels exceed the allowed range.")
        return channels
    if space == "SPOT":
        if not isinstance(value, str) or not value.strip():
            _issue(issues, path, "Spot colors require a non-empty sample name.")
            return ""
        return _safe_text(value.strip(), path, issues)
    if value not in (None, ""):
        _safe_metadata_value(value, path, issues)
    return deepcopy(value)


def _normalize_sample_row(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    data = _mapping(value, path, issues)
    normalized: Dict[str, Any] = {}
    for key, raw in data.items():
        key_text = str(key or "").strip()
        key_path = f"{path}.{key_text or '<empty>'}"
        if not key_text:
            _issue(issues, key_path, "Preview sample row keys cannot be empty.")
            continue
        if _is_execution_field_name(key_text):
            _issue(issues, key_path, "Preview sample rows cannot contain execution or natural-language rule fields.")
            continue
        normalized[key_text] = _safe_scalar(raw, key_path, issues)
    return normalized


def _normalize_preview_evidence(evidence: Mapping[str, Any], issues: list[Dict[str, str]]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in evidence.items():
        path = f"$.preview.evidence.{key}"
        if key in {
            "draft_revision",
            "template_sha256",
            "scan_sha256",
            "config_sha256",
            "sample_sha256",
            "render_task_sha256",
            "preview_sha256",
            "renderer_version",
            "rendered_at",
            "approved_by",
            "approved_at",
        }:
            if not isinstance(value, str):
                _issue(issues, path, "Preview evidence value must be a string.")
                continue
            normalized[str(key)] = _safe_text(value.strip(), path, issues)
        elif key == "warnings":
            normalized[str(key)] = _string_list(value, path, issues)
        elif key == "font_check":
            normalized[str(key)] = _safe_metadata_value(value, path, issues)
        elif key == "outputs":
            output_values = _list(value, path, issues)
            normalized[str(key)] = [
                _normalize_preview_output(output, f"{path}[{index}]", issues)
                for index, output in enumerate(output_values)
            ]
    return normalized


def _normalize_preview_output(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, str]:
    data = _mapping(value, path, issues)
    _reject_unknown(data, _PREVIEW_OUTPUT_FIELDS, path, issues)
    return {
        "key": _required_string(data, "key", f"{path}.key", issues),
        "ai_sha256": _required_string(data, "ai_sha256", f"{path}.ai_sha256", issues),
        "png_sha256": _required_string(data, "png_sha256", f"{path}.png_sha256", issues),
    }


def _normalize_string_map(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, str]:
    data = _mapping(value, path, issues) if value not in ({}, None, "") else {}
    result: Dict[str, str] = {}
    for key, raw in data.items():
        if not isinstance(key, str) or not _FIELD_RE.match(key):
            _issue(issues, f"{path}.{key}", "Field binding keys must be stable identifiers.")
            continue
        if not isinstance(raw, str) or not raw.strip():
            _issue(issues, f"{path}.{key}", "Field binding values must be non-empty column names.")
            continue
        result[key] = _safe_text(raw.strip(), f"{path}.{key}", issues)
    return result


def _normalize_metadata_object(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    if value in ({}, None, ""):
        return {}
    data = _mapping(value, path, issues)
    normalized: Dict[str, Any] = {}
    for key, raw in data.items():
        key_text = str(key or "").strip()
        key_path = f"{path}.{key_text or '<empty>'}"
        if not key_text:
            _issue(issues, key_path, "Metadata keys cannot be empty.")
            continue
        if _is_execution_field_name(key_text):
            _issue(issues, key_path, "Metadata cannot contain execution or natural-language rule fields.")
            continue
        normalized[key_text] = _safe_metadata_value(raw, key_path, issues)
    return normalized


def _validate_output_policy(output: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    for key in ("outline_text", "pathfinder_merge"):
        if key in output and not isinstance(output[key], bool):
            _issue(issues, f"$.output.{key}", "Output policy values must be boolean.")


def _mapping(value: Any, path: str, issues: list[Dict[str, str]]) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    _issue(issues, path, "Expected a JSON object.")
    return {}


def _list(value: Any, path: str, issues: list[Dict[str, str]]) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return list(value)
    _issue(issues, path, "Expected a JSON array.")
    return []


def _string_list(value: Any, path: str, issues: list[Dict[str, str]]) -> list[str]:
    result = []
    for index, item in enumerate(_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            _issue(issues, f"{path}[{index}]", "Expected a non-empty string.")
            continue
        result.append(_safe_text(item.strip(), f"{path}[{index}]", issues))
    return result


def _required_string(data: Mapping[str, Any], key: str, path: str, issues: list[Dict[str, str]]) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        _issue(issues, path, "Required string is missing.")
        return ""
    return _safe_text(value.strip(), path, issues)


def _optional_string(data: Mapping[str, Any], key: str, path: str, issues: list[Dict[str, str]]) -> str:
    if key not in data or data.get(key) in (None, ""):
        return ""
    value = data.get(key)
    if not isinstance(value, str):
        _issue(issues, path, "Expected a string.")
        return ""
    return _safe_text(value.strip(), path, issues)


def _scope(value: Any, path: str, issues: list[Dict[str, str]]) -> str:
    if value in (None, ""):
        return "local"
    if not isinstance(value, str):
        _issue(issues, path, "Expected a string scope.")
        return "local"
    scope = value.strip()
    if scope not in V2_SCOPE_VALUES:
        _issue(issues, path, "Scope must be local or shared.")
        return "local"
    return scope


def _internal_false(data: Mapping[str, Any], key: str, path: str, issues: list[Dict[str, str]]) -> None:
    if key not in data or data.get(key) in (None, ""):
        return
    if data.get(key) is not False:
        _issue(issues, path, "Internal execution marker must be false.")


def _internal_order(data: Mapping[str, Any], path: str, issues: list[Dict[str, str]]) -> None:
    if "order" not in data:
        return
    value = data.get("order")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _issue(issues, path, "Internal order must be a non-negative integer.")


def _number(value: Any, path: str, issues: list[Dict[str, str]]) -> float:
    if isinstance(value, bool):
        _issue(issues, path, "Expected a number.")
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        _issue(issues, path, "Expected a number.")
        return 0.0
    if number < 0:
        _issue(issues, path, "Expected a non-negative number.")
    return number


def _non_negative_int(value: Any, path: str, issues: list[Dict[str, str]]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _issue(issues, path, "Expected a non-negative integer.")
        return 0
    if value < 0:
        _issue(issues, path, "Expected a non-negative integer.")
        return 0
    return value


def _safe_scalar(value: Any, path: str, issues: list[Dict[str, str]]) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value, path, issues)
    _issue(issues, path, "Expected a scalar value.")
    _safe_metadata_value(value, path, issues)
    return ""


def _safe_text(value: str, path: str, issues: list[Dict[str, str]]) -> str:
    if _EXECUTION_TEXT_RE.search(value):
        _issue(issues, path, "Text value cannot contain script, JSX, or executable references.")
    return value


def _safe_metadata_value(value: Any, path: str, issues: list[Dict[str, str]]) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value, path, issues)
    if isinstance(value, list):
        return [_safe_metadata_value(item, f"{path}[{index}]", issues) for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        normalized: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key or "").strip()
            key_path = f"{path}.{key_text or '<empty>'}"
            if not key_text:
                _issue(issues, key_path, "Metadata keys cannot be empty.")
                continue
            if _is_execution_field_name(key_text):
                _issue(issues, key_path, "Metadata cannot contain execution or natural-language rule fields.")
                continue
            normalized[key_text] = _safe_metadata_value(item, key_path, issues)
        return normalized
    _issue(issues, path, "Unsupported metadata value type.")
    return ""


def _is_execution_field_name(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    compact = re.sub(r"[^a-z0-9]+", "", value.strip().casefold())
    return normalized in _EXECUTION_FIELD_NAMES or compact in _EXECUTION_FIELD_COMPACT_NAMES


def _reject_unknown(
    data: Mapping[str, Any],
    allowed: set[str],
    path: str,
    issues: list[Dict[str, str]],
) -> None:
    for key in sorted(set(data) - allowed):
        _issue(issues, f"{path}.{key}", "Unknown V2 contract field.")


def _issue(issues: list[Dict[str, str]], path: str, message: str) -> None:
    issues.append({"path": path, "message": message})


def _raise_if_issues(issues: list[Dict[str, str]]) -> None:
    if issues:
        raise V2ContractError(issues)
