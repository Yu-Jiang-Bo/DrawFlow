"""Operator maintenance snapshots for V2 template storage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, Callable

from .paths import V2_TEMPLATE_DATA_DIR
from .v2_template_limits import DEFAULT_V2_TEMPLATE_LIMITS, V2TemplateLimitConfig
from .v2_template_store_utils import read_json, utc_now


DiskUsageGetter = Callable[[Path], Any]

MAINTENANCE_SCHEMA = "custom-renderer/v2-template-maintenance"
ALLOWED_CENTRAL_UPLOAD_KINDS = {
    "template",
    "template_asset",
    "config",
    "scan",
    "preview_audit_metadata",
    "preview_metadata",
    "metadata",
}
ORDER_OUTPUT_MARKERS = ("order_output", "official_order_output", "production_output", "formal_order_output")


class V2TemplateMaintenanceError(RuntimeError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class CentralUploadDecision:
    allowed: bool
    code: str
    reason: str

    def to_dict(self) -> dict[str, bool | str]:
        return {"allowed": self.allowed, "code": self.code, "reason": self.reason}


def list_template_metadata(root: Path | str = V2_TEMPLATE_DATA_DIR) -> list[dict[str, Any]]:
    storage_root = Path(root)
    if not storage_root.exists():
        return []
    return [_state_summary(read_json(path)) for path in sorted(storage_root.glob("*/state.json"))]


def build_maintenance_snapshot(
    root: Path | str = V2_TEMPLATE_DATA_DIR,
    *,
    limits: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS,
    disk_usage_getter: DiskUsageGetter | None = None,
) -> dict[str, Any]:
    storage_root = Path(root)
    templates = list_template_metadata(storage_root)
    disk = _disk_status(storage_root, limits, disk_usage_getter)
    return {
        "schema": MAINTENANCE_SCHEMA,
        "checked_at": utc_now(),
        "root": str(storage_root),
        "limits": {
            "max_file_size_bytes": limits.max_file_size_bytes,
            "max_concurrent_uploads": limits.max_concurrent_uploads,
            "temp_dir": str(limits.temp_dir),
            "min_free_space_bytes": limits.min_free_space_bytes,
        },
        "disk": disk,
        "templates": {
            "total": len(templates),
            "active": sum(1 for item in templates if item.get("publication", {}).get("status") == "active"),
            "with_draft": sum(1 for item in templates if item.get("draft")),
            "version_count": sum(len(item.get("versions", [])) for item in templates),
        },
        "template_metadata": templates,
    }


def drawing_group_safe_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    templates = snapshot.get("template_metadata", [])
    return {
        "templates": [dict(item) for item in templates if isinstance(item, Mapping)],
        "summary": {
            "total": int(dict(snapshot.get("templates", {})).get("total") or 0),
            "active": int(dict(snapshot.get("templates", {})).get("active") or 0),
            "with_draft": int(dict(snapshot.get("templates", {})).get("with_draft") or 0),
            "version_count": int(dict(snapshot.get("templates", {})).get("version_count") or 0),
        },
    }


def maintenance_log_fields(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    disk = dict(snapshot.get("disk", {}))
    templates = dict(snapshot.get("templates", {}))
    return {
        "template_total": templates.get("total", 0),
        "template_active": templates.get("active", 0),
        "disk_status": disk.get("status", ""),
        "disk_free_bytes": disk.get("free_bytes", 0),
        "disk_min_free_space_bytes": disk.get("min_free_space_bytes", 0),
        "reason": disk.get("reason", ""),
    }


def central_upload_decision(artifact_kind: str) -> CentralUploadDecision:
    normalized = str(artifact_kind or "").strip().lower().replace("-", "_")
    if _is_order_output(normalized):
        return CentralUploadDecision(
            False,
            "v2_official_order_output_upload_forbidden",
            "正式订单成品不得上传中央服务；中央服务只保存模板、配置、扫描和预览审核元数据。",
        )
    if normalized in ALLOWED_CENTRAL_UPLOAD_KINDS:
        return CentralUploadDecision(True, "v2_central_upload_allowed", "中央服务允许保存该类 V2 模板资料。")
    return CentralUploadDecision(
        False,
        "v2_central_upload_kind_rejected",
        "中央服务只接受模板、配置、扫描和预览审核元数据，不接收其它业务文件。",
    )


def require_central_upload_allowed(artifact_kind: str) -> None:
    decision = central_upload_decision(artifact_kind)
    if not decision.allowed:
        raise V2TemplateMaintenanceError(decision.code, decision.reason)


def _disk_status(
    root: Path,
    limits: V2TemplateLimitConfig,
    disk_usage_getter: DiskUsageGetter | None,
) -> dict[str, Any]:
    probe = _existing_probe(root)
    usage = disk_usage_getter(probe) if disk_usage_getter else shutil.disk_usage(probe)
    free = int(usage.free)
    ok = free >= limits.min_free_space_bytes
    return {
        "path": str(probe),
        "status": "ok" if ok else "low",
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": free,
        "min_free_space_bytes": limits.min_free_space_bytes,
        "reason": "磁盘余量满足 V2 模板服务要求。" if ok else "磁盘剩余空间低于 V2 模板服务最低安全余量。",
    }


def _state_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_id": state.get("template_id", ""),
        "template": dict(state.get("template", {})),
        "draft": dict(state["draft"]) if isinstance(state.get("draft"), Mapping) else None,
        "publication": dict(state.get("publication", {})),
        "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
    }


def _existing_probe(path: Path) -> Path:
    probe = path if path.exists() else path.parent
    while probe and not probe.exists():
        if probe.parent == probe:
            break
        probe = probe.parent
    return probe if probe.exists() else Path.cwd()


def _is_order_output(normalized_kind: str) -> bool:
    if not normalized_kind:
        return False
    return any(marker in normalized_kind for marker in ORDER_OUTPUT_MARKERS) or (
        "order" in normalized_kind and "output" in normalized_kind
    )


__all__ = [
    "CentralUploadDecision",
    "V2TemplateMaintenanceError",
    "build_maintenance_snapshot",
    "central_upload_decision",
    "drawing_group_safe_view",
    "list_template_metadata",
    "maintenance_log_fields",
    "require_central_upload_allowed",
]
