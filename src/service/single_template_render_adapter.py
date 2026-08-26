"""Safe dry-run adapter that reuses existing single-template validation paths."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .job_store import JobStore
from .canary_diagnostics import suppress_delivery_outputs
from .multi_template_order import TemplateOrderGroup
from .multi_template_plan_metrics import PlanMetricsError, planned_row_metrics
from .multi_template_snapshot import TemplateSnapshot
from .render_service import RenderService
from .template_registry import TemplateDefinition
from .v2_order_render import V2OrderRenderService
from .v2_order_render_support import V2OrderRenderError
from .v2_template_boundary import V2_RENDER_PIPELINE
from .v2_trial_render_support import missing_required_fonts


@dataclass(frozen=True)
class SingleTemplatePreflightResult:
    template_id: str
    can_render: bool
    normalized_request: dict[str, Any]
    plan: dict[str, Any]
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "can_render": self.can_render,
            "normalized_request": dict(self.normalized_request),
            "plan": dict(self.plan),
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class SingleTemplateRenderAdapter:
    """Build one group plan through the existing dry-run services only."""

    def __init__(
        self,
        *,
        central: Any,
        cache: Any,
        data_dir: Path | str,
        v2_renderer: Any,
        font_dirs: list[Path] | None,
    ) -> None:
        self.central = central
        self.cache = cache
        self.data_dir = Path(data_dir)
        self.v2_renderer = v2_renderer
        self.font_dirs = font_dirs

    def preflight(
        self,
        group: TemplateOrderGroup,
        snapshot: TemplateSnapshot,
        *,
        group_workbook: Path | str,
        work_dir: Path | str,
    ) -> SingleTemplatePreflightResult:
        if group.template_id != snapshot.template_id:
            return _failed(snapshot.template_id, "template_snapshot_mismatch", "模板分组与预检快照不一致，请重新预检。")
        missing_fonts = missing_required_fonts(list(snapshot.required_fonts), self.font_dirs)
        if missing_fonts:
            return _failed(snapshot.template_id, "missing_required_fonts", "本机缺少模板字体：" + "、".join(missing_fonts))
        source = Path(group_workbook)
        if not source.is_file():
            return _failed(snapshot.template_id, "group_workbook_missing", "模板分组订单文件不存在，请重新预检。")
        target = Path(work_dir).resolve()
        jobs = JobStore(target / "jobs")
        payload = {
            "template_id": snapshot.template_id,
            "order_file": str(source.resolve()),
            "sheet_name": group.rows[0].sheet_name,
            "dry_run": True,
            "visible": False,
        }
        if snapshot.pipeline == V2_RENDER_PIPELINE:
            record = V2OrderRenderService(
                self.central,
                target,
                self.v2_renderer,
                self.font_dirs,
                jobs,
            ).render_fixed_snapshot(
                payload,
                version=snapshot.version,
                template_sha256=snapshot.template_sha256,
                config_sha256=snapshot.config_sha256,
                scan_sha256=snapshot.scan_sha256,
            )
        else:
            record = RenderService(
                registry=_SnapshotRegistry(_legacy_template(snapshot)),
                jobs=jobs,
            ).submit(payload)
        if record.get("status") != "completed":
            return _failed(
                snapshot.template_id,
                str(record.get("error_code") or "template_preflight_failed"),
                _business_error_message(str(record.get("error_code") or "template_preflight_failed")),
                request=dict(record.get("request") or {}),
            )
        try:
            row_metrics = planned_row_metrics(group, record)
        except PlanMetricsError:
            return _failed(
                snapshot.template_id,
                "preflight_plan_metrics_missing",
                "无法从模板 dry-run 计划确认每行订单的效果图数量，请检查模板渲染配置后重新预检。",
                request=dict(record.get("request") or {}),
            )
        return SingleTemplatePreflightResult(
            snapshot.template_id,
            True,
            dict(record.get("request") or {}),
            {
                "stats": dict(record.get("stats") or {}),
                "output_keys": sorted(dict(record.get("outputs") or {}).keys()),
                "group_order_count": len(group.rows),
                "row_metrics": row_metrics,
            },
        )

    def render_canary(
        self,
        group: TemplateOrderGroup,
        snapshot: TemplateSnapshot,
        *,
        group_workbook: Path | str,
        work_dir: Path | str,
    ) -> dict[str, Any]:
        """Render one isolated representative order through the production path.

        The returned child job is explicitly diagnostic: its original delivery
        paths are retained under ``canary_outputs`` for local troubleshooting,
        while the ordinary delivery fields are removed before the job is saved.
        """
        source = Path(group_workbook)
        target = Path(work_dir).resolve()
        payload = {
            "template_id": snapshot.template_id,
            "order_file": str(source.resolve()),
            "sheet_name": group.rows[0].sheet_name if group.rows else "",
            "dry_run": False,
            "visible": False,
        }
        if group.template_id != snapshot.template_id:
            return _failed_render(payload, "template_snapshot_mismatch", "模板分组与预检快照不一致，请重新预检。")
        if not source.is_file():
            return _failed_render(payload, "canary_workbook_missing", "代表订单文件不存在，请重新预检。")
        missing_fonts = missing_required_fonts(list(snapshot.required_fonts), self.font_dirs)
        if missing_fonts:
            return _failed_render(payload, "missing_required_fonts", "本机缺少模板字体：" + "、".join(missing_fonts))
        jobs = JobStore(target / "jobs")
        if snapshot.pipeline == V2_RENDER_PIPELINE:
            try:
                record = V2OrderRenderService(
                    self.central,
                    target,
                    self.v2_renderer,
                    self.font_dirs,
                    jobs,
                ).render_fixed_snapshot(
                    payload,
                    version=snapshot.version,
                    template_sha256=snapshot.template_sha256,
                    config_sha256=snapshot.config_sha256,
                    scan_sha256=snapshot.scan_sha256,
                    suppress_delivery_outputs=True,
                )
            except V2OrderRenderError as exc:
                return _failed_render(payload, exc.code, str(exc), failure_scope=exc.failure_scope)
        else:
            record = RenderService(
                registry=_SnapshotRegistry(_legacy_template(snapshot)),
                jobs=jobs,
            ).submit(payload, suppress_delivery_outputs=True)
        _mark_diagnostic_canary(jobs, record)
        return record


class _SnapshotRegistry:
    def __init__(self, template: TemplateDefinition) -> None:
        self.template = template

    def get_template(self, template_id: str) -> TemplateDefinition:
        if template_id != self.template.template_id:
            raise KeyError(template_id)
        return self.template


def _legacy_template(snapshot: TemplateSnapshot) -> TemplateDefinition:
    try:
        metadata = json.loads(snapshot.template_metadata)
    except (TypeError, ValueError):
        metadata = {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return TemplateDefinition(
        snapshot.template_id,
        str(metadata.get("name") or snapshot.template_id),
        str(metadata.get("template_type") or "pure_text"),
        snapshot.pipeline,
        "active",
        Path(snapshot.template_ai),
        str(metadata.get("template_ai_role") or "尺寸/作图区模板"),
        int(metadata.get("default_columns") or 4),
        bool(metadata.get("default_hide_boxes", True)),
        Path(snapshot.template_config) if snapshot.template_config else None,
        Path(snapshot.template_rules_config) if snapshot.template_rules_config else None,
        [dict(item) for item in metadata.get("assets", []) if isinstance(item, Mapping)],
    )


def _failed(template_id: str, code: str, message: str, *, request: dict[str, Any] | None = None) -> SingleTemplatePreflightResult:
    return SingleTemplatePreflightResult(template_id, False, request or {}, {}, code, message)


def _failed_render(
    request: dict[str, Any],
    code: str,
    message: str,
    *,
    failure_scope: str = "",
) -> dict[str, Any]:
    return {
        "status": "failed",
        "request": request,
        "outputs": {},
        "stats": {},
        "error_code": code,
        "error": message,
        "failure_scope": failure_scope,
        "canary": True,
    }


def _mark_diagnostic_canary(jobs: JobStore, record: dict[str, Any]) -> None:
    suppress_delivery_outputs(record)
    if record.get("job_id") and record.get("job_dir"):
        jobs.save(record)


def _business_error_message(code: str) -> str:
    messages = {
        "template_rules_invalid": "模板规则不完整，请补齐配置后重新预检。",
        "template_config_missing": "模板配置缺失，请重新发布模板后再试。",
        "template_font_config_missing": "模板字体配置缺失，请重新发布模板后再试。",
        "v2_template_version_unavailable": "预检时固定的模板版本已不可用，请重新预检后再试。",
        "v2_template_asset_invalid": "预检时固定的模板文件已变化，请重新预检后再试。",
        "v2_template_config_invalid": "预检时固定的模板配置已变化，请重新预检后再试。",
        "v2_order_preflight_failed": "该模板的订单字段或选项未通过预检，请检查订单内容。",
    }
    return messages.get(code, "模板订单预检失败，请检查订单字段和模板配置。")


__all__ = ["SingleTemplatePreflightResult", "SingleTemplateRenderAdapter"]
