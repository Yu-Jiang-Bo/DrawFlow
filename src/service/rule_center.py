"""Template rule draft parsing and readiness checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


MODE_BY_TEMPLATE_TYPE = {
    "pure_text": "pure_text",
    "pure_text_color_design": "pure_text",
    "pure_text_style": "pure_text",
    "curved_title_text": "annotated_ai",
    "annotated_ai": "annotated_ai",
    "asset_split": "asset_split",
}

LEGACY_RENDERABLE_PIPELINES = {
    "jjmb_202508",
    "jjmb_202603_grouped",
    "jjmb_202509_curved",
}

PIPELINE_CONFIG_REQUIRED = {
    "jjmb_202508": False,
    "jjmb_202603_grouped": True,
    "jjmb_202509_curved": True,
}

DEFAULT_OUTPUT_COLOR_MODE = "CMYK"
OUTPUT_COLOR_MODES = {"CMYK", "RGB"}

DIMENSION_PAIR_RE = re.compile(
    r"(?P<width>\d+(?:\.\d+)?)\s*(?P<width_unit>mm|cm|\u6beb\u7c73|\u5398\u7c73)?"
    r"\s*(?:\*|x|X|\u00d7|\uff0a)\s*"
    r"(?P<height>\d+(?:\.\d+)?)\s*(?P<height_unit>mm|cm|\u6beb\u7c73|\u5398\u7c73)?",
    re.I,
)

DIMENSION_TARGETS = {
    "title": ("title", "\u6807\u9898", "\u5f2f\u66f2"),
    "name": (
        "name",
        "name_content",
        "text_box",
        "\u540d\u5b57",
        "\u59d3\u540d",
        "\u6587\u5b57",
        "\u6587\u5b57\u533a\u57df",
        "\u5b9a\u5236\u533a\u57df",
    ),
}

UNIT_TO_MM = {
    "mm": 1.0,
    "\u6beb\u7c73": 1.0,
    "cm": 10.0,
    "\u5398\u7c73": 10.0,
}


def build_template_rule_draft(
    template_id: str,
    template_type: str,
    natural_text: str,
    asset_count: int = 0,
) -> Dict[str, Any]:
    """Build a deterministic structured draft from business-language rules."""

    raw = (natural_text or "").strip()
    mode = infer_mode(template_type, raw, asset_count)
    capabilities = infer_capabilities(mode, raw, asset_count)
    font_options = parse_numbered_options(raw, "F", "font")
    design_options = parse_design_options(raw)
    design_font_options = parse_design_font_options(raw)
    style_options = parse_style_options(raw, template_type, design_options)
    defaults = infer_defaults(raw)
    slots = infer_slots(mode, raw, capabilities, defaults)
    dimensions = parse_dimensions(raw)
    output = infer_output_settings(raw)
    transforms = infer_transforms(raw)

    return {
        "version": 1,
        "template_id": template_id,
        "mode": mode,
        "status": "draft",
        "rule_source": "natural_language",
        "raw_text": raw,
        "capabilities": capabilities,
        "font_options": font_options,
        "style_options": style_options,
        "design_options": design_options,
        "design_font_options": design_font_options,
        "defaults": defaults,
        "transforms": transforms,
        "dimensions": dimensions,
        "output": output,
        "slots": slots,
        "assets": {
            "mode": "split_ai" if mode == "asset_split" else "inline",
            "count": asset_count,
        },
    }


def check_template_definition(template: Any) -> Dict[str, Any]:
    """Return rule completeness and renderability for a template definition."""

    config = read_template_rule_config(
        getattr(template, "template_rules_config", None) or getattr(template, "template_config", None)
    )
    template_type = str(getattr(template, "template_type", "") or "")
    pipeline = str(getattr(template, "pipeline", "") or "")
    mode = str(config.get("mode") or MODE_BY_TEMPLATE_TYPE.get(template_type, template_type or "unknown"))
    capabilities = _string_list(config.get("capabilities", []))
    slots = config.get("slots", []) if isinstance(config.get("slots", []), list) else []
    assets = getattr(template, "assets", []) or []

    missing: List[Dict[str, str]] = []
    warnings: List[str] = []
    template_ai = getattr(template, "template_ai", None)
    template_config = getattr(template, "template_config", None)

    has_template_ai = bool(template_ai) and Path(template_ai).exists()
    if not has_template_ai:
        missing.append({"code": "template_ai", "message": "缺少可用的 .ai 模板文件"})

    if pipeline == "generic_rules_only":
        if config.get("status") != "confirmed":
            missing.append({"code": "rule_status", "message": "Template rules are not confirmed."})
        if not isinstance(config.get("order_bindings"), dict) or not config.get("order_bindings"):
            missing.append({"code": "order_bindings", "message": "Missing order field bindings."})
        if not config.get("slot_mappings") and not config.get("text_targets"):
            missing.append({"code": "text_targets", "message": "Missing executable text target mappings."})
        missing.extend(_generic_asset_issues(config, assets))
        complete = not missing
        return {
            "template_id": str(getattr(template, "template_id", "")),
            "mode": mode,
            "status": str(config.get("status") or getattr(template, "status", "draft")),
            "complete": complete,
            "renderable": complete and getattr(template, "status", "draft") == "active",
            "missing": missing,
            "warnings": warnings,
            "capabilities": capabilities,
        }

    if mode in {"pure_text", "annotated_ai"} and not config.get("font_options"):
        missing.append({"code": "font_options", "message": "缺少字体选项规则，例如 F1-F9 或 F1-F14"})

    if mode == "pure_text" and not _has_slot(slots, "text_fit_box"):
        missing.append({"code": "text_slot", "message": "缺少普通文字作图区规则 text_fit_box"})

    if mode == "annotated_ai":
        if "text_on_curve" in capabilities and not _has_slot(slots, "text_on_curve"):
            missing.append({"code": "curve_title_slot", "message": "缺少曲线标题槽位 text_on_curve"})
        if not config and pipeline not in LEGACY_RENDERABLE_PIPELINES:
            missing.append({"code": "template_config", "message": "缺少模板结构配置 template.config.json"})

    if mode == "asset_split":
        if not assets:
            missing.append({"code": "design_assets", "message": "缺少独立设计资产，例如 assets/D1.ai"})
        if not config.get("design_options") and not config.get("design_font_options"):
            missing.append({"code": "design_options", "message": "缺少设计选项规则，例如 D1-D12"})
        if not _has_capability(capabilities, "place_ai_asset"):
            missing.append({"code": "place_ai_asset", "message": "缺少放置独立设计资产的能力声明"})

    config_required = PIPELINE_CONFIG_REQUIRED.get(pipeline, False)
    legacy_pipeline_ready = pipeline in LEGACY_RENDERABLE_PIPELINES and has_template_ai
    if legacy_pipeline_ready:
        if config_required and (not template_config or not Path(template_config).exists()):
            legacy_pipeline_ready = False
        else:
            warnings.append("当前模板仍使用已验证的专用 pipeline，后续应迁移到通用能力模块")

    complete = not missing
    renderable = complete or legacy_pipeline_ready
    return {
        "template_id": str(getattr(template, "template_id", "")),
        "mode": mode,
        "status": str(config.get("status") or getattr(template, "status", "draft")),
        "complete": complete,
        "renderable": renderable,
        "missing": missing,
        "warnings": warnings,
        "capabilities": capabilities,
    }


def read_template_rule_config(path_value: object) -> Dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("$schema") == "custom-renderer/template-rule-pack" and isinstance(payload.get("rules"), dict):
        rules = dict(payload["rules"])
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        rules["status"] = validation.get("status", "draft")
        rules["capabilities"] = payload.get("capabilities", [])
        rules["assets"] = payload.get("assets", {})
        return rules
    return payload


def _generic_asset_issues(config: Dict[str, Any], assets: Any) -> List[Dict[str, str]]:
    mappings = config.get("asset_mappings", [])
    if not isinstance(mappings, list) or not mappings:
        return []
    catalog: Dict[str, Path] = {}
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict):
            continue
        path = Path(str(asset.get("stored_path") or ""))
        if not path.is_absolute():
            path = (Path(__file__).resolve().parents[2] / path).resolve()
        for key in ("file_name", "stored_path"):
            value = str(asset.get(key) or "")
            if value:
                catalog[value] = path
    issues = []
    for mapping in mappings:
        name = str(mapping.get("asset") or "") if isinstance(mapping, dict) else ""
        path = catalog.get(name) or next(
            (item for value, item in catalog.items() if value.endswith("/" + name)),
            None,
        )
        if path is None or not path.exists():
            issues.append({"code": "asset_file", "message": f"Mapped asset is unavailable: {name}"})
    return issues


def parse_dimensions(text: str) -> Dict[str, Dict[str, object]]:
    """Parse business-language size rules into millimeter dimensions."""

    result: Dict[str, Dict[str, object]] = {}
    for segment in re.split(r"[\r\n,，;；。]+", text or ""):
        target = _dimension_target(segment)
        if not target:
            continue
        match = DIMENSION_PAIR_RE.search(segment)
        if not match:
            continue
        width_unit = _normalize_unit(match.group("width_unit"))
        height_unit = _normalize_unit(match.group("height_unit"))
        fallback_unit = height_unit or width_unit or _unit_hint(segment) or "cm"
        width_mm = _dimension_value_to_mm(match.group("width"), width_unit or fallback_unit)
        height_mm = _dimension_value_to_mm(match.group("height"), height_unit or fallback_unit)
        if width_mm <= 0 or height_mm <= 0:
            continue
        result[target] = {
            "width_mm": round(width_mm, 3),
            "height_mm": round(height_mm, 3),
            "source": segment.strip(),
        }
    return result


def curved_layout_overrides(config: Dict[str, Any]) -> Dict[str, float]:
    """Return JJMB202509 curved-title layout overrides from template rules."""

    dimensions = config.get("dimensions")
    if not isinstance(dimensions, dict):
        dimensions = {}
    if not dimensions and isinstance(config.get("raw_text"), str):
        dimensions = parse_dimensions(config["raw_text"])

    result: Dict[str, float] = {}
    for target in ("name", "title"):
        dimension = _dimension_entry(dimensions, target)
        if not dimension:
            continue
        width = _positive_float(dimension.get("width_mm"))
        height = _positive_float(dimension.get("height_mm"))
        if width:
            result[f"{target}_width_mm"] = width
        if height:
            result[f"{target}_height_mm"] = height
    return result


def infer_output_settings(text: str) -> Dict[str, str]:
    return {"color_mode": infer_output_color_mode(text) or DEFAULT_OUTPUT_COLOR_MODE}


def infer_output_color_mode(text: str) -> str:
    upper = (text or "").upper()
    if "RGB" in upper:
        return "RGB"
    if "CMYK" in upper:
        return "CMYK"
    return ""


def output_color_mode(config: Dict[str, Any], default: str = DEFAULT_OUTPUT_COLOR_MODE) -> str:
    output = config.get("output")
    if isinstance(output, dict):
        mode = _normalize_output_color_mode(output.get("color_mode"))
        if mode:
            return mode
    mode = _normalize_output_color_mode(config.get("output_color_mode"))
    if mode:
        return mode
    if isinstance(config.get("raw_text"), str):
        mode = infer_output_color_mode(config["raw_text"])
        if mode:
            return mode
    return _normalize_output_color_mode(default) or DEFAULT_OUTPUT_COLOR_MODE


def infer_mode(template_type: str, text: str, asset_count: int = 0) -> str:
    lower = text.lower()
    if asset_count > 0 or any(token in lower for token in ["asset", "d1.ai", "d2.ai", "拆分", "独立设计"]):
        return "asset_split"
    if any(token in lower for token in ["curve", "curved", "path", "弯曲", "曲线", "标题"]):
        return "annotated_ai"
    return MODE_BY_TEMPLATE_TYPE.get(template_type, "pure_text")


def infer_capabilities(mode: str, text: str, asset_count: int = 0) -> List[str]:
    lower = text.lower()
    capabilities = set()
    if mode in {"pure_text", "annotated_ai"}:
        capabilities.add("text_fit_box")
    if mode == "annotated_ai" or any(token in lower for token in ["curve", "curved", "弯曲", "曲线", "标题"]):
        capabilities.add("text_on_curve")
    if mode == "asset_split" or asset_count > 0:
        capabilities.update({"place_ai_asset", "replace_text", "scale_to_box"})
    if any(token in lower for token in ["照片", "photo", "image", "图片"]):
        capabilities.add("image_slot")
    capabilities.update({"outline_dedupe", "export_ai8"})
    return sorted(capabilities)


def infer_defaults(text: str) -> Dict[str, str]:
    return {
        "color": infer_color(text),
        "design": infer_design(text),
        "font": infer_font(text),
        "title": infer_title(text),
    }


def infer_slots(
    mode: str,
    text: str,
    capabilities: Iterable[str],
    defaults: Dict[str, str],
) -> List[Dict[str, Any]]:
    lower = text.lower()
    slots: List[Dict[str, Any]] = []
    if "text_fit_box" in capabilities:
        slot: Dict[str, Any] = {"name": "Name", "type": "text_fit_box", "source": "names"}
        if "text_box" in lower:
            slot["box"] = "text_box"
        if "design" in lower:
            slot["scope"] = "Design group"
        if "text" in lower:
            slot["content"] = "text"
        slots.append(slot)
    if "text_on_curve" in capabilities:
        slots.append(
            {
                "name": "Title",
                "type": "text_on_curve",
                "source": "title",
                "default": defaults.get("title") or "Merry Christmas",
            }
        )
    if mode == "asset_split" or "text1" in lower or "text2" in lower:
        slots.append({"name": "DesignAsset", "type": "place_ai_asset", "source": "design"})
        slots.append({"name": "Text1", "type": "replace_text", "source": "variables.Text1"})
    return slots


def parse_numbered_options(text: str, prefix: str, kind: str) -> List[str]:
    options = set()
    escaped = re.escape(prefix)
    for start, end in re.findall(rf"{escaped}\s*(\d+)\s*(?:-|~|到|至)\s*{escaped}?\s*(\d+)", text, re.I):
        for index in range(int(start), int(end) + 1):
            options.add(f"{prefix}{index}")
    for value in re.findall(rf"{escaped}\s*(\d+)", text, re.I):
        options.add(f"{prefix}{int(value)}")
    if kind == "style":
        return sorted(options, key=lambda value: int(re.search(r"\d+", value).group(0)))  # type: ignore[union-attr]
    return sorted(options, key=lambda value: int(re.search(r"\d+", value).group(0)))  # type: ignore[union-attr]


def parse_style_options(text: str, template_type: str, design_options: List[str]) -> List[str]:
    styles = parse_numbered_options(text, "Style", "style")
    if styles:
        return styles
    lower = (text or "").lower()
    design_is_size_box = (
        template_type == "pure_text_color_design"
        and design_options
        and any(token in lower for token in ["text_box", "尺寸", "作图区", "作图框", "款式", "设计款式"])
    )
    return design_options if design_is_size_box else []


def parse_design_options(text: str) -> List[str]:
    options = set()
    range_re = re.compile(
        r"(?P<prefix>Design|D)\s*(?P<start>\d+)\s*(?:-|~|到|至)\s*(?P<end_prefix>Design|D)?\s*(?P<end>\d+)",
        re.I,
    )
    single_re = re.compile(r"(?P<prefix>Design|D)\s*(?P<value>\d+)", re.I)
    for match in range_re.finditer(text or ""):
        prefix = _design_prefix(match.group("prefix"), match.group("end_prefix"))
        start = int(match.group("start"))
        end = int(match.group("end"))
        for index in range(int(start), int(end) + 1):
            options.add(f"{prefix}{index}")
    for match in single_re.finditer(text or ""):
        options.add(f"{_design_prefix(match.group('prefix'))}{int(match.group('value'))}")
    return sorted(options, key=_design_sort_key)


def parse_design_font_options(text: str) -> List[str]:
    options = set()
    for segment in re.split(r"[\r\n,，;；。]+", text or ""):
        lower = segment.lower()
        if "设计" not in segment and "design" not in lower and "asset" not in lower:
            continue
        options.update(parse_numbered_options(segment, "F", "font"))
    return sorted(options, key=_design_sort_key)


def infer_color(text: str) -> str:
    color_map = [
        ("Rose Gold", ["rose gold", "玫瑰金"]),
        ("Gold", ["gold", "金色"]),
        ("Black", ["black", "黑色"]),
        ("White", ["white", "白色"]),
        ("Silver", ["silver", "银色"]),
        ("Red", ["red", "红色"]),
        ("Blue", ["blue", "蓝色"]),
    ]
    lower = text.lower()
    for color, tokens in color_map:
        if any(token.lower() in lower for token in tokens):
            return color
    return ""


def infer_design(text: str) -> str:
    match = re.search(r"(?:默认|default).*?(?P<prefix>Design|D)\s*(?P<value>\d+)", text, re.I)
    if not match:
        match = re.search(r"(?P<prefix>Design|D)\s*(?P<value>\d+)", text, re.I)
    return f"{_design_prefix(match.group('prefix'))}{int(match.group('value'))}" if match else ""


def infer_transforms(text: str) -> Dict[str, Dict[str, object]]:
    transforms: Dict[str, Dict[str, object]] = {}
    rotation_re = re.compile(
        r"(?P<prefix>Design|D)\s*(?P<value>\d+)(?P<body>[^。；;,\n]{0,80}?)旋转\s*(?P<degree>-?\d+(?:\.\d+)?)\s*(?:°|度)?",
        re.I,
    )
    for match in rotation_re.finditer(text or ""):
        option = f"{_design_prefix(match.group('prefix'))}{int(match.group('value'))}"
        degree = float(match.group("degree"))
        body = match.group("body") or ""
        direction = "逆时针" if "逆时针" in body else "顺时针" if "顺时针" in body else ""
        if direction == "逆时针":
            degree = -abs(degree)
        elif direction == "顺时针":
            degree = abs(degree)
        transforms[option] = {
            "rotation_deg": degree,
            "source": match.group(0).strip(),
        }
    return transforms


def infer_font(text: str) -> str:
    match = re.search(r"(?:默认|default).*?F\s*(\d+)", text, re.I)
    return f"F{int(match.group(1))}" if match else ""


def infer_title(text: str) -> str:
    patterns = [
        r"Title[^。；;\n]*?[默认|default|为|是]\s*[\"“']([^\"”']+)[\"”']",
        r"默认(?:标题|Title)?\s*[为是:：]\s*[\"“']([^\"”']+)[\"”']",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    if "Merry Christmas" in text:
        return "Merry Christmas"
    return ""


def _design_prefix(*values: object) -> str:
    for value in values:
        if str(value or "").strip().lower() == "design":
            return "Design"
    return "D"


def _design_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"\d+", value)
    return (int(match.group(0)) if match else 0, value)


def _has_slot(slots: List[object], slot_type: str) -> bool:
    for slot in slots:
        if isinstance(slot, dict) and slot.get("type") == slot_type:
            return True
    return False


def _has_capability(capabilities: Iterable[str], name: str) -> bool:
    return name in set(capabilities)


def _string_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dimension_target(segment: str) -> str:
    lower = (segment or "").lower()
    for target, tokens in DIMENSION_TARGETS.items():
        if any(token in lower for token in tokens):
            return target
    return ""


def _normalize_unit(value: object) -> str:
    unit = str(value or "").strip().lower()
    return unit if unit in UNIT_TO_MM else ""


def _unit_hint(segment: str) -> str:
    lower = (segment or "").lower()
    if "\u6beb\u7c73" in lower or "mm" in lower:
        return "mm"
    if "\u5398\u7c73" in lower or "cm" in lower:
        return "cm"
    return ""


def _dimension_value_to_mm(value: object, unit: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number * UNIT_TO_MM.get(unit, 10.0)


def _dimension_entry(dimensions: Dict[str, Any], target: str) -> Dict[str, Any]:
    candidates = [target, target.capitalize(), target.upper()]
    if target == "name":
        candidates.extend(["Name_Content", "NAME_CONTENT"])
    for key in candidates:
        value = dimensions.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _positive_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


def _normalize_output_color_mode(value: object) -> str:
    mode = str(value or "").strip().upper()
    return mode if mode in OUTPUT_COLOR_MODES else ""
