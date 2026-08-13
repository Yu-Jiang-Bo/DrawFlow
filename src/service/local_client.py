"""Public facade and orchestration for the local DrawFlow client."""

from __future__ import annotations

import hashlib
import http.client  # Re-exported for existing transport monkeypatches.
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from src.renderer.illustrator_bridge import IllustratorBridge
from src.renderer.v2_template_renderer import V2TemplateRenderer

from .job_store import JobStore
from .local_central_client import HttpCentralClient
from .local_client_errors import (
    LocalClientError,
    central_error_detail,
    template_sync_error,
)
from .local_scan_client import save_v2_scan_ai, scan_and_import
from .local_scan_support import (
    blocked_scan_message,
    has_upload_body,
    is_v2_scan_request,
    safe_file_name,
    upload_bytes,
    upload_path_or_saved_copy,
)
from .local_template_cache import (
    CachedTemplate,
    LocalTemplateCache,
    safe_segment,
    template_sha256,
)
from .paths import LOCAL_DRAWFLOW_DIR
from .render_service import RenderService, RenderServiceError
from .template_inspector import TemplateInspector
from .v2_template_scanner import V2TemplateScanner
from .v2_trial_render import V2TrialRenderError, V2TrialRenderService
from .v2_trial_render_support import missing_required_fonts


class LocalDrawFlowClient:
    """Coordinates local cache, Illustrator work, and central metadata APIs."""

    def __init__(
        self,
        central: Any,
        data_dir: Path | str = LOCAL_DRAWFLOW_DIR,
        *,
        inspector: TemplateInspector | None = None,
        v2_scanner: Any | None = None,
        v2_renderer: Any | None = None,
        font_dirs: list[Path] | None = None,
        preview_worker_secret: str | bytes | None = None,
        preview_worker_id: str = "",
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.cache = LocalTemplateCache(central, self.data_dir)
        self.jobs = JobStore(self.data_dir / "jobs")
        self.inspector = inspector or TemplateInspector()
        self.v2_scanner = v2_scanner or V2TemplateScanner()
        self.v2_renderer = v2_renderer or V2TemplateRenderer(
            bridge=IllustratorBridge(
                visible=False,
                fresh_instance=True,
                quit_after=True,
            )
        )
        self.font_dirs = font_dirs
        self.preview_worker_secret = (
            preview_worker_secret
            if preview_worker_secret is not None
            else os.environ.get("DRAWFLOW_PREVIEW_WORKER_SECRET", "")
        )
        configured_worker = preview_worker_id or os.environ.get(
            "DRAWFLOW_PREVIEW_WORKER_ID",
            "drawflow-local",
        )
        self.preview_worker_id = str(configured_worker).strip() or "drawflow-local"

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "role": "local-client",
            "template_cache": str(self.cache.templates_dir),
            "jobs": str(self.data_dir / "jobs"),
            "central": getattr(self.central, "base_url", "in-process"),
            "illustrator": "checked_on_scan_or_render",
        }

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id") or "").strip()
        if not template_id:
            raise LocalClientError("缺少 template_id", code="missing_template_id")
        cached = self.cache.ensure_template(template_id)
        missing_fonts = missing_required_fonts(
            cached.manifest.get("required_fonts", []),
            self.font_dirs,
        )
        if missing_fonts:
            raise LocalClientError(
                "本机缺少模板字体：" + "、".join(missing_fonts),
                code="missing_required_fonts",
            )
        try:
            record = RenderService(
                registry=self.cache.registry(),
                jobs=self.jobs,
            ).submit({
                **payload,
                "template_id": template_id,
                "template_version": cached.version,
                "template_sha256": template_sha256(cached.manifest),
            })
        except RenderServiceError as exc:
            raise LocalClientError(str(exc), code=exc.code) from exc
        if record.get("status") == "failed":
            raise LocalClientError(
                str(record.get("error") or "渲染失败"),
                code=str(record.get("error_code") or "render_failed"),
            )
        record["template_cache"] = {
            "version": cached.version,
            "cache_hit": cached.cache_hit,
            "sha256": template_sha256(cached.manifest),
        }
        return record

    def trial_render(
        self,
        template_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._trial_service().render(template_id, payload)
        except V2TrialRenderError as exc:
            raise LocalClientError(
                str(exc),
                code=exc.code,
                technical_message=exc.technical_message,
            ) from exc

    def trial_preview_path(self, trial_id: str, output_key: str) -> Path:
        try:
            return self._trial_service().preview_path(trial_id, output_key)
        except V2TrialRenderError as exc:
            raise LocalClientError(
                str(exc),
                code=exc.code,
                technical_message=exc.technical_message,
            ) from exc

    def _trial_service(self) -> V2TrialRenderService:
        return V2TrialRenderService(
            self.central,
            self.data_dir,
            self.v2_renderer,
            self.font_dirs,
            self.preview_worker_secret,
            self.preview_worker_id,
        )

    def scan_and_import(
        self,
        fields: Mapping[str, str],
        uploads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return scan_and_import(self, fields, uploads)

    def _scan_v2_and_submit(
        self,
        fields: Mapping[str, str],
        uploads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # Compatibility hook retained for callers that explicitly select V2 scan.
        return scan_and_import(self, {**fields, "scan_contract_version": "v2"}, uploads)

    def _save_v2_scan_ai(
        self,
        template_id: str,
        filename: str,
        content: bytes,
    ) -> Path:
        return save_v2_scan_ai(self, template_id, filename, content)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def quote_segment(value: str) -> str:
    return quote(value, safe="")


_has_upload_body = has_upload_body
_is_v2_scan_request = is_v2_scan_request
_blocked_scan_message = blocked_scan_message


__all__ = [
    "CachedTemplate",
    "HttpCentralClient",
    "LocalClientError",
    "LocalDrawFlowClient",
    "LocalTemplateCache",
    "central_error_detail",
    "quote_segment",
    "safe_file_name",
    "safe_segment",
    "sha256_text",
    "template_sha256",
    "template_sync_error",
    "upload_bytes",
    "upload_path_or_saved_copy",
]
