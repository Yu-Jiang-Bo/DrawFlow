"""Build editable template rule drafts from Illustrator scan evidence."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .template_rule_pack import (
    PROFILE_UNCLASSIFIED,
    infer_profile,
    normalize_template_rule_pack,
)


OPTION_RE = re.compile(r"^(F|Style|Design|D)\s*(\d+)$", re.I)
LIBRARY_OPTION_RE = re.compile(r"^#(\d+)$")
TARGET_RE = re.compile(r"^(Name|Text|Title|Date|Custom)[_\s-]?(\d+)?$", re.I)
ANCHOR_RE = re.compile(r"(?:_ANCHOR|text_box)$", re.I)
PT_TO_MM = 25.4 / 72.0


def build_rule_draft_from_scan(scan: Mapping[str, Any], *, template_id: str = "") -> Dict[str, Any]:
    """Convert immutable scan evidence into an editable, unconfirmed rule pack."""

    items = _dict_list(scan.get("items"))
    options, option_sources, untrusted_suggestions = _collect_options(items)
    asset_mappings, asset_mapping_issues = _collect_design_asset_mappings(
        items,
        options["design_font_options"],
        options["design_options"],
    )
    targets = _collect_text_targets(items)
    dimensions = _collect_dimensions(items, options["style_options"])
    capabilities = _collect_capabilities(targets, items, dimensions, asset_mappings)
    flat_rule = {
        "template_id": template_id or _template_id(scan),
        "profile": infer_profile(
            {
                "font_options": options["font_options"],
                "design_options": options["design_options"],
                "style_options": options["style_options"],
            }
        ),
        "status": "draft",
        "rule_source": "ai_scan_draft",
        "option_groups": _option_groups(options),
        **options,
        "dimensions": dimensions,
        "slots": targets,
        "capabilities": capabilities,
        "asset_mappings": asset_mappings,
        "unresolved_items": _unresolved_items(
            options, targets, untrusted_suggestions, asset_mapping_issues
        ),
    }
    pack = normalize_template_rule_pack(flat_rule)
    scan_version = str(scan.get("scan_version") or scan_fingerprint(scan))
    pack["structure"] = {
        "scan_version": scan_version,
        "evidence": build_scan_summary(scan),
    }
    pack["audit"] = {
        "source_format": "ai_scan_draft",
        "source_ai": str(_dict(scan.get("document")).get("source_ai") or ""),
        "field_sources": _field_sources(
            options, option_sources, targets, dimensions, asset_mappings
        ),
        "untrusted_suggestions": untrusted_suggestions,
        "confirmed_at": "",
    }
    return pack


def build_scan_summary(scan: Mapping[str, Any]) -> Dict[str, Any]:
    items = _dict_list(scan.get("items"))
    type_counts: Dict[str, int] = {}
    named_items = []
    for item in items:
        item_type = str(item.get("type") or "Unknown")
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
        if str(item.get("name") or "").strip():
            named_items.append({
                "path": str(item.get("path") or ""),
                "type": item_type,
                "name": str(item.get("name") or "").strip(),
            })
    return {
        "document": deepcopy(_dict(scan.get("document"))),
        "documents": deepcopy(scan.get("documents", [])) if isinstance(scan.get("documents"), list) else [],
        "source_files": deepcopy(scan.get("source_files", [])) if isinstance(scan.get("source_files"), list) else [],
        "layer_count": len(_dict_list(scan.get("layers"))),
        "item_count": len(items),
        "type_counts": type_counts,
        "named_items": named_items,
        "scan_errors": deepcopy(scan.get("scan_errors", [])) if isinstance(scan.get("scan_errors"), list) else [],
        "fatal_error": str(scan.get("fatal_error") or ""),
    }


def scan_fingerprint(scan: Mapping[str, Any]) -> str:
    stable_scan = deepcopy(dict(scan))
    stable_scan.pop("scan_version", None)
    stable = json.dumps(stable_scan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _collect_options(
    items: Iterable[Mapping[str, Any]],
) -> tuple[Dict[str, list[str]], Dict[str, set[str]], Dict[str, list[str]]]:
    roles = ("font_options", "style_options", "design_options", "design_font_options")
    found = {role: set() for role in roles}
    sources = {role: set() for role in roles}
    suggestions = {role: set() for role in roles}
    explicit_design_fonts: set[str] = set()
    legacy_design_fonts: set[str] = set()
    for item in items:
        if not _is_trusted_item(item):
            continue
        for source_key in ("name", "text"):
            value = str(item.get(source_key) or "").strip()
            match = OPTION_RE.fullmatch(value)
            if match:
                prefix = _option_prefix(match.group(1))
                option = f"{prefix}{int(match.group(2))}"
                role = _option_role(prefix)
            elif source_key == "name" and _is_library_option(item, value):
                option = f"#{int(LIBRARY_OPTION_RE.fullmatch(value).group(1))}"
                role = "design_options"
            else:
                continue
            if source_key == "text":
                suggestions[role].add(option)
                continue
            if role == "font_options" and _is_design_font_asset_group(item):
                explicit_design_fonts.add(option)
                continue
            if role == "font_options" and _is_legacy_design_asset_group(item):
                legacy_design_fonts.add(option)
                continue
            found[role].add(option)
            sources[role].add(source_key)
    # New resource roles are explicit. Legacy "独立设计模板" keeps the safer
    # cross-file match so previously uploaded assets do not become active unexpectedly.
    matched_design_fonts = legacy_design_fonts & found["font_options"]
    design_font_options = explicit_design_fonts | matched_design_fonts
    found["design_font_options"].update(design_font_options)
    if design_font_options:
        sources["design_font_options"].add("independent_design_group")
    return (
        {key: sorted(values, key=_numbered_sort_key) for key, values in found.items()},
        sources,
        {key: sorted(values, key=_numbered_sort_key) for key, values in suggestions.items() if values},
    )


def _collect_design_asset_mappings(
    items: Iterable[Mapping[str, Any]],
    design_font_options: Iterable[str],
    design_options: Iterable[str],
) -> tuple[list[Dict[str, str]], list[Dict[str, str]]]:
    """Map named option groups in independent resource files to their owning asset."""

    allowed_font_options = {str(value).strip() for value in design_font_options if str(value).strip()}
    allowed_design_options = {str(value).strip() for value in design_options if str(value).strip()}
    candidates: Dict[str, set[tuple[str, str]]] = {}
    for item in items:
        if not _is_trusted_item(item):
            continue
        name = str(item.get("name") or "").strip()
        match = OPTION_RE.fullmatch(name)
        if not match:
            continue
        source_ai = str(item.get("source_ai") or "").strip()
        if not source_ai:
            continue
        prefix = _option_prefix(match.group(1))
        option = f"{prefix}{int(match.group(2))}"
        is_font_candidate = (
            prefix == "F"
            and (_is_design_font_asset_group(item) or _is_legacy_design_asset_group(item))
            and option in allowed_font_options
        )
        is_design_candidate = (
            prefix in {"D", "Design"}
            and _is_independent_design_resource_group(item)
            and option in allowed_design_options
        )
        if not (is_font_candidate or is_design_candidate):
            continue
        candidates.setdefault(option, set()).add((Path(source_ai).name, name))

    mappings: list[Dict[str, str]] = []
    issues: list[Dict[str, str]] = []
    for option in sorted(candidates, key=_numbered_sort_key):
        matches = sorted(candidates[option])
        if len(matches) != 1:
            issues.append(
                {
                    "code": "design_asset_mapping",
                    "message": f"Independent resource {option} needs an asset mapping confirmation.",
                }
            )
            continue
        asset, group = matches[0]
        mappings.append({"option": option, "asset": asset, "group": group})
    return mappings, issues


def _collect_text_targets(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    targets = []
    for item in items:
        if not _is_trusted_item(item):
            continue
        if str(item.get("type") or "") != "TextFrame":
            continue
        name = str(item.get("name") or "").strip()
        if not name or not TARGET_RE.fullmatch(name):
            continue
        text_kind = str(item.get("text_kind") or "").lower()
        target_type = "text_on_curve" if "path" in text_kind else "replace_text"
        targets.append(
            {
                "name": name,
                "type": target_type,
                "source_path": str(item.get("path") or ""),
                "font_name": str(item.get("font_name") or ""),
            }
        )
    return targets


def _collect_dimensions(items: Iterable[Mapping[str, Any]], style_options: Iterable[str]) -> Dict[str, Any]:
    styles = set(style_options)
    dimensions: Dict[str, Any] = {}
    for item in items:
        if not _is_trusted_item(item):
            continue
        name = str(item.get("name") or "").strip()
        bounds = item.get("bounds")
        if name not in styles and not ANCHOR_RE.search(name):
            continue
        if not isinstance(bounds, list) or len(bounds) != 4:
            continue
        try:
            width = abs(float(bounds[2]) - float(bounds[0])) * PT_TO_MM
            height = abs(float(bounds[1]) - float(bounds[3])) * PT_TO_MM
        except (TypeError, ValueError):
            continue
        dimensions[name] = {
            "width_mm": round(width, 3),
            "height_mm": round(height, 3),
            "source": "ai_visible_bounds",
        }
    return dimensions


def _collect_capabilities(
    targets: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    dimensions: Mapping[str, Any],
    asset_mappings: Iterable[Mapping[str, Any]],
) -> list[str]:
    capabilities = set()
    for target in targets:
        capabilities.add(str(target.get("type") or "replace_text"))
    if dimensions:
        capabilities.add("scale_to_box")
    if any(
        _is_trusted_item(item) and "path" in str(item.get("text_kind") or "").lower()
        for item in items
    ):
        capabilities.add("text_on_curve")
    if any(asset_mappings):
        capabilities.add("place_ai_asset")
    return sorted(value for value in capabilities if value)


def _option_groups(options: Mapping[str, list[str]]) -> list[Dict[str, Any]]:
    groups = []
    for role, values in options.items():
        if not values:
            continue
        prefix = re.sub(r"\d+$", "", values[0])
        groups.append({"name": _range_name(values), "prefix": prefix, "role": role, "values": values})
    return groups


def _unresolved_items(
    options: Mapping[str, list[str]],
    targets: list[Dict[str, Any]],
    untrusted_suggestions: Mapping[str, list[str]],
    asset_mapping_issues: Iterable[Mapping[str, str]],
) -> list[Dict[str, str]]:
    unresolved = [{"code": "confirmation_required", "message": "自动提取结果需要用户确认后才能保存"}]
    if infer_profile(options) == PROFILE_UNCLASSIFIED:
        unresolved.append({"code": "profile", "message": "未识别出模板 Profile"})
    if not targets:
        unresolved.append({"code": "text_targets", "message": "未识别到已命名的可编辑文字目标"})
    if any(untrusted_suggestions.values()):
        unresolved.append({"code": "option_group_names", "message": "发现画面文字标签建议，需要确认并命名对应对象编组"})
    unresolved.extend(dict(item) for item in asset_mapping_issues)
    return unresolved


def _field_sources(
    options: Mapping[str, list[str]],
    option_sources: Mapping[str, set[str]],
    targets: list[Dict[str, Any]],
    dimensions: Mapping[str, Any],
    asset_mappings: list[Dict[str, str]],
) -> Dict[str, Any]:
    sources: Dict[str, Any] = {}
    for role, values in options.items():
        if values:
            sources[f"rules.{role}"] = {
                "source": "ai_scan",
                "evidence_fields": sorted(option_sources[role]),
                "suggestion": values,
                "modified": False,
            }
    if targets:
        sources["rules.text_targets"] = {
            "source": "ai_object_name",
            "suggestion": deepcopy(targets),
            "modified": False,
        }
    if dimensions:
        sources["rules.dimensions"] = {
            "source": "ai_visible_bounds",
            "suggestion": deepcopy(dict(dimensions)),
            "modified": False,
        }
    if asset_mappings:
        sources["rules.asset_mappings"] = {
            "source": "independent_design_group",
            "suggestion": deepcopy(asset_mappings),
            "modified": False,
        }
    return sources


def _template_id(scan: Mapping[str, Any]) -> str:
    source = str(_dict(scan.get("document")).get("source_ai") or "")
    return Path(source).stem

def _range_name(values: list[str]) -> str:
    return values[0] if len(values) == 1 else f"{values[0]}-{values[-1]}"

def _is_library_option(item: Mapping[str, Any], value: str) -> bool:
    if not LIBRARY_OPTION_RE.fullmatch(value):
        return False
    path = str(item.get("path") or "").upper()
    return any(token in path for token in ("ICON_LIBRARY", "DESIGN_LIBRARY", "PATTERN_LIBRARY"))

def _is_trusted_item(item: Mapping[str, Any]) -> bool:
    return item.get("hidden") is not True and item.get("locked") is not True


def _is_design_font_asset_group(item: Mapping[str, Any]) -> bool:
    role = str(item.get("source_role") or "")
    return "独立设计字体" in role and str(item.get("type") or "") == "GroupItem"


def _is_legacy_design_asset_group(item: Mapping[str, Any]) -> bool:
    role = str(item.get("source_role") or "")
    return role == "独立设计模板" and str(item.get("type") or "") == "GroupItem"


def _is_independent_design_resource_group(item: Mapping[str, Any]) -> bool:
    role = str(item.get("source_role") or "")
    return role == "独立设计资源" and str(item.get("type") or "") == "GroupItem"

def _option_prefix(value: str) -> str:
    lower = value.lower()
    if lower == "style":
        return "Style"
    if lower == "design":
        return "Design"
    return value.upper()

def _option_role(prefix: str) -> str:
    if prefix == "F":
        return "font_options"
    if prefix == "Style":
        return "style_options"
    return "design_options"

def _numbered_sort_key(value: str) -> tuple[str, int]:
    match = re.search(r"(\d+)$", value)
    return (re.sub(r"\d+$", "", value), int(match.group(1)) if match else 0)

def _dict(value: Any) -> Dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def _dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]
