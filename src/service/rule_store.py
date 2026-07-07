"""Read and write business rule configurations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from ..jjmb_202508_main import DEPARTMENT_RULES_PATH
from .paths import CONFIG_DIR


FIELD_ALIASES = {
    "订单号": "order_no",
    "内部订单号": "order_no",
    "字体颜色": "color_option",
    "颜色": "color_option",
    "定制信息": "text",
    "名字": "text",
    "文本": "text",
    "产品名称": "product_name",
    "产品中文名称": "product_name",
    "商品名称": "product_name",
    "order_no": "order_no",
    "color_option": "color_option",
    "text": "text",
    "product_name": "product_name",
}


class DepartmentRuleStore:
    def __init__(
        self,
        rules_path: Path | str = DEPARTMENT_RULES_PATH,
        drafts_path: Path | str = CONFIG_DIR / "department_rule_drafts.json",
    ) -> None:
        self.rules_path = Path(rules_path)
        self.drafts_path = Path(drafts_path)

    def read(self) -> Dict[str, Any]:
        payload = self._read_rules_file()
        payload["drafts"] = self._read_drafts_file().get("drafts", [])
        return payload

    def save_draft(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        draft = normalize_department_rule(payload, draft=True)
        raw = self._read_drafts_file()
        drafts = [item for item in raw.get("drafts", []) if item.get("rule_name") != draft["rule_name"]]
        drafts.append(draft)
        raw["version"] = int(raw.get("version", 1) or 1)
        raw["drafts"] = drafts
        self.drafts_path.parent.mkdir(parents=True, exist_ok=True)
        self.drafts_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "drafts": len(drafts), "draft": draft}

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rule = normalize_department_rule(payload, draft=False)
        raw = self._read_rules_file()
        rules = [item for item in raw.get("rules", []) if item.get("name") != rule["name"]]
        rules.append(rule)
        raw["version"] = int(raw.get("version", 1) or 1)
        raw["rules"] = rules
        self.rules_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "rule": rule, "rules": len(rules)}

    def build_draft_from_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        seed = normalize_department_rule(payload, draft=True, require_name=False)
        text = str(payload.get("natural_text", "") or "").strip()
        if text:
            inferred = infer_department_rule_from_text(text)
            for key, value in inferred.items():
                if value not in ("", [], None):
                    if key in {"show_frame", "apply_color_to_artwork"}:
                        seed[key] = bool(value)
                    elif not seed.get(key):
                        seed[key] = value
            seed["natural_text"] = text
        return seed

    def _read_rules_file(self) -> Dict[str, Any]:
        if not self.rules_path.exists():
            return {"version": 1, "default": {}, "shop_rules": {}, "rules": []}
        return json.loads(self.rules_path.read_text(encoding="utf-8"))

    def _read_drafts_file(self) -> Dict[str, Any]:
        if not self.drafts_path.exists():
            return {"version": 1, "drafts": []}
        return json.loads(self.drafts_path.read_text(encoding="utf-8"))


def normalize_department_rule(
    payload: Dict[str, Any],
    *,
    draft: bool,
    require_name: bool = True,
) -> Dict[str, Any]:
    rule_name = str(payload.get("rule_name") or payload.get("name") or "").strip()
    if require_name and not rule_name:
        raise ValueError("缺少规则名称")
    departments = _to_string_list(payload.get("departments", []))
    label_fields = normalize_label_fields(payload.get("label_fields", []))
    normalized: Dict[str, Any] = {
        "display_name": str(payload.get("display_name", "") or "").strip(),
        "departments": departments,
        "match": str(payload.get("match", "exact") or "exact").strip() or "exact",
        "label_fields": label_fields,
        "label_lines": normalize_label_lines(payload.get("label_lines", []), label_fields),
        "apply_color_to_artwork": _to_bool(payload.get("apply_color_to_artwork", False)),
        "show_frame": _to_bool(payload.get("show_frame", False)),
        "description": str(payload.get("description", "") or "").strip(),
        "natural_text": str(payload.get("natural_text", "") or "").strip(),
    }
    if draft:
        normalized["rule_name"] = rule_name
        normalized["preview"] = str(payload.get("preview", "") or "").strip()
    else:
        normalized["name"] = rule_name
    return normalized


def infer_department_rule_from_text(text: str) -> Dict[str, Any]:
    departments = infer_departments(text)
    label_fields = infer_label_fields(text)
    return {
        "rule_name": "_".join(departments) if departments else "",
        "display_name": "/".join(departments) + " 部门" if departments else "",
        "departments": departments,
        "match": "contains" if "包含" in text or "含" in text else "exact",
        "label_fields": label_fields,
        "label_lines": [[field] for field in label_fields],
        "show_frame": "不带框" not in text and any(token in text for token in ["带框", "输出框", "作图框"]),
        "apply_color_to_artwork": any(token in text for token in ["效果图应用颜色", "颜色填充", "字体颜色填充", "按字体颜色渲染"]),
        "description": text,
        "natural_text": text,
    }


def infer_departments(text: str) -> List[str]:
    candidates: List[str] = []
    for match in re.finditer(r"([A-Z]{1,3}(?:\s*[/、,，]\s*[A-Z]{1,3})*)\s*部门", text):
        candidates.extend(_to_string_list(match.group(1)))
    if not candidates:
        for match in re.finditer(r"\b[A-Z]{1,3}\b", text):
            value = match.group(0)
            if value not in {"AI", "JSON", "PNG", "JPG"}:
                candidates.append(value)
    return _dedupe(candidates)


def infer_label_fields(text: str) -> List[str]:
    fields = []
    for label, field in FIELD_ALIASES.items():
        if label in text:
            fields.append(field)
    return _dedupe(fields) or ["order_no", "text"]


def normalize_label_fields(value: Any) -> List[str]:
    fields = []
    for item in _to_string_list(value):
        fields.append(FIELD_ALIASES.get(item, item))
    return _dedupe(fields)


def normalize_label_lines(value: Any, fallback: List[str]) -> List[List[str]]:
    if isinstance(value, list):
        lines: List[List[str]] = []
        for item in value:
            line = normalize_label_fields(item)
            if line:
                lines.append(line)
        if lines:
            return lines
    return [[field] for field in fallback]


def _to_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        items: List[str] = []
        for item in value:
            if isinstance(item, list):
                items.extend(_to_string_list(item))
            else:
                text = str(item).strip()
                if text:
                    items.append(text)
        return items
    text = str(value or "").strip()
    if not text:
        return []
    for delimiter in ["，", "、", "/", "|", ";", "；"]:
        text = text.replace(delimiter, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    if text in {"0", "false", "no", "off", "否"}:
        return False
    return bool(value)


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
