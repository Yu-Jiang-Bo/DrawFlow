"""Local scan orchestration kept separate from render/cache services."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .local_client_errors import LocalClientError
from .local_scan_support import (
    blocked_scan_message,
    has_upload_body,
    is_v2_scan_request,
    safe_file_name,
    upload_bytes,
    upload_path_or_saved_copy,
)
from .local_template_cache import safe_segment
from .template_onboarding import TemplateOnboardingStore
from .template_registry import TemplateRegistry
from .v2_scan_worker_auth import V2ScanWorkerAuthError, sign_scan_worker_challenge
from .v2_tail_profile_proof import scan_needs_trusted_tail_profile_proof
from .v2_template_scanner import V2TemplateScannerError


def scan_and_import(
    client: Any,
    fields: Mapping[str, str],
    uploads: list[dict[str, Any]],
) -> dict[str, Any]:
    if is_v2_scan_request(fields):
        return _scan_v2_and_submit(client, fields, uploads)
    template_id = str(fields.get("template_id") or "").strip()
    if not template_id:
        raise LocalClientError("缺少 template_id")
    scan_registry = TemplateRegistry(
        client.data_dir / "scan" / "templates.json",
        client.data_dir / "scan" / "templates",
    )
    first = _first_ai(uploads)
    if not first:
        raise LocalClientError("请上传 .ai 模板文件")
    ai_path = scan_registry.save_uploaded_ai(
        template_id,
        str(first["filename"]),
        upload_bytes(first),
    )
    template = scan_registry.upsert_template({
        "template_id": template_id,
        "name": str(fields.get("name") or template_id),
        "template_type": str(fields.get("template_type") or "pure_text"),
        "status": "draft",
        "template_ai": scan_registry.to_config_path(ai_path),
    })
    state = client.inspector.scan(
        template,
        TemplateOnboardingStore(scan_registry.storage_dir),
    )
    return client.central.import_scan({
        "template_id": template_id,
        "name": template.name,
        "template_type": template.template_type,
        "scan": state.get("scan_evidence") or {},
        "files": _encoded_uploads(uploads),
    })


def save_v2_scan_ai(
    client: Any,
    template_id: str,
    filename: str,
    content: bytes,
) -> Path:
    target_dir = (
        client.data_dir / "v2-scan" / safe_segment(template_id) / uuid4().hex
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(content)
    return target


def _scan_v2_and_submit(
    client: Any,
    fields: Mapping[str, str],
    uploads: list[dict[str, Any]],
) -> dict[str, Any]:
    template_id = str(fields.get("template_id") or "").strip()
    if not template_id:
        raise LocalClientError("缺少 template_id", code="missing_template_id")
    first = _first_ai(uploads)
    if not first:
        raise LocalClientError("请上传 .ai 模板文件", code="v2_scan_ai_required")
    filename = safe_file_name(str(first.get("filename") or "template.ai"))
    ai_path = upload_path_or_saved_copy(client, template_id, filename, first)
    try:
        scan = client.v2_scanner.scan(
            template_id=template_id,
            ai_path=ai_path,
            fields=fields,
        )
    except V2TemplateScannerError as exc:
        raise LocalClientError(
            str(exc),
            code=exc.code,
            technical_message=exc.technical_message,
        ) from exc
    except Exception as exc:
        raise LocalClientError(
            "本地 Illustrator 扫描失败，请关闭占用中的窗口后重试；若仍失败，请检查模板是否可以正常打开。",
            code="v2_illustrator_scan_failed",
            technical_message=str(exc),
        ) from exc
    if scan.get("blocked"):
        raise LocalClientError(blocked_scan_message(scan), code="v2_scan_blocked")
    if hasattr(client.central, "upload_v2_asset") and hasattr(
        client.central,
        "submit_v2_scan",
    ):
        client.central.upload_v2_asset(template_id, filename, ai_path)
        if scan_needs_trusted_tail_profile_proof(scan):
            return _submit_trusted_tail_profile_scan(client, template_id, scan)
        return client.central.submit_v2_scan(template_id, scan)
    return client.central.import_scan({
        "template_id": template_id,
        "name": str(fields.get("name") or template_id),
        "shop_name": str(fields.get("shop_name") or ""),
        "template_type": str(fields.get("template_type") or "pure_text"),
        "scan": scan,
        "files": _encoded_uploads([first]),
    })


def _submit_trusted_tail_profile_scan(client: Any, template_id: str, scan: Mapping[str, Any]) -> dict[str, Any]:
    central = client.central
    if not hasattr(central, "get_v2_draft") or not hasattr(central, "request_v2_scan_challenge"):
        raise LocalClientError(
            "中央服务版本过旧，无法验证自动尾巴字形；请先更新中央服务。",
            code="v2_tail_profile_scan_not_supported",
        )
    draft = dict(central.get_v2_draft(template_id))
    revision = str(dict(draft.get("manifest") or {}).get("draft_revision") or "").strip()
    if not revision:
        raise LocalClientError("中央草稿版本无效，请重新上传并扫描模板。", code="v2_scan_draft_invalid")
    worker_id = str(getattr(client, "preview_worker_id", "") or "").strip()
    secret = getattr(client, "scan_worker_secret", "")
    try:
        challenge = central.request_v2_scan_challenge(
            template_id,
            expected_draft_revision=revision,
            worker_id=worker_id,
        )
        proof = sign_scan_worker_challenge(
            secret,
            challenge,
            template_id=template_id,
            draft_revision=revision,
            evidence=scan,
            worker_id=worker_id,
        )
    except V2ScanWorkerAuthError as exc:
        raise LocalClientError(
            "自动尾巴扫描服务尚未完成安全配置，请联系维护人员。",
            code="v2_tail_profile_scanner_unavailable",
            technical_message=f"{exc.code}: {exc}",
        ) from exc
    return central.submit_v2_scan(
        template_id,
        scan,
        expected_draft_revision=revision,
        worker_proof=proof,
    )


def _first_ai(uploads: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in uploads
            if str(item.get("filename", "")).lower().endswith(".ai")
        ),
        None,
    )


def _encoded_uploads(uploads: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "filename": str(item["filename"]),
            "content_base64": base64.b64encode(upload_bytes(item)).decode("ascii"),
        }
        for item in uploads
        if has_upload_body(item)
    ]


__all__ = ["save_v2_scan_ai", "scan_and_import"]
