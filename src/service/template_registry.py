"""Template registry backed by config/templates.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .paths import CONFIG_DIR, PROJECT_ROOT


TEMPLATES_CONFIG = CONFIG_DIR / "templates.json"


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
    def __init__(self, config_path: Path | str = TEMPLATES_CONFIG) -> None:
        self.config_path = Path(config_path)

    def list_templates(self) -> List[TemplateDefinition]:
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        templates = raw.get("templates", [])
        return [self._parse_template(item) for item in templates if isinstance(item, dict)]

    def get_template(self, template_id: str) -> TemplateDefinition:
        for template in self.list_templates():
            if template.template_id == template_id:
                return template
        raise KeyError(f"模板不存在: {template_id}")

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
