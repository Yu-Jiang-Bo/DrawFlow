"""Canonical template rule pack schema and legacy migration helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping

from .font_style_rules import normalize_font_style_rules, strip_legacy_font_bold_overrides
from .llm_rule_parser import normalize_option_list
from .name_color_cycle import normalize_name_color_cycle
from .template_rule_ast import migrate_legacy_rule_ast, normalize_rule_ast


RULE_PACK_SCHEMA = "custom-renderer/template-rule-pack"
RULE_PACK_VERSION = 2

PROFILE_PURE_TEXT = "pure_text"
PROFILE_FIXED_FONT_DESIGN = "fixed_font_design"
PROFILE_COMPOSITE = "composite"
PROFILE_BUNDLE = "bundle"
PROFILE_UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class TemplateProfile:
    key: str
    label: str
    required_rule_sections: tuple[str, ...]
    default_capabilities: tuple[str, ...]


PROFILE_DEFINITIONS = {
    PROFILE_PURE_TEXT: TemplateProfile(
        key=PROFILE_PURE_TEXT,
        label="纯文本",
        required_rule_sections=("font_options", "text_targets"),
        default_capabilities=("replace_text", "text_fit_box"),
    ),
    PROFILE_FIXED_FONT_DESIGN: TemplateProfile(
        key=PROFILE_FIXED_FONT_DESIGN,
        label="设计加固定字体",
        required_rule_sections=("design_options", "text_targets"),
        default_capabilities=("replace_text",),
    ),
    PROFILE_COMPOSITE: TemplateProfile(
        key=PROFILE_COMPOSITE,
        label="尺寸/设计/字体/颜色复合模板",
        required_rule_sections=("text_targets",),
        default_capabilities=("replace_text",),
    ),
    PROFILE_BUNDLE: TemplateProfile(
        key=PROFILE_BUNDLE,
        label="套装",
        required_rule_sections=("children",),
        default_capabilities=("compose_templates",),
    ),
}


def profile_definition(profile: str) -> TemplateProfile | None:
    return PROFILE_DEFINITIONS.get(str(profile or "").strip())


def normalize_template_rule_pack(payload: Mapping[str, Any], *, template_id: str = "") -> Dict[str, Any]:
    """Return a stable rule pack from a canonical pack or legacy flat config."""

    source = deepcopy(dict(payload or {}))
    if source.get("$schema") == RULE_PACK_SCHEMA or "rules" in source and "template" in source:
        return _normalize_canonical_pack(source, template_id=template_id)
    return migrate_legacy_template_rule(source, template_id=template_id)


def strip_template_output_text_flags(pack: Any) -> Any:
    """Remove template-level text output flags from a rule pack copy."""

    if not isinstance(pack, dict):
        return pack
    sanitized = dict(pack)
    _strip_text_flags_from_output(sanitized)
    rules = sanitized.get("rules")
    if not isinstance(rules, dict):
        return sanitized
    sanitized_rules = dict(rules)
    _strip_text_flags_from_output(sanitized_rules)
    sanitized["rules"] = sanitized_rules
    return sanitized


def migrate_legacy_template_rule(payload: Mapping[str, Any], *, template_id: str = "") -> Dict[str, Any]:
    """Migrate the current flat rule JSON without discarding legacy details."""

    source = deepcopy(dict(payload or {}))
    resolved_template_id = str(template_id or source.get("template_id") or "").strip()
    profile = infer_profile(source)
    design_options, inferred_design_settings = _normalize_design_options(source.get("design_options"))
    design_settings = {**inferred_design_settings, **_dict(source.get("design_settings"))}
    assets = _normalize_assets(source.get("assets"))
    text_targets = _dict_list(source.get("text_targets") or source.get("slots"))
    unresolved = _dict_list(source.get("unresolved_items"))
    legacy_option_overrides = _dict(source.get("option_overrides"))
    special_rules_text = str(source.get("special_rules_text") or "").strip()
    legacy_rule_ast = migrate_legacy_rule_ast(
        source_text=special_rules_text,
        name_color_cycle=source.get("name_color_cycle"),
        font_style_rules=source.get("font_style_rules"),
        option_overrides=legacy_option_overrides,
    )
    rule_ast = (
        normalize_rule_ast(source.get("rule_ast"), natural_text=special_rules_text)
        if isinstance(source.get("rule_ast"), Mapping)
        else legacy_rule_ast
    )
    if profile == PROFILE_UNCLASSIFIED and not _has_unresolved_code(unresolved, "profile"):
        unresolved.append({"code": "profile", "message": "无法从旧规则确定模板 Profile，需要人工确认"})

    rules = {
        "option_groups": _dict_list(source.get("option_groups")),
        "font_options": normalize_option_list(source.get("font_options")),
        "design_options": design_options,
        "design_settings": design_settings,
        "design_font_options": normalize_option_list(
            source.get("design_font_options") or design_settings.get("design_font_options")
        ),
        "style_options": normalize_option_list(source.get("style_options")),
        "dimensions": _dict(source.get("dimensions")),
        "text_targets": text_targets,
        "text_sequences": _dict_list(source.get("text_sequences")),
        "text_policies": _dict(source.get("text_policies")),
        "multi_name_customization": _dict(source.get("multi_name_customization")),
        "render_layout": _dict(source.get("render_layout")),
        "name_color_cycle": normalize_name_color_cycle(source.get("name_color_cycle")),
        "slot_mappings": _dict_list(source.get("slot_mappings")),
        "order_bindings": _dict(source.get("order_bindings")),
        "asset_mappings": _dict_list(source.get("asset_mappings")),
        "defaults": _dict(source.get("defaults")),
        "font_style_rules": normalize_font_style_rules(
            source.get("font_style_rules"),
            legacy_option_overrides=legacy_option_overrides,
        ),
        "option_overrides": strip_legacy_font_bold_overrides(legacy_option_overrides),
        "special_rules_text": special_rules_text,
        "rule_ast": rule_ast,
        "notes": _dict(source.get("notes")),
        "transforms": deepcopy(source.get("transforms", {})),
        "output": _dict(source.get("output")),
        "exceptions": _dict(source.get("exceptions")),
        "children": _dict_list(source.get("children")),
        "natural_text": str(source.get("natural_text") or source.get("raw_text") or ""),
    }
    return {
        "$schema": RULE_PACK_SCHEMA,
        "schema_version": RULE_PACK_VERSION,
        "template": {
            "template_id": resolved_template_id,
            "profile": profile,
            "legacy_mode": str(source.get("mode") or source.get("template_type") or "").strip(),
        },
        "structure": {
            "scan_version": "",
            "evidence": {},
        },
        "rules": rules,
        "assets": assets,
        "capabilities": normalize_option_list(source.get("capabilities")),
        "validation": {
            "status": str(source.get("status") or "draft").strip(),
            "unresolved_items": unresolved,
        },
        "audit": {
            "source_format": "legacy_flat",
            "source_version": source.get("version", ""),
            "legacy_payload": source,
        },
    }


def infer_profile(payload: Mapping[str, Any]) -> str:
    """Infer a draft Profile conservatively; unknown structures remain unclassified."""

    source = dict(payload or {})
    explicit = str(source.get("profile") or "").strip()
    if explicit in {*PROFILE_DEFINITIONS, PROFILE_UNCLASSIFIED}:
        return explicit

    template = source.get("template")
    if isinstance(template, Mapping):
        explicit = str(template.get("profile") or "").strip()
        if explicit in {*PROFILE_DEFINITIONS, PROFILE_UNCLASSIFIED}:
            return explicit

    mode = str(source.get("mode") or source.get("template_type") or "").strip().lower()
    if mode in {"bundle", "suite", "template_bundle"} or source.get("children"):
        return PROFILE_BUNDLE
    if mode == "pure_text":
        return PROFILE_PURE_TEXT
    if mode in {"pure_text_color_design", "pure_text_style", "curved_title_text", "asset_split"}:
        return PROFILE_COMPOSITE

    font_options = normalize_option_list(source.get("font_options"))
    design_options, _ = _normalize_design_options(source.get("design_options"))
    style_options = normalize_option_list(source.get("style_options"))
    assets = _normalize_assets(source.get("assets"))
    has_design_assets = bool(assets["items"]) or assets["policy"].get("mode") == "split_ai"
    if font_options and not design_options and not style_options and not has_design_assets:
        return PROFILE_PURE_TEXT
    if design_options and not font_options and not style_options and not has_design_assets:
        return PROFILE_FIXED_FONT_DESIGN
    if font_options or design_options or style_options or has_design_assets:
        return PROFILE_COMPOSITE
    return PROFILE_UNCLASSIFIED


def _normalize_canonical_pack(source: Dict[str, Any], *, template_id: str) -> Dict[str, Any]:
    template = _dict(source.get("template"))
    rules = _dict(source.get("rules"))
    profile = infer_profile({**rules, "profile": template.get("profile", "")})
    legacy_rules = {
        **rules,
        "slots": rules.get("text_targets", rules.get("slots", [])),
    }
    normalized = migrate_legacy_template_rule(
        {
            **legacy_rules,
            "template_id": template_id or template.get("template_id", ""),
            "profile": profile,
            "capabilities": source.get("capabilities", []),
            "status": _dict(source.get("validation")).get("status", "draft"),
            "unresolved_items": _dict(source.get("validation")).get("unresolved_items", []),
        }
    )
    normalized["assets"] = _normalize_pack_assets(source.get("assets"))
    _migrate_legacy_text_binding(normalized["rules"])
    normalized["structure"] = {
        "scan_version": str(_dict(source.get("structure")).get("scan_version", "")),
        "evidence": deepcopy(_dict(source.get("structure")).get("evidence", {})),
    }
    normalized["audit"] = deepcopy(_dict(source.get("audit")))
    normalized["audit"].setdefault("source_format", "template_rule_pack")
    extra_validation = deepcopy(_dict(source.get("validation")))
    extra_validation.pop("unresolved_items", None)
    normalized["validation"].update(extra_validation)
    normalized["validation"].setdefault("status", "draft")
    normalized["validation"].setdefault("unresolved_items", [])
    return normalized


def _migrate_legacy_text_binding(rules: Dict[str, Any]) -> None:
    """Keep old custom text field names out of the internal rule contract."""

    bindings = _dict(rules.get("order_bindings"))
    mappings = _dict_list(rules.get("slot_mappings"))
    sequences = _dict_list(rules.get("text_sequences"))
    migrated_legacy_text = False
    if "text" not in bindings:
        fields = {
            str(item.get("field") or item.get("source") or "").strip()
            for item in [*mappings, *sequences]
            if str(item.get("field") or item.get("source") or "").strip()
        }
        legacy_fields = [field for field in fields if field in bindings]
        if len(legacy_fields) == 1:
            legacy_field = legacy_fields[0]
            bindings["text"] = bindings.pop(legacy_field)
            for item in mappings:
                if str(item.get("field") or item.get("source") or "").strip() == legacy_field:
                    item["field"] = "text"
                    item.pop("source", None)
            for item in sequences:
                if str(item.get("field") or "").strip() == legacy_field:
                    item["field"] = "text"
            migrated_legacy_text = True
    if migrated_legacy_text:
        for item in mappings:
            if not str(item.get("delimiter") or "").strip():
                item.pop("sequence_index", None)
    rules["order_bindings"] = bindings
    rules["slot_mappings"] = mappings
    rules["text_sequences"] = sequences


def _normalize_design_options(value: Any) -> tuple[list[str], Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return normalize_option_list(value), {}
    settings = deepcopy(dict(value))
    options = normalize_option_list(value)
    return options, settings


def _normalize_assets(value: Any) -> Dict[str, Any]:
    if isinstance(value, list):
        return {"items": _dict_list(value), "policy": {}}
    if isinstance(value, Mapping):
        items = _dict_list(value.get("items"))
        policy = deepcopy(dict(value))
        policy.pop("items", None)
        return {"items": items, "policy": policy}
    return {"items": [], "policy": {}}


def _normalize_pack_assets(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return _normalize_assets(value)
    if "items" not in value and "policy" not in value:
        return _normalize_assets(value)
    return {
        "items": _dict_list(value.get("items")),
        "policy": _dict(value.get("policy")),
    }


def _dict(value: Any) -> Dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _strip_text_flags_from_output(container: Dict[str, Any]) -> None:
    output = container.get("output")
    if not isinstance(output, dict):
        return
    sanitized_output = {
        key: value
        for key, value in output.items()
        if key not in {"outline_text", "pathfinder_merge"}
    }
    if sanitized_output:
        container["output"] = sanitized_output
    else:
        container.pop("output", None)


def _dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def _has_unresolved_code(items: Iterable[Mapping[str, Any]], code: str) -> bool:
    return any(str(item.get("code") or "") == code for item in items)
