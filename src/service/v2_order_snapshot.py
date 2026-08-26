"""Fixed V2 template snapshot resolution and failure classification."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from .v2_order_render_support import V2OrderRenderError, central_v2_versions, sha256_file


def resolve_published_version(central: Any, template_id: str, *, fixed_version: str = "") -> dict[str, str]:
    try:
        payload = central_v2_versions(central, template_id)
    except Exception as exc:
        raise V2OrderRenderError(
            "模板尚未在 V2 工作台发布可用版本，请先发布后再出图。",
            code="v2_template_not_found",
            technical_message=str(exc),
            failure_scope="system",
        ) from exc
    publication = dict(payload.get("publication") or {})
    current_version = str(publication.get("current_version") or "").strip()
    if str(publication.get("status") or "").strip() != "active" or not current_version:
        raise V2OrderRenderError(
            "模板尚未在 V2 工作台发布可用版本，请先发布后再出图。",
            code="v2_template_not_published",
            failure_scope="template",
        )
    version = fixed_version or current_version
    if fixed_version:
        versions = {
            str(item.get("version") or "").strip()
            for item in payload.get("versions", [])
            if isinstance(item, Mapping)
        }
        if (versions and fixed_version not in versions) or (not versions and fixed_version != current_version):
            raise V2OrderRenderError(
                "预检时固定的模板版本已不可用，请重新预检后再试。",
                code="v2_template_version_unavailable",
                failure_scope="template",
            )
    return {"template_id": template_id, "version": version}


def check_snapshot_file_hash(path: Path, expected: Any, label: str) -> None:
    expected_sha = str(expected or "").strip().lower()
    if expected_sha and sha256_file(path) != expected_sha:
        raise V2OrderRenderError(
            f"预检时固定的{label}已变化，请重新预检后再试。",
            code="v2_template_config_invalid",
        )


def require_fixed_snapshot(
    *,
    version: Any,
    template_sha256: Any,
    config_sha256: Any,
    scan_sha256: Any,
) -> dict[str, str]:
    """Validate the private fixed-snapshot contract before it can render."""

    fixed_version = str(version or "").strip()
    hashes = {
        "template_sha256": str(template_sha256 or "").strip().lower(),
        "config_sha256": str(config_sha256 or "").strip().lower(),
        "scan_sha256": str(scan_sha256 or "").strip().lower(),
    }
    if not fixed_version or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        raise V2OrderRenderError(
            "预检模板快照不完整，请重新预检后再试。",
            code="v2_template_snapshot_invalid",
            failure_scope="template",
        )
    return {"version": fixed_version, **hashes}


def failure_scope(exc: Exception) -> str:
    declared = str(getattr(exc, "failure_scope", "") or "")
    if declared in {"template", "system"}:
        return declared
    if isinstance(exc, V2OrderRenderError) and exc.code in _TEMPLATE_FAILURE_CODES:
        return "template"
    return "system"


_TEMPLATE_FAILURE_CODES = frozenset({
    "missing_order_file",
    "missing_required_fonts",
    "missing_template_id",
    "order_file_missing",
    "v2_department_master_packing_missing",
    "v2_order_batch_invalid",
    "v2_order_color_compose_not_supported",
    "v2_order_compose_not_supported",
    "v2_order_file_unreadable",
    "v2_order_not_supported",
    "v2_order_plan_invalid",
    "v2_order_png_master_not_supported",
    "v2_order_preflight_failed",
    "v2_order_render_not_supported",
    "v2_order_style_dimensions_invalid",
    "v2_order_style_dimensions_missing",
    "v2_public_output_metadata_missing",
    "v2_render_task_invalid",
    "v2_template_asset_invalid",
    "v2_template_asset_missing",
    "v2_template_bundle_invalid",
    "v2_template_config_invalid",
    "v2_template_not_found",
    "v2_template_not_published",
    "v2_template_version_unavailable",
    "v2_template_snapshot_invalid",
    "v2_output_missing",
})


__all__ = ["check_snapshot_file_hash", "failure_scope", "require_fixed_snapshot", "resolve_published_version"]
