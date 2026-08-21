"""Batch rendering for published V2 workbench templates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from .job_store import JobStore
from .v2_order_output import V2OrderOutputRenderer
from .v2_order_plan import build_v2_order_units
from .v2_order_preflight import preflight_v2_order_rows
from .v2_order_render_support import (
    V2OrderRenderError,
    asset_path,
    business_error,
    central_v2_versions,
    compile_task,
    extract_bundle,
    read_json,
    read_order_rows,
    safe_template_id,
    sha256_file,
    stats,
    to_bool,
    write_json,
)
from .v2_template_validation import validate_v2_template_configuration
from .v2_trial_render_support import (
    current_template_asset,
    first_business_issue,
    missing_required_fonts,
    required_fonts,
)


class V2OrderRenderService:
    def __init__(
        self,
        central: Any,
        data_dir: Path | str,
        renderer: Any,
        font_dirs: list[Path] | None,
        jobs: JobStore | None = None,
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.renderer = renderer
        self.font_dirs = font_dirs
        self.jobs = jobs or JobStore(self.data_dir / "jobs")

    def render(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        template_id = safe_template_id(payload.get("template_id"))
        publication = self._published_version(template_id)
        request = self._normalize_request(payload, publication)
        record = self.jobs.create(request)
        try:
            self.jobs.update(record, status="running")
            result = self._run(record, request)
            record["outputs"] = result["outputs"]
            record["stats"] = result["stats"]
            self.jobs.update(record, status="completed")
        except Exception as exc:
            message, code = business_error(exc)
            self.jobs.update(record, status="failed", error=message, error_code=code)
        return record

    def _published_version(self, template_id: str) -> dict[str, str]:
        try:
            payload = central_v2_versions(self.central, template_id)
        except Exception as exc:
            raise V2OrderRenderError(
                "模板尚未在 V2 工作台发布可用版本，请先发布后再出图。",
                code="v2_template_not_found",
                technical_message=str(exc),
            ) from exc
        publication = dict(payload.get("publication") or {})
        version = str(publication.get("current_version") or "").strip()
        if str(publication.get("status") or "").strip() != "active" or not version:
            raise V2OrderRenderError(
                "模板尚未在 V2 工作台发布可用版本，请先发布后再出图。",
                code="v2_template_not_published",
            )
        return {"template_id": template_id, "version": version}

    def _normalize_request(
        self,
        payload: Mapping[str, Any],
        publication: Mapping[str, str],
    ) -> dict[str, Any]:
        order_file_value = str(payload.get("order_file") or "").strip()
        if not order_file_value:
            raise V2OrderRenderError("请先上传订单表格。", code="missing_order_file")
        order_file = Path(order_file_value)
        if not order_file.exists():
            raise V2OrderRenderError(
                "订单表格不存在，请重新选择后再试。",
                code="order_file_missing",
            )
        return {
            "template_id": publication["template_id"],
            "template_version": publication["version"],
            "order_file": str(order_file.resolve()),
            "sheet_name": str(payload.get("sheet_name") or "").strip(),
            "dry_run": to_bool(payload.get("dry_run", False)),
        }

    def _run(self, record: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        template_id = str(request["template_id"])
        version = str(request["template_version"])
        version_dir = self._download_version(template_id, version, job_dir)
        manifest = read_json(version_dir / "manifest.json")
        config = read_json(version_dir / "config.json")
        scan = read_json(version_dir / "scan.json")
        validation = validate_v2_template_configuration(config)
        if validation.get("can_save") is not True:
            raise V2OrderRenderError(
                first_business_issue(validation, "当前模板配置还不能出图，请回到 V2 工作台检查发布状态。"),
                code="v2_template_config_invalid",
            )
        asset = current_template_asset(manifest)
        template_ai = asset_path(version_dir, asset)
        self._check_asset(template_ai, asset)
        rows = read_order_rows(request)
        preflight = preflight_v2_order_rows(config, rows)
        if preflight.get("can_render") is not True:
            raise V2OrderRenderError(
                first_business_issue(preflight, "订单表格没有通过出图前检查，请核对字段和选项值。"),
                code="v2_order_preflight_failed",
            )
        missing_fonts = missing_required_fonts(required_fonts(config, scan), self.font_dirs)
        if missing_fonts:
            raise V2OrderRenderError(
                "本机缺少当前模板所需字体：" + "、".join(missing_fonts),
                code="missing_required_fonts",
            )
        render_task = compile_task(config, scan, manifest, template_id, version)
        task_file = job_dir / "render-task.json"
        write_json(task_file, render_task, ensure_ascii=True)
        manifest_path = job_dir / "manifest.json"
        if request.get("dry_run"):
            planned_units = build_v2_order_units(config, render_task, rows, preflight)
            write_json(manifest_path, {"orders": len(rows), "outputs": len(render_task.get("outputs", [])), "items": len(planned_units)})
            return {
                "outputs": {"render_task": str(task_file), "output_manifest": str(manifest_path)},
                "stats": stats(rows, render_task, dry_run=True, planned_items=len(planned_units)),
            }
        return V2OrderOutputRenderer(self.renderer).render_outputs(
            record,
            config,
            render_task,
            template_ai,
            rows,
            preflight,
            task_file,
            manifest_path,
        )

    def _download_version(self, template_id: str, version: str, job_dir: Path) -> Path:
        bundle_path = job_dir / "template-version.zip"
        version_dir = job_dir / "template-version"
        try:
            if hasattr(self.central, "download_v2_version_bundle_to_file"):
                self.central.download_v2_version_bundle_to_file(template_id, version, bundle_path)
            elif hasattr(self.central, "version_bundle_path"):
                shutil.copyfile(self.central.version_bundle_path(template_id, version), bundle_path)
            else:
                raise V2OrderRenderError(
                    "中央服务暂不支持 V2 正式模板出图，请更新服务后再试。",
                    code="v2_order_not_supported",
                )
            extract_bundle(bundle_path, version_dir)
        except V2OrderRenderError:
            raise
        except Exception as exc:
            raise V2OrderRenderError(
                "正式模板文件读取失败，请重新发布模板后再试。",
                code="v2_template_version_unavailable",
                technical_message=str(exc),
            ) from exc
        return version_dir

    def _check_asset(self, template_ai: Path, asset: Mapping[str, Any]) -> None:
        expected = str(asset.get("sha256") or "").strip().lower()
        if not template_ai.is_file() or not expected or sha256_file(template_ai) != expected:
            raise V2OrderRenderError(
                "正式模板文件校验未通过，请重新发布模板后再试。",
                code="v2_template_asset_invalid",
            )

__all__ = ["V2OrderRenderError", "V2OrderRenderService"]
