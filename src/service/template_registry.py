"""Template registry backed by config/templates.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List

from .paths import CONFIG_DIR, PROJECT_ROOT, TEMPLATE_STORAGE_DIR
from .template_locks import TEMPLATE_STATE_LOCK
from .template_rule_pack import strip_template_output_text_flags


TEMPLATES_CONFIG = CONFIG_DIR / "templates.json"
DEFAULT_PIPELINES = {
    "pure_text": "generic_rules_only",
    "pure_text_color_design": "jjmb_202508",
    "pure_text_style": "jjmb_202603_grouped",
    "curved_title_text": "jjmb_202509_curved",
    "annotated_ai": "generic_rules_only",
    "asset_split": "generic_rules_only",
}
_REGISTRY_LOCK = TEMPLATE_STATE_LOCK


def _registry_locked(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        with _REGISTRY_LOCK:
            return method(*args, **kwargs)

    return wrapped


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    name: str
    template_type: str
    pipeline: str
    status: str
    template_ai: Path | None
    template_ai_role: str = "尺寸/作图区模板"
    default_columns: int = 4
    default_hide_boxes: bool = True
    template_config: Path | None = None
    template_rules_config: Path | None = None
    assets: List[Dict[str, Any]] = field(default_factory=list)

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "template_type": self.template_type,
            "pipeline": self.pipeline,
            "status": self.status,
            "template_ai": str(self.template_ai) if self.template_ai else "",
            "template_ai_role": self.template_ai_role,
            "template_config": str(self.template_config) if self.template_config else "",
            "template_rules_config": str(self.template_rules_config) if self.template_rules_config else "",
            "default_columns": self.default_columns,
            "default_hide_boxes": self.default_hide_boxes,
            "assets": self.assets,
        }


class TemplateRegistry:
    def __init__(
        self,
        config_path: Path | str = TEMPLATES_CONFIG,
        storage_dir: Path | str = TEMPLATE_STORAGE_DIR,
    ) -> None:
        self.config_path = Path(config_path)
        self.storage_dir = Path(storage_dir)

    @_registry_locked
    def list_templates(self) -> List[TemplateDefinition]:
        raw = self._read_config()
        templates = raw.get("templates", [])
        return [self._parse_template(item) for item in templates if isinstance(item, dict)]

    @_registry_locked
    def get_template(self, template_id: str) -> TemplateDefinition:
        for template in self.list_templates():
            if template.template_id == template_id:
                return template
        raise KeyError(f"模板不存在: {template_id}")

    @_registry_locked
    def validate_template_id(self, template_id: str) -> None:
        candidate_id = str(template_id or "").strip()
        if not candidate_id or _safe_segment(candidate_id) != candidate_id:
            raise ValueError("template_id may only contain letters, numbers, '-' and '_'.")
        for existing in self._read_config().get("templates", []):
            existing_id = str(existing.get("template_id", "")).strip()
            if existing_id.casefold() == candidate_id.casefold() and existing_id != candidate_id:
                raise ValueError(f"Template ID differs only by case from existing template: {existing_id}")

    @_registry_locked
    def upsert_template(self, item: Dict[str, Any]) -> TemplateDefinition:
        self.validate_template_id(str(item.get("template_id", "")))
        normalized = self._normalize_template_item(item)
        raw = self._read_config()
        templates = [entry for entry in raw.get("templates", []) if entry.get("template_id") != normalized["template_id"]]
        templates.append(normalized)
        raw["version"] = int(raw.get("version", 1) or 1)
        raw["templates"] = templates
        self._write_config(raw)
        return self.get_template(normalized["template_id"])

    @_registry_locked
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

    @_registry_locked
    def save_uploaded_assets(
        self,
        template_id: str,
        uploads: List[Dict[str, object]],
        role: str = "附加模板",
    ) -> List[Dict[str, Any]]:
        if not uploads:
            return []
        asset_dir = self._template_dir(template_id) / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        saved: List[Dict[str, Any]] = []
        for upload in uploads:
            filename = str(upload.get("filename", "")).strip()
            content = upload.get("content", b"")
            if not filename.lower().endswith(".ai"):
                raise ValueError("附加模板资产必须是 .ai 格式")
            if not isinstance(content, bytes) or not content:
                raise ValueError(f"附加模板资产为空: {filename}")
            output_path = _unique_path(asset_dir, _safe_filename(filename))
            output_path.write_bytes(content)
            saved.append(
                {
                    "file_name": Path(filename).name,
                    "stored_path": self.to_config_path(output_path),
                    "asset_type": "ai_template",
                    "role": role.strip() or "附加模板",
                    "status": "uploaded",
                    "size_bytes": len(content),
                }
            )
        return saved

    @_registry_locked
    def delete_template_asset(self, template_id: str, asset_index: int) -> Dict[str, Any]:
        raw = self._read_config()
        templates = raw.get("templates", [])
        for item in templates:
            if item.get("template_id") != template_id:
                continue
            assets = item.get("assets", [])
            if not isinstance(assets, list):
                assets = []
                item["assets"] = assets
            if asset_index < 0 or asset_index >= len(assets):
                raise IndexError("模板 AI 资产不存在")
            removed = assets.pop(asset_index)
            item["status"] = "draft"
            raw["version"] = int(raw.get("version", 1) or 1)
            self._write_config(raw)
            return removed if isinstance(removed, dict) else {"value": removed}
        raise KeyError(f"模板不存在: {template_id}")

    @_registry_locked
    def delete_template_ai(self, template_id: str) -> Dict[str, Any]:
        raw = self._read_config()
        templates = raw.get("templates", [])
        for item in templates:
            if item.get("template_id") != template_id:
                continue
            template_ai = str(item.get("template_ai", "")).strip()
            if not template_ai:
                raise IndexError("模板 AI 文件不存在")
            role = str(item.get("template_ai_role", "尺寸/作图区模板") or "尺寸/作图区模板").strip()
            item["template_ai"] = ""
            item["template_ai_role"] = ""
            item["status"] = "draft"
            raw["version"] = int(raw.get("version", 1) or 1)
            self._write_config(raw)
            return {
                "file_name": Path(template_ai).name,
                "stored_path": template_ai,
                "asset_type": "ai_template",
                "role": role,
                "status": "removed",
            }
        raise KeyError(f"模板不存在: {template_id}")

    @_registry_locked
    def set_template_status(self, template_id: str, status: str) -> TemplateDefinition:
        raw = self._read_config()
        for item in raw.get("templates", []):
            if item.get("template_id") == template_id:
                item["status"] = str(status or "draft").strip()
                self._write_config(raw)
                return self.get_template(template_id)
        raise KeyError(f"Template does not exist: {template_id}")

    @_registry_locked
    def remove_template_record(self, template_id: str) -> Dict[str, Any]:
        """Remove registry metadata while retaining all files for recovery."""

        raw = self._read_config()
        templates = raw.get("templates", [])
        for index, item in enumerate(templates):
            if item.get("template_id") == template_id:
                removed = templates.pop(index)
                self._write_config(raw)
                return removed
        raise KeyError(f"Template does not exist: {template_id}")

    @_registry_locked
    def apply_confirmed_rule_pack(
        self,
        template_id: str,
        pack: Dict[str, Any],
        *,
        activate: bool,
    ) -> TemplateDefinition:
        """Publish a confirmed pack to the runtime config path and optionally activate it."""

        raw = self._read_config()
        target = next(
            (item for item in raw.get("templates", []) if item.get("template_id") == template_id),
            None,
        )
        if target is None:
            raise KeyError(f"Template does not exist: {template_id}")
        runtime_pack = strip_template_output_text_flags(pack)
        output_path = self._template_dir(template_id) / "template.rules.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(runtime_pack, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output_path)
        target["template_rules_config"] = self.to_config_path(output_path)
        if _pack_requests_generic_pipeline(pack):
            target["pipeline"] = "generic_rules_only"
        if activate:
            target["status"] = "active"
        self._write_config(raw)
        return self.get_template(template_id)

    @_registry_locked
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

    @_registry_locked
    def save_template_rules_config(self, template_id: str, content: str) -> Path | None:
        text = content.strip()
        if not text:
            return None
        parsed = json.loads(text)
        parsed = strip_template_output_text_flags(parsed)
        template_dir = self._template_dir(template_id)
        template_dir.mkdir(parents=True, exist_ok=True)
        output_path = template_dir / "template.rules.json"
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
            template_ai=self._optional_path(item.get("template_ai", "")),
            template_ai_role=str(item.get("template_ai_role", "尺寸/作图区模板") or "尺寸/作图区模板").strip(),
            default_columns=int(item.get("default_columns", 4) or 4),
            default_hide_boxes=bool(item.get("default_hide_boxes", True)),
            template_config=self._optional_path(item.get("template_config", "")),
            template_rules_config=self._optional_path(item.get("template_rules_config", "")),
            assets=self._parse_assets(item.get("assets", [])),
        )

    def _parse_assets(self, value: object) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        assets: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                assets.append({str(key): item[key] for key in item})
        return assets

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
        temporary = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.config_path)

    def _normalize_template_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(item.get("template_id", "")).strip()
        name = str(item.get("name", "")).strip()
        template_type = str(item.get("template_type", "")).strip()
        pipeline = str(item.get("pipeline", "")).strip() or DEFAULT_PIPELINES.get(template_type, "")
        status = str(item.get("status", "draft")).strip() or "draft"
        template_ai = str(item.get("template_ai", "")).strip()
        if not template_id:
            raise ValueError("缺少 template_id")
        if _safe_segment(template_id) != template_id:
            raise ValueError("template_id may only contain letters, numbers, '-' and '_'.")
        if not name:
            raise ValueError("缺少模板名称")
        if not template_type:
            raise ValueError("缺少模板类型")
        if not pipeline:
            raise ValueError("无法根据模板类型推断渲染流程，请检查模板类型")
        normalized: Dict[str, Any] = {
            "template_id": template_id,
            "name": name,
            "template_type": template_type,
            "pipeline": pipeline,
            "status": status,
            "template_ai": template_ai,
            "template_ai_role": str(item.get("template_ai_role", "尺寸/作图区模板") or "尺寸/作图区模板").strip(),
            "default_columns": int(item.get("default_columns", 4) or 4),
            "default_hide_boxes": _to_bool(item.get("default_hide_boxes", True)),
        }
        template_config = str(item.get("template_config", "")).strip()
        if template_config:
            normalized["template_config"] = template_config
        template_rules_config = str(item.get("template_rules_config", "")).strip()
        if template_rules_config:
            normalized["template_rules_config"] = template_rules_config
        assets = item.get("assets", [])
        if isinstance(assets, list):
            normalized["assets"] = [asset for asset in assets if isinstance(asset, dict)]
        return normalized

    def _template_dir(self, template_id: str) -> Path:
        safe_id = _safe_segment(template_id)
        if not safe_id or safe_id != str(template_id).strip():
            raise ValueError("模板 ID 不合法")
        return self.storage_dir / safe_id


def _safe_segment(value: str) -> str:
    chars = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
    return "".join(chars)


def _safe_filename(value: str) -> str:
    chars = []
    for char in Path(value).name.strip():
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("_")
    name = "".join(chars).strip("._")
    return name or "asset.ai"


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "否"}:
        return False
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    return bool(value)


def _pack_requests_generic_pipeline(pack: Dict[str, Any]) -> bool:
    rules = pack.get("rules") if isinstance(pack, dict) else None
    if not isinstance(rules, dict):
        return False
    bindings = rules.get("order_bindings")
    if not isinstance(bindings, dict) or not bindings:
        return False
    return bool(rules.get("slot_mappings") or rules.get("text_targets") or rules.get("asset_mappings"))
