"""Local orchestration for real V2 sample rendering and preview serving."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from uuid import uuid4

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.renderer.v2_template_renderer import V2TemplateRendererError

from .runtime_templates import sha256_file
from .v2_order_preflight import preflight_v2_order_rows
from .v2_preview_proof import (
    V2PreviewProofError,
    compile_preview_render_task,
    preview_config_payload,
    preview_config_sha256,
    preview_outputs_sha256,
    sample_rows_sha256,
    utc_timestamp_now,
)
from .v2_preview_worker_auth import V2PreviewWorkerAuthError, WORKER_ID_PATTERN
from .v2_render_task import V2_RENDERER_VERSION, V2RenderTaskError
from .v2_template_store_utils import safe_segment
from .v2_template_validation import validate_v2_template_configuration
from .v2_trial_render_support import (
    V2TrialRenderError,
    current_template_asset,
    download_asset,
    first_business_issue,
    logical_values,
    missing_required_fonts,
    output_labels,
    read_draft,
    read_warnings,
    request_challenge,
    required_fonts,
    sample_row,
    selections,
    submit_proof,
    worker_proof,
)


class V2TrialRenderService:
    def __init__(
        self,
        central: Any,
        data_dir: Path | str,
        renderer: Any,
        font_dirs: list[Path] | None,
        preview_worker_secret: str | bytes,
        preview_worker_id: str,
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.renderer = renderer
        self.font_dirs = font_dirs
        self.preview_worker_secret = preview_worker_secret
        self.preview_worker_id = preview_worker_id

    def render(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        safe_id, revision, row = self._request(template_id, payload)
        draft = read_draft(self.central, safe_id)
        manifest = dict(draft.get("manifest") or {})
        if str(manifest.get("draft_revision") or "").strip() != revision:
            raise V2TrialRenderError("模板草稿已在其他操作中更新，请刷新页面后重新试渲染。", code="v2_trial_draft_changed")
        self._require_worker_configuration()
        config = preview_config_payload(dict(draft.get("config") or {}), [row])
        preflight = self._preflight(config, row)
        fonts = missing_required_fonts(required_fonts(config, dict(draft.get("scan") or {})), self.font_dirs)
        if fonts:
            raise V2TrialRenderError("本机缺少当前模板所需字体：" + "、".join(fonts), code="v2_trial_fonts_missing")
        font_check = {"ok": True, "missing": []}
        try:
            render_task = compile_preview_render_task(draft, config, font_check)
        except (V2PreviewProofError, V2RenderTaskError) as exc:
            raise V2TrialRenderError(_safe_compile_message(exc), code="v2_trial_task_invalid", technical_message=str(exc)) from exc
        asset = current_template_asset(manifest)
        if not asset:
            raise V2TrialRenderError("当前草稿缺少模板 AI 文件，请重新上传并扫描。", code="v2_trial_asset_missing")
        trial_id = uuid4().hex
        trial_dir = self.data_dir / "v2-trials" / safe_id / trial_id
        trial_dir.mkdir(parents=True, exist_ok=False)
        try:
            result = self._run_outputs(config, row, preflight, render_task, asset, trial_id, trial_dir)
            evidence = self._evidence(draft, config, row, render_task, asset, result, font_check, revision)
            _write_manifest(trial_dir, result["public_outputs"])
            challenge = request_challenge(
                self.central,
                safe_id,
                revision,
                self.preview_worker_id,
            )
            signed = worker_proof(
                self.preview_worker_secret,
                challenge,
                safe_id,
                revision,
                [row],
                evidence,
                self.preview_worker_id,
            )
            registered = submit_proof(
                self.central,
                safe_id,
                revision,
                [row],
                evidence,
                signed,
            )
            return {
                "trial": {
                    "id": trial_id,
                    "status": "passed",
                    "outputs": result["public_outputs"],
                    "warnings": result["warnings"],
                    "rendered_at": evidence["rendered_at"],
                },
                **registered,
            }
        except V2TrialRenderError:
            shutil.rmtree(trial_dir, ignore_errors=True)
            raise
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            shutil.rmtree(trial_dir, ignore_errors=True)
            raise V2TrialRenderError("Illustrator 未能完成样例渲染，请确认模板可正常打开后重试。", code="v2_trial_render_failed", technical_message=str(exc)) from exc
        except V2PreviewWorkerAuthError as exc:
            shutil.rmtree(trial_dir, ignore_errors=True)
            raise V2TrialRenderError(
                "真实试渲染服务的安全配置无效，请联系维护人员。",
                code="v2_trial_worker_unavailable",
                technical_message=f"{exc.code}: {exc}",
            ) from exc
        except Exception as exc:
            shutil.rmtree(trial_dir, ignore_errors=True)
            raise V2TrialRenderError("样例渲染未完成，请重新启动本地客户端后重试。", code="v2_trial_unexpected", technical_message=str(exc)) from exc

    def preview_path(self, trial_id: str, output_key: str) -> Path:
        safe_trial = str(trial_id or "").strip()
        safe_output = str(output_key or "").strip()
        if safe_segment(safe_trial) != safe_trial or safe_segment(safe_output) != safe_output:
            raise V2TrialRenderError("样例效果图不存在，请重新试渲染。", code="v2_trial_preview_missing")
        root = self.data_dir / "v2-trials"
        matches = list(root.glob(f"*/{safe_trial}/trial.json")) if root.exists() else []
        if len(matches) != 1:
            raise V2TrialRenderError("样例效果图不存在，请重新试渲染。", code="v2_trial_preview_missing")
        trial_dir = matches[0].parent.resolve()
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
        outputs = payload.get("outputs") if isinstance(payload, Mapping) else []
        file_name = next((str(item.get("file_name") or "") for item in outputs if isinstance(item, Mapping) and item.get("key") == safe_output), "")
        target = (trial_dir / "outputs" / file_name).resolve()
        if not file_name or target.parent != (trial_dir / "outputs").resolve() or not target.is_file():
            raise V2TrialRenderError("样例效果图不存在，请重新试渲染。", code="v2_trial_preview_missing")
        return target

    def _request(self, template_id: str, payload: Mapping[str, Any]) -> tuple[str, str, dict[str, str]]:
        safe_id = str(template_id or "").strip()
        revision = str(payload.get("expected_draft_revision") or "").strip()
        raw_row = payload.get("sample_row")
        if not safe_id or safe_segment(safe_id) != safe_id:
            raise V2TrialRenderError("当前模板信息无效，请返回模板列表后重新打开。", code="v2_trial_template_invalid")
        if not revision:
            raise V2TrialRenderError("模板草稿已变化，请保存后重新试渲染。", code="v2_trial_revision_required")
        if not isinstance(raw_row, Mapping) or not (row := sample_row(raw_row)):
            raise V2TrialRenderError("请先填写一行样例订单数据。", code="v2_trial_sample_required")
        return safe_id, revision, row

    def _preflight(self, config: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
        validation = validate_v2_template_configuration(config)
        if validation.get("can_save") is not True:
            raise V2TrialRenderError(first_business_issue(validation, "当前模板配置还不能试渲染，请先完成标红设置。"), code="v2_trial_config_invalid")
        preflight = preflight_v2_order_rows(config, [row])
        if preflight.get("can_render") is not True:
            raise V2TrialRenderError(first_business_issue(preflight, "样例订单没有通过渲染前检查，请核对字段和值。"), code="v2_trial_preflight_failed")
        return preflight

    def _require_worker_configuration(self) -> None:
        raw = self.preview_worker_secret
        secret = raw.strip() if isinstance(raw, bytes) else str(raw or "").strip().encode("utf-8")
        if len(secret) < 32:
            raise V2TrialRenderError(
                "真实试渲染服务尚未完成安全配置，请联系维护人员。",
                code="v2_trial_worker_unavailable",
            )
        if not WORKER_ID_PATTERN.fullmatch(str(self.preview_worker_id or "")):
            raise V2TrialRenderError(
                "真实试渲染服务的安全配置无效，请联系维护人员。",
                code="v2_trial_worker_unavailable",
                technical_message="preview_worker_id_invalid",
            )

    def _run_outputs(self, config: Mapping[str, Any], row: Mapping[str, Any], preflight: Mapping[str, Any], task: Mapping[str, Any], asset: Mapping[str, Any], trial_id: str, trial_dir: Path) -> dict[str, Any]:
        source = trial_dir / "source" / _safe_name(str(asset.get("file_name") or "template.ai"))
        download_asset(self.central, str(dict(config.get("template") or {}).get("template_id") or ""), asset, source)
        selected = selections(preflight)
        labels = output_labels(config)
        output_evidence: list[dict[str, str]] = []
        public_outputs: list[dict[str, Any]] = []
        warnings: list[str] = []
        for index, raw_output in enumerate(task.get("outputs", []), start=1):
            key = str(dict(raw_output).get("key") or "").strip()
            if not key or safe_segment(key) != key:
                raise V2TrialRenderError("扫描得到的效果图信息无效，请修正模板标注后重新扫描。", code="v2_trial_output_invalid")
            output_ai = trial_dir / "outputs" / f"{key}.ai"
            preview_png = trial_dir / "outputs" / f"{key}.png"
            warning_file = trial_dir / "outputs" / f"{key}.warnings.json"
            self.renderer.render(task, template_ai=source, output_ai=output_ai, preview_png=preview_png, output_key=key, layout_warning_file=warning_file, values=logical_values(config, row), selections=selected, task_file=trial_dir / "tasks" / f"{key}.json")
            _require_file(output_ai, "样例 AI 文件")
            _require_file(preview_png, "样例效果图")
            output_warnings = read_warnings(warning_file)
            warnings.extend(item for item in output_warnings if item not in warnings)
            output_evidence.append({"key": key, "ai_sha256": sha256_file(output_ai), "png_sha256": sha256_file(preview_png)})
            public_outputs.append({"key": key, "display_name": labels.get(key) or f"效果图 {index}", "preview_url": f"/local/v2/trials/{quote(trial_id, safe='')}/outputs/{quote(key, safe='')}.png", "warnings": output_warnings})
        return {"output_evidence": output_evidence, "public_outputs": public_outputs, "warnings": warnings}

    @staticmethod
    def _evidence(draft: Mapping[str, Any], config: Mapping[str, Any], row: Mapping[str, Any], task: Mapping[str, Any], asset: Mapping[str, Any], result: Mapping[str, Any], font_check: Mapping[str, Any], revision: str) -> dict[str, Any]:
        manifest = dict(draft.get("manifest") or {})
        return {"draft_revision": revision, "template_sha256": str(asset.get("sha256") or "").lower(), "scan_sha256": str(manifest.get("scan_sha256") or "").lower(), "config_sha256": preview_config_sha256(config), "sample_sha256": sample_rows_sha256([row]), "render_task_sha256": str(task.get("task_sha256") or "").lower(), "preview_sha256": preview_outputs_sha256(result["output_evidence"]), "renderer_version": V2_RENDERER_VERSION, "font_check": dict(font_check), "warnings": list(result["warnings"]), "rendered_at": utc_timestamp_now(), "outputs": list(result["output_evidence"])}


def _require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise V2TrialRenderError(f"{label}没有生成，请重新试渲染。", code="v2_trial_output_missing")


def _write_manifest(directory: Path, outputs: list[Mapping[str, Any]]) -> None:
    payload = {"outputs": [{"key": str(item.get("key") or ""), "file_name": f"{safe_segment(str(item.get('key') or ''))}.png"} for item in outputs]}
    (directory / "trial.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_compile_message(exc: BaseException) -> str:
    message = str(exc).strip()
    return message if message and not any(marker in message for marker in (":\\", "Traceback", "$.")) else "当前配置与扫描结果不一致，请重新扫描并保存后再试。"


def _safe_name(value: str) -> str:
    name = Path(value or "template.ai").name
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in name).strip("._") or "template.ai"


__all__ = ["V2TrialRenderError", "V2TrialRenderService"]
