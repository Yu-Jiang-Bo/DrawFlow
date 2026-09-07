"""Support helpers for the V2 template API bridge."""

from __future__ import annotations

from http import HTTPStatus
import logging
from typing import Any, Mapping
from urllib.parse import unquote

from .v2_template_errors import V2ApiError, status_for_code
from .v2_template_limits import V2TemplateLimitError
from .v2_template_maintenance import V2TemplateMaintenanceError
from .v2_template_store import V2TemplateStore, V2TemplateStoreError
from .v2_template_api_streams import handle_v2_template_stream
from .v2_template_transfer import TransferError


LOGGER = logging.getLogger("drawflow.v2_template_api")


class V2TemplateApiError(V2ApiError):
    def to_payload(self) -> dict[str, str]:
        return self.to_response_payload()


class ContentLengthReader:
    """Read at most the declared HTTP request body length."""

    def __init__(self, source: Any, remaining: int) -> None:
        self.source = source
        self.remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        bounded = self.remaining if size is None or size < 0 else min(int(size), self.remaining)
        chunk = self.source.read(bounded)
        if chunk == b"" and self.remaining > 0:
            raise OSError("request body ended before Content-Length bytes were read")
        self.remaining -= len(chunk)
        return chunk


def handle_v2_template_api(handler: Any, method: str, path: str, parts: list[str]) -> bool:
    if len(parts) < 3 or parts[:3] != ["api", "v2", "templates"]:
        return False
    try:
        if method == "POST" and len(parts) == 6 and parts[:3] == ["api", "v2", "templates"] and parts[4] == "assets":
            content_length = _required_content_length(handler.headers)
            result = handler.v2_template_api.upload_asset(
                unquote(parts[3]),
                unquote(parts[5]),
                ContentLengthReader(handler.rfile, content_length),
                content_length=content_length,
                headers=handler.headers,
            )
            handler._send_json(result, HTTPStatus.CREATED)
            return True
        if handle_v2_template_stream(handler, method, parts):
            return True
        payload = handler._read_json() if method == "POST" else None
        result = handler.v2_template_api.handle(method, parts, payload)
        handler._send_json(result.payload, result.status)
    except Exception as exc:
        error = _public_error(exc)
        _log_v2_api_error(error, exc, method, path)
        handler._send_json({"error": error.to_response_payload()}, error.status)
    return True


def metadata_from_payload(
    template_id: str,
    payload: Mapping[str, Any],
    current_state: Mapping[str, Any] | None,
) -> dict[str, str]:
    template = current_state.get("template", {}) if isinstance(current_state, Mapping) else {}
    name = str(payload.get("name") or dict(template).get("name") or "").strip()
    if not name:
        raise V2TemplateApiError("v2_template_name_required", "请填写模板名称。")
    return {
        "template_id": template_id,
        "name": name,
        "shop_name": str(payload.get("shop_name") or dict(template).get("shop_name") or "").strip(),
    }


def metadata_from_state(template_id: str, state: Mapping[str, Any]) -> dict[str, str]:
    template = dict(state.get("template", {}))
    if not str(template.get("name") or "").strip():
        raise not_found("模板草稿不存在，请先创建模板再上传资产。")
    return metadata_from_payload(template_id, template, state)


def optional_mapping(payload: Mapping[str, Any], key: str, fallback_key: str = "") -> dict[str, Any]:
    value = payload.get(key, payload.get(fallback_key, {})) if fallback_key else payload.get(key, {})
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise V2TemplateApiError("v2_payload_invalid", f"{key} 内容格式不正确，请刷新页面后重试。")
    return dict(value)


def optional_draft(store: V2TemplateStore, template_id: str) -> dict[str, Any] | None:
    try:
        return store.read_draft(template_id)
    except V2TemplateStoreError:
        return None


def draft_source_version(draft: Mapping[str, Any] | None) -> str:
    manifest = draft.get("manifest") if isinstance(draft, Mapping) else None
    return str(manifest.get("source_version") or "").strip() if isinstance(manifest, Mapping) else ""


def draft_allows_legacy_render_mode(draft: Mapping[str, Any] | None) -> bool:
    manifest = draft.get("manifest") if isinstance(draft, Mapping) else None
    if not isinstance(manifest, Mapping) or not manifest:
        return False
    if "legacy_render_mode_allowed" not in manifest:
        return True
    return manifest.get("legacy_render_mode_allowed") is True


def current_asset_sources(
    store: V2TemplateStore,
    template_id: str,
    draft: Mapping[str, Any] | None,
    *,
    replace_file_name: str,
) -> list[dict[str, Any]]:
    if not draft:
        return []
    manifest = dict(draft.get("manifest", {}))
    draft_revision = str(manifest.get("draft_revision") or "")
    draft_dir = store._draft_dir(template_id, draft_revision)
    assets = []
    for item in manifest.get("assets", []):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("file_name") or "") == replace_file_name:
            continue
        assets.append({
            **dict(item),
            "filename": str(item.get("file_name") or ""),
            "source_path": draft_dir / str(item.get("path") or ""),
        })
    return assets


def find_asset(manifest: Mapping[str, Any], file_name: str) -> dict[str, Any]:
    for item in manifest.get("assets", []):
        if isinstance(item, Mapping) and str(item.get("file_name") or "") == file_name:
            return dict(item)
    return {}


def required_text(payload: Mapping[str, Any], key: str, reason: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise V2TemplateApiError("v2_required_field_missing", reason)
    return value


def ensure_payload_fields(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise V2TemplateApiError(
            "v2_payload_rejected",
            "请求包含未开放的字段，已拒绝处理。",
            suggestion="请只提交当前界面允许编辑的字段后重试。",
        )


def state_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_id": state.get("template_id", ""),
        "template": dict(state.get("template", {})),
        "draft": dict(state["draft"]) if isinstance(state.get("draft"), Mapping) else None,
        "publication": dict(state.get("publication", {})),
        "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
    }


def not_found(reason: str) -> V2TemplateApiError:
    return V2TemplateApiError(
        "v2_template_not_found",
        reason,
        status=HTTPStatus.NOT_FOUND,
        suggestion="请确认模板 ID 是否存在，或先创建模板草稿。",
    )


def header_map(headers: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def header(headers: Mapping[str, str], key: str) -> str:
    return str(headers.get(key.lower()) or "").strip()


def _required_content_length(headers: Mapping[str, Any]) -> int:
    raw = str(headers.get("Content-Length") or headers.get("content-length") or "").strip()
    if not raw:
        raise V2TemplateApiError("v2_payload_rejected", "上传 AI 文件必须提供 Content-Length。")
    try:
        value = int(raw)
    except ValueError as exc:
        raise V2TemplateApiError("v2_payload_rejected", "Content-Length 不是有效数字。") from exc
    if value < 0:
        raise V2TemplateApiError("v2_payload_rejected", "Content-Length 不能为负数。")
    return value


def _public_error(exc: BaseException) -> V2ApiError:
    if isinstance(exc, V2ApiError):
        return exc
    if isinstance(exc, TransferError):
        transfer_status = HTTPStatus(exc.status) if exc.status in {400, 409, 413, 415, 500, 507} else HTTPStatus.BAD_REQUEST
        return V2ApiError(exc.code, exc.reason, status=transfer_status, title=exc.title, suggestion=exc.suggestion, cause=exc)
    if isinstance(exc, V2TemplateLimitError):
        return V2ApiError(
            exc.code,
            exc.reason,
            status=_limit_status(exc.code),
            suggestion="请调整文件大小、等待当前上传完成，或联系维护人员检查磁盘余量后重试。",
            cause=exc,
        )
    if isinstance(exc, V2TemplateMaintenanceError):
        return V2ApiError(
            exc.code,
            exc.reason,
            status=HTTPStatus.BAD_REQUEST,
            suggestion="请只上传模板、配置、扫描或预览审核元数据；正式订单成品请保存在本地任务目录。",
            cause=exc,
        )
    if isinstance(exc, V2TemplateStoreError):
        return V2ApiError("v2_invalid_request", _safe_reason(exc), cause=exc)
    if isinstance(exc, (TypeError, ValueError)):
        return V2ApiError("v2_invalid_request", _safe_reason(exc), cause=exc)
    return V2ApiError.from_exception("v2_internal_error", exc)


def _log_v2_api_error(error: V2ApiError, exc: BaseException, method: str, path: str) -> None:
    context = error.to_log_context()
    context.update({"method": method, "route": path, "cause_chain": _cause_chain(exc)})
    if error.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        LOGGER.exception("v2 api failed: %s", context)
    else:
        # Client-facing 4xx responses can still wrap an I/O failure while a
        # streamed asset is being persisted. Preserve the chained traceback
        # in the service log without exposing filesystem details to clients.
        LOGGER.warning("v2 api rejected: %s", context, exc_info=exc)


def _cause_chain(exc: BaseException) -> list[str]:
    chain = []
    current: BaseException | None = exc
    while current is not None and len(chain) < 8:
        chain.append(type(current).__name__)
        current = current.__cause__
    return chain


def _limit_status(code: str) -> HTTPStatus:
    safe_code = str(code or "")
    if "file_too_large" in safe_code:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    if "disk" in safe_code or "space" in safe_code:
        return HTTPStatus.INSUFFICIENT_STORAGE
    if "concurrency" in safe_code:
        return HTTPStatus.CONFLICT
    return status_for_code(safe_code)


def _safe_reason(exc: BaseException) -> str:
    reason = str(exc).strip() or "请求内容不符合 V2 模板接口要求。"
    for marker in (":\\", "/", "Traceback", "HTTPStatus"):
        if marker in reason:
            return "请求内容不符合 V2 模板接口要求。"
    return reason


__all__ = [
    "V2TemplateApiError",
    "current_asset_sources",
    "ensure_payload_fields",
    "find_asset",
    "handle_v2_template_api",
    "header",
    "header_map",
    "metadata_from_payload",
    "metadata_from_state",
    "not_found",
    "optional_draft",
    "optional_mapping",
    "required_text",
    "state_summary",
]
