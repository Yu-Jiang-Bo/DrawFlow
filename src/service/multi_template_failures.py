"""Stable failure normalization for multi-template rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..renderer.illustrator_bridge import IllustratorBridgeError, RETRYABLE_COM_HRESULTS


FAILURE_SCOPES = frozenset({"template", "system"})
TEMPLATE_FAILURE_CODES = frozenset({
    "child_output_missing",
    "department_output_pipeline_unsupported",
    "department_output_policy_conflict",
    "illustrator_render_failed",
    "missing_order_file",
    "missing_required_fonts",
    "missing_template_id",
    "order_file_missing",
    "order_parse_failed",
    "render_failed",
    "template_bundle_invalid",
    "template_config_missing",
    "template_font_config_missing",
    "template_not_active",
    "template_not_available",
    "template_not_published",
    "template_pipeline_invalid",
    "template_rules_invalid",
    "template_snapshot_mismatch",
    "template_style_config_invalid",
    "template_style_config_missing",
    "v2_department_master_packing_missing",
    "v2_order_batch_invalid",
    "v2_order_color_compose_not_supported",
    "v2_order_compose_not_supported",
    "v2_order_file_unreadable",
    "v2_order_not_supported",
    "v2_order_plan_invalid",
    "v2_order_png_master_not_supported",
    "v2_order_preflight_failed",
    "v2_order_render_failed",
    "v2_order_render_not_supported",
    "v2_order_style_dimensions_invalid",
    "v2_order_style_dimensions_missing",
    "v2_output_missing",
    "v2_public_output_metadata_missing",
    "v2_render_task_invalid",
    "v2_template_asset_invalid",
    "v2_template_asset_missing",
    "v2_template_bundle_invalid",
    "v2_template_config_invalid",
    "v2_template_not_found",
    "v2_template_not_published",
    "v2_template_snapshot_invalid",
    "v2_template_version_unavailable",
})


@dataclass(frozen=True)
class MultiTemplateFailure:
    code: str
    message: str
    failure_scope: str
    technical_message: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "failure_scope": self.failure_scope,
            "technical_message": self.technical_message,
        }


def normalize_failure(value: Mapping[str, Any] | BaseException, *, default_code: str = "template_render_failed") -> MultiTemplateFailure:
    if isinstance(value, Mapping):
        code = str(value.get("error_code") or default_code)
        message = str(value.get("error") or "模板组渲染失败。")
        technical_message = str(value.get("technical_message") or value.get("_technical_failure") or "")
        declared = str(value.get("failure_scope") or "")
    else:
        code = str(getattr(value, "code", "") or default_code)
        message = str(value) or "模板组渲染失败。"
        technical_message = str(getattr(value, "technical_message", "") or "")
        declared = str(getattr(value, "failure_scope", "") or "")
    return MultiTemplateFailure(code, message, _scope_for(value, code, declared), technical_message)


def failure_scope(value: Mapping[str, Any] | BaseException) -> str:
    return normalize_failure(value).failure_scope


def is_recoverable_com_failure(value: Mapping[str, Any] | BaseException) -> bool:
    if isinstance(value, Mapping):
        details = " ".join(
            str(value.get(key) or "")
            for key in ("error_code", "error", "technical_message", "_technical_failure")
        )
        return any(code in details for code in RETRYABLE_COM_HRESULTS)
    return isinstance(value, IllustratorBridgeError) and any(code in str(value) for code in RETRYABLE_COM_HRESULTS)


def _scope_for(value: Mapping[str, Any] | BaseException, code: str, declared: str) -> str:
    if declared in FAILURE_SCOPES:
        return declared
    if isinstance(value, OSError):
        return "system"
    if isinstance(value, IllustratorBridgeError):
        return "system" if is_recoverable_com_failure(value) else "template"
    return "template" if code in TEMPLATE_FAILURE_CODES else "system"


__all__ = [
    "FAILURE_SCOPES",
    "TEMPLATE_FAILURE_CODES",
    "MultiTemplateFailure",
    "failure_scope",
    "is_recoverable_com_failure",
    "normalize_failure",
]
