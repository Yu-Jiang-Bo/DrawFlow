"""Batch rendering for published V2 workbench templates."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any, Mapping

from .canary_diagnostics import suppress_delivery_outputs as suppress_canary_delivery_outputs
from .job_store import JobStore
from .local_gateway_support import LOGGER
from .v2_order_io import read_order_rows
from .v2_order_output import V2OrderOutputRenderer
from .v2_order_plan import build_v2_order_units, v2_preflight_row_metrics
from .v2_order_preflight import preflight_v2_order_rows
from .v2_order_render_support import (
    V2OrderRenderError,
    asset_path,
    business_error,
    compile_task,
    extract_bundle,
    read_json,
    safe_template_id,
    sha256_file,
    stats,
    to_bool,
    write_json,
)
from .v2_order_snapshot import (
    check_snapshot_file_hash,
    failure_scope as v2_failure_scope,
    require_fixed_snapshot,
    resolve_published_version,
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
        *,
        production_batch_session: Any | None = None,
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.renderer = renderer
        self.font_dirs = font_dirs
        self.jobs = jobs or JobStore(self.data_dir / "jobs")
        # Internal-only dependency used by multi-template orchestration.  It
        # leaves the public single-template request and constructor call shape
        # intact for existing callers.
        self.production_batch_session = production_batch_session

    def render(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._render(payload)

    def render_fixed_snapshot(
        self,
        payload: Mapping[str, Any],
        *,
        version: str,
        template_sha256: str,
        config_sha256: str = "",
        scan_sha256: str = "",
        suppress_delivery_outputs: bool = False,
    ) -> dict[str, Any]:
        """Internal multi-template entry point; fixed fields are never HTTP payload data."""
        fixed_snapshot = require_fixed_snapshot(
            version=version,
            template_sha256=template_sha256,
            config_sha256=config_sha256,
            scan_sha256=scan_sha256,
        )
        return self._render(
            payload,
            fixed_version=fixed_snapshot["version"],
            fixed_template_sha256=fixed_snapshot["template_sha256"],
            fixed_config_sha256=fixed_snapshot["config_sha256"],
            fixed_scan_sha256=fixed_snapshot["scan_sha256"],
            include_preflight_metrics=True,
            suppress_delivery_outputs=suppress_delivery_outputs,
        )

    def _render(
        self,
        payload: Mapping[str, Any],
        *,
        fixed_version: str = "",
        fixed_template_sha256: str = "",
        fixed_config_sha256: str = "",
        fixed_scan_sha256: str = "",
        include_preflight_metrics: bool = False,
        suppress_delivery_outputs: bool = False,
    ) -> dict[str, Any]:
        template_id = safe_template_id(payload.get("template_id"))
        publication = self._published_version(
            template_id,
            fixed_version=fixed_version,
        )
        request = self._normalize_request(
            payload,
            publication,
            fixed_template_sha256=fixed_template_sha256,
            fixed_config_sha256=fixed_config_sha256,
            fixed_scan_sha256=fixed_scan_sha256,
            include_preflight_metrics=include_preflight_metrics,
        )
        record = self.jobs.create(request)
        try:
            self.jobs.update(record, status="running")
            result = self._run(record, request)
            record["outputs"] = result["outputs"]
            record["stats"] = result["stats"]
            if "_preflight_row_metrics" in result:
                record["_preflight_row_metrics"] = result["_preflight_row_metrics"]
            if suppress_delivery_outputs:
                suppress_canary_delivery_outputs(record)
            self.jobs.update(record, status="completed")
        except Exception as exc:
            failure = business_error(exc)
            message, code = failure[:2]
            technical_message = failure[2] if len(failure) > 2 else str(exc)
            LOGGER.error(
                "V2 render failed (job_id=%s, code=%s): %s",
                record["job_id"],
                code,
                technical_message,
            )
            self.jobs.update(
                record,
                status="failed",
                error=message,
                error_code=code,
                failure_scope=v2_failure_scope(exc),
            )
            # Recovery orchestration may inspect this in-memory value, but a
            # job query is public to the local UI and must never expose COM
            # details or machine paths from the exception chain.
            record["_technical_failure"] = technical_message
        return record

    def _published_version(self, template_id: str, *, fixed_version: str = "") -> dict[str, str]:
        return resolve_published_version(self.central, template_id, fixed_version=fixed_version)

    def _normalize_request(
        self,
        payload: Mapping[str, Any],
        publication: Mapping[str, str],
        *,
        fixed_template_sha256: str = "",
        fixed_config_sha256: str = "",
        fixed_scan_sha256: str = "",
        include_preflight_metrics: bool = False,
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
        request = {
            "template_id": publication["template_id"],
            "template_version": publication["version"],
            "order_file": str(order_file.resolve()),
            "sheet_name": str(payload.get("sheet_name") or "").strip(),
            "dry_run": to_bool(payload.get("dry_run", False)),
        }
        if fixed_template_sha256 or fixed_config_sha256 or fixed_scan_sha256:
            request.update({
                "_fixed_template_sha256": fixed_template_sha256,
                "_fixed_config_sha256": fixed_config_sha256,
                "_fixed_scan_sha256": fixed_scan_sha256,
            })
        if include_preflight_metrics:
            request["_include_preflight_metrics"] = True
        return request

    def _run(self, record: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        template_id = str(request["template_id"])
        version = str(request["template_version"])
        version_dir = self._download_version(template_id, version, job_dir)
        manifest = read_json(version_dir / "manifest.json")
        if str(manifest.get("version") or "").strip() != version:
            raise V2OrderRenderError(
                "预检时固定的模板版本校验未通过，请重新预检后再试。",
                code="v2_template_version_unavailable",
            )
        config = read_json(version_dir / "config.json")
        scan = read_json(version_dir / "scan.json")
        check_snapshot_file_hash(config_path := version_dir / "config.json", request.get("_fixed_config_sha256"), "模板配置")
        check_snapshot_file_hash(scan_path := version_dir / "scan.json", request.get("_fixed_scan_sha256"), "模板扫描")
        validation = validate_v2_template_configuration(config)
        if validation.get("can_save") is not True:
            raise V2OrderRenderError(
                first_business_issue(validation, "当前模板配置还不能出图，请回到 V2 工作台检查发布状态。"),
                code="v2_template_config_invalid",
            )
        asset = current_template_asset(manifest)
        template_ai = asset_path(version_dir, asset)
        self._check_asset(template_ai, asset)
        expected_snapshot_sha = str(request.get("_fixed_template_sha256") or "").strip().lower()
        if expected_snapshot_sha and sha256_file(template_ai) != expected_snapshot_sha:
            raise V2OrderRenderError(
                "预检时固定的模板文件已变化，请重新预检后再试。",
                code="v2_template_asset_invalid",
            )
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
            result = {
                "outputs": {"render_task": str(task_file), "output_manifest": str(manifest_path)},
                "stats": stats(rows, render_task, dry_run=True, planned_items=len(planned_units)),
            }
            if request.get("_include_preflight_metrics"):
                result["_preflight_row_metrics"] = v2_preflight_row_metrics(render_task, planned_units)
            return result
        return V2OrderOutputRenderer(
            self.renderer,
            production_batch_session=self.production_batch_session,
        ).render_outputs(
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
        except OSError as exc:
            raise V2OrderRenderError(
                "正式模板文件无法写入本机，请检查磁盘空间和目录权限后重试。",
                code="v2_template_version_unavailable",
                technical_message=str(exc),
                failure_scope="system",
            ) from exc
        except zipfile.BadZipFile as exc:
            raise V2OrderRenderError(
                "正式模板文件包已损坏，请重新发布模板后再试。",
                code="v2_template_version_unavailable",
                technical_message=str(exc),
                failure_scope="template",
            ) from exc
        except Exception as exc:
            raise V2OrderRenderError(
                "正式模板文件暂时无法读取，请检查本机客户端和模板服务后重试。",
                code="v2_template_version_unavailable",
                technical_message=str(exc),
                failure_scope="system",
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
