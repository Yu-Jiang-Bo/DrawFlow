"""Template registry backed by config/templates.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .paths import CONFIG_DIR, PROJECT_ROOT, TEMPLATE_STORAGE_DIR


TEMPLATES_CONFIG = CONFIG_DIR / "templates.json"
DEFAULT_PIPELINES = {
    "pure_text_color_design": "jjmb_202508",
    "pure_text_style": "jjmb_202603_grouped",
}


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    name: str
    template_type: str
    pipeline: str
    status: str
    template_ai: Path
    default_columns: int = 4
    default_hide_boxes: bool = True
    template_config: Path | None = None

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "template_type": self.template_type,
            "pipeline": self.pipeline,
            "status": self.status,
            "template_ai": str(self.template_ai),
            "template_config": str(self.template_config) if self.template_config else "",
            "default_columns": self.default_columns,
            "default_hide_boxes": self.default_hide_boxes,
        }


class TemplateRegistry:
    def __init__(
        self,
        config_path: Path | str = TEMPLATES_CONFIG,
        storage_dir: Path | str = TEMPLATE_STORAGE_DIR,
    ) -> None:
        self.config_path = Path(config_path)
        self.storage_dir = Path(storage_dir)

    def list_templates(self) -> List[TemplateDefinition]:
        raw = self._read_config()
        templates = raw.get("templates", [])
        return [self._parse_template(item) for item in templates if isinstance(item, dict)]

    def get_template(self, template_id: str) -> TemplateDefinition:
        for template in self.list_templates():
            if template.template_id == template_id:
                return template
        raise KeyError(f"模板不存在: {template_id}")

    def upsert_template(self, item: Dict[str, Any]) -> TemplateDefinition:
        normalized = self._normalize_template_item(item)
        raw = self._read_config()
        templates = [entry for entry in raw.get("templates", []) if entry.get("template_id") != normalized["template_id"]]
        templates.append(normalized)
        raw["version"] = int(raw.get("version", 1) or 1)
        raw["templates"] = templates
        self._write_config(raw)
        return self.get_template(normalized["template_id"])

    def save_uploaded_ai(self, template_id: str, filename: str, content: bytes) -> Path:
        if not filename.lower().endswith(".ai"):
            raise ValueError("模板文件必须是 .ai 格式")
        if not content:
            raise ValueError("上传的模板文件为空")
        template_dir = self._template_dir(template_id)
        template_dir.mkdir(parents=True, exist_ok=True)
        output_path = template_dir / "template.ai"
        output_path.write_bytes(content)
        return output_path

    def save_template_config(self, template_id: str, content: str) -> Path | None:
        text = content.strip()
        if not text:
            return None
        parsed = json.loads(text)
        template_dir = self._template_dir(template_id)
        template_dir.mkdir(parents=True, exist_ok=True)
        output_path = template_dir / "template.config.json"
        output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    def to_config_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(resolved)

    def _parse_template(self, item: Dict[str, Any]) -> TemplateDefinition:
        return TemplateDefinition(
            template_id=str(item.get("template_id", "")).strip(),
            name=str(item.get("name", "")).strip(),
            template_type=str(item.get("template_type", "")).strip(),
            pipeline=str(item.get("pipeline", "")).strip(),
            status=str(item.get("status", "draft")).strip(),
            template_ai=self._resolve_path(str(item.get("template_ai", "")).strip()),
            default_columns=int(item.get("default_columns", 4) or 4),
            default_hide_boxes=bool(item.get("default_hide_boxes", True)),
            template_config=self._optional_path(item.get("template_config", "")),
        )

    def _optional_path(self, value: object) -> Path | None:
        text = str(value or "").strip()
        return self._resolve_path(text) if text else None

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()

    def _read_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {"version": 1, "templates": []}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _write_config(self, raw: Dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_template_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(item.get("template_id", "")).strip()
        name = str(item.get("name", "")).strip()
        template_type = str(item.get("template_type", "")).strip()
        pipeline = str(item.get("pipeline", "")).strip() or DEFAULT_PIPELINES.get(template_type, "")
        status = str(item.get("status", "draft")).strip() or "draft"
        template_ai = str(item.get("template_ai", "")).strip()
        if not template_id:
            raise ValueError("缺少 template_id")
        if not name:
            raise ValueError("缺少模板名称")
        if not template_type:
            raise ValueError("缺少模板类型")
        if not pipeline:
            raise ValueError("无法根据模板类型推断渲染流程，请检查模板类型")
        if not template_ai:
            raise ValueError("缺少模板 AI 文件")
        normalized: Dict[str, Any] = {
            "template_id": template_id,
            "name": name,
            "template_type": template_type,
            "pipeline": pipeline,
            "status": status,
            "template_ai": template_ai,
            "default_columns": int(item.get("default_columns", 4) or 4),
            "default_hide_boxes": _to_bool(item.get("default_hide_boxes", True)),
        }
        template_config = str(item.get("template_config", "")).strip()
        if template_config:
            normalized["template_config"] = template_config
        return normalized

    def _template_dir(self, template_id: str) -> Path:
        safe_id = _safe_segment(template_id)
        if not safe_id:
            raise ValueError("模板 ID 不合法")
        return self.storage_dir / safe_id


def _safe_segment(value: str) -> str:
    chars = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
    return "".join(chars)


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "否"}:
        return False
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    return bool(value)
