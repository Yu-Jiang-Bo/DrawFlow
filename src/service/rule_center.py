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
    style_options = parse_numbered_options(raw, "Style", "style")
    design_options = parse_design_options(raw)
    defaults = infer_defaults(raw)
    slots = infer_slots(mode, raw, capabilities, defaults)

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
        "defaults": defaults,
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
        if not config.get("design_options"):
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
    return payload if isinstance(payload, dict) else {}


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
        slots.append({"name": "Name", "type": "text_fit_box", "source": "names"})
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


def parse_design_options(text: str) -> List[str]:
    options = set()
    for start, end in re.findall(r"(?:D|Design)\s*(\d+)\s*(?:-|~|到|至)\s*(?:D|Design)?\s*(\d+)", text, re.I):
        for index in range(int(start), int(end) + 1):
            options.add(f"D{index}")
    for value in re.findall(r"(?:D|Design)\s*(\d+)", text, re.I):
        options.add(f"D{int(value)}")
    return sorted(options, key=lambda value: int(value[1:]))


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
    match = re.search(r"(?:默认|default).*?(?:D|Design)\s*(\d+)", text, re.I)
    if not match:
        match = re.search(r"(?:D|Design)\s*(\d+)", text, re.I)
    return f"D{int(match.group(1))}" if match else ""


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
