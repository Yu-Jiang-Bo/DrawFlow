"""V2 template API orchestration with sanitized business responses."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, BinaryIO, Mapping
from urllib.parse import unquote
from uuid import uuid4

from .paths import V2_TEMPLATE_DATA_DIR
from .v2_template_api_support import (
    V2TemplateApiError,
    current_asset_sources,
    ensure_payload_fields,
    find_asset,
    handle_v2_template_api,
    header,
    header_map,
    metadata_from_payload,
    metadata_from_state,
    not_found,
    optional_draft,
    optional_mapping,
    required_text,
    state_summary,
)
from .v2_template_audit import V2AuditRecorder, audit_event_from_state
from .v2_template_errors import V2ApiError, sanitize_v2_config
from .v2_template_limits import StreamingWriteGuard, V2TemplateLimitConfig, V2UploadConcurrencyGate
from .v2_template_maintenance import build_maintenance_snapshot, drawing_group_safe_view
from .v2_template_maintenance import require_central_upload_allowed
from .v2_template_store import V2TemplateStore, V2TemplateStoreError
from .v2_template_store_utils import read_json, remove_tree, safe_segment
from .v2_template_transfer import DEFAULT_CHUNK_SIZE, receive_ai_stream
from .v2_template_validation import validate_v2_template_configuration


@dataclass(frozen=True)
class V2ApiResult:
    payload: dict[str, Any]
    status: HTTPStatus = HTTPStatus.OK


class V2TemplateApi:
    def __init__(
        self,
        store: V2TemplateStore | None = None,
        *,
        limits: V2TemplateLimitConfig | None = None,
        upload_gate: V2UploadConcurrencyGate | None = None,
        audit_recorder: V2AuditRecorder | None = None,
    ) -> None:
        self.store = store or V2TemplateStore(V2_TEMPLATE_DATA_DIR)
        self.limits = limits or V2TemplateLimitConfig(temp_dir=self.store.root / "_tmp")
        self.upload_gate = upload_gate or V2UploadConcurrencyGate(self.limits)
        self.audit_recorder = audit_recorder or V2AuditRecorder(self.store.root / "audit.jsonl")

    def handle(self, method: str, parts: list[str], payload: Mapping[str, Any] | None = None) -> V2ApiResult:
        if len(parts) == 3 and parts == ["api", "v2", "templates"]:
            if method == "GET":
                return V2ApiResult({"templates": self.list_templates()})
            if method == "POST":
                return V2ApiResult(self.create_template(payload or {}), HTTPStatus.CREATED)
        if len(parts) == 4 and parts == ["api", "v2", "templates", "maintenance"]:
            if method == "GET":
                return V2ApiResult({"maintenance": self.drawing_group_safe_maintenance()})
        if len(parts) == 5 and parts[:3] == ["api", "v2", "templates"]:
            template_id = unquote(parts[3])
            action = parts[4]
            if method == "GET" and action == "draft":
                return V2ApiResult({"draft": self.read_draft(template_id)})
            if method == "POST" and action == "draft":
                return V2ApiResult(self.save_draft(template_id, payload or {}))
            if method == "GET" and action == "scan":
                return V2ApiResult(self.read_scan(template_id))
            if method == "POST" and action == "validate":
                return V2ApiResult(self.validate_config(payload or {}))
            if method == "GET" and action == "versions":
                return V2ApiResult(self.read_versions(template_id))
        raise V2TemplateApiError(
            "v2_route_not_found",
            "请求的 V2 模板接口不存在。",
            status=HTTPStatus.NOT_FOUND,
            suggestion="请使用 /api/v2/templates 及其草稿、扫描、校验、版本或资产子接口。",
        )

    def list_templates(self) -> list[dict[str, Any]]:
        if not self.store.root.exists():
            return []
        states = []
        for state_path in sorted(self.store.root.glob("*/state.json")):
            states.append(state_summary(read_json(state_path)))
        return states

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"template_id", "name", "shop_name"})
        template_id = required_text(payload, "template_id", "请填写模板 ID。")
        metadata = metadata_from_payload(template_id, payload, None)
        state = self.store.save_draft(template_id, metadata=metadata)
        self._record_audit("template_created", state)
        return {"template": state["template"], "state": state_summary(state)}

    def save_draft(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"name", "shop_name", "config"})
        current = self.store.get_state(template_id)
        metadata = metadata_from_payload(template_id, payload, current)
        config = dict(optional_mapping(payload, "config"))
        current_draft = optional_draft(self.store, template_id)
        scan = dict(current_draft.get("scan", {})) if current_draft else {}
        self._apply_trusted_scan_audit(config, scan)
        config, validation = self._prepare_saveable_config(config)
        self._ensure_config_template_matches(template_id, validation)
        state = self.store.save_draft(template_id, metadata=metadata, config=config, scan=scan)
        draft = self.store.read_draft(template_id)
        self._record_audit("draft_saved", state, draft)
        return {
            "state": state_summary(state),
            "draft": draft,
            "validation": validation,
        }

    def upload_asset(
        self,
        template_id: str,
        file_name: str,
        source: BinaryIO,
        *,
        content_length: int | None = None,
        headers: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.store.get_state(template_id)
        metadata = metadata_from_state(template_id, state)
        draft = optional_draft(self.store, template_id)
        config = dict(draft.get("config", {})) if draft else {}
        scan = dict(draft.get("scan", {})) if draft else {}
        headers_by_name = header_map(headers or {})
        asset_role = header(headers_by_name, "x-drawflow-asset-role") or "template"
        require_central_upload_allowed(asset_role)
        safe_id = safe_segment(template_id)
        if not safe_id:
            raise V2TemplateApiError("v2_template_not_found", "模板 ID 不合法，无法上传资产。", status=HTTPStatus.NOT_FOUND)
        upload_dir = self.limits.temp_dir / "uploads" / safe_id / uuid4().hex
        upload_path = upload_dir / file_name
        guard = StreamingWriteGuard(
            upload_path,
            config=self.limits,
            expected_size_bytes=content_length,
        )
        guard.preflight()
        try:
            with self.upload_gate.acquire():
                upload_record = receive_ai_stream(
                    source,
                    upload_dir,
                    file_name,
                    role=asset_role,
                    scan_version=header(headers_by_name, "x-drawflow-scan-version") or str(scan.get("scan_version") or ""),
                    draft_version=str(dict(state.get("draft") or {}).get("revision") or ""),
                    mime_type=header(headers_by_name, "content-type"),
                    chunk_size=DEFAULT_CHUNK_SIZE,
                    on_chunk=guard.record_chunk,
                )
                assets = [
                    *current_asset_sources(self.store, template_id, draft, replace_file_name=upload_record["file_name"]),
                    {
                        **upload_record,
                        "filename": upload_record["file_name"],
                        "source_path": upload_dir / upload_record["file_name"],
                    },
                ]
                next_state = self.store.save_draft(template_id, metadata=metadata, config=config, scan=scan, assets=assets)
                next_draft = self.store.read_draft(template_id)
                self._record_audit("asset_uploaded", next_state, next_draft, details={"file_name": upload_record["file_name"]})
                return {
                    "state": state_summary(next_state),
                    "asset": find_asset(next_draft["manifest"], upload_record["file_name"]),
                    "draft": next_draft,
                }
        finally:
            remove_tree(upload_dir)

    def version_bundle_path(self, template_id: str, version: str) -> Path:
        return self.store.version_bundle_path(template_id, version)

    def read_draft(self, template_id: str) -> dict[str, Any]:
        try:
            return self.store.read_draft(template_id)
        except V2TemplateStoreError as exc:
            raise not_found(str(exc)) from exc

    def read_scan(self, template_id: str) -> dict[str, Any]:
        draft = self.read_draft(template_id)
        return {
            "template_id": template_id,
            "draft_revision": draft["manifest"].get("draft_revision", ""),
            "scan": draft["scan"],
        }

    def validate_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        config = payload.get("config", payload)
        if not isinstance(config, Mapping):
            raise V2TemplateApiError("v2_config_invalid", "校验内容必须是 JSON 对象。")
        validation = validate_v2_template_configuration(dict(config))
        if validation.get("ok"):
            state = {"template_id": str(dict(validation.get("contract", {}).get("template", {})).get("template_id") or "")}
            self._record_audit("draft_validated", state, details={"can_save": validation.get("can_save", False)})
        return {"validation": validation}

    def read_versions(self, template_id: str) -> dict[str, Any]:
        state = self.store.get_state(template_id)
        return {
            "template_id": state["template_id"],
            "publication": state["publication"],
            "versions": state["versions"],
        }

    def maintenance_snapshot(self) -> dict[str, Any]:
        return build_maintenance_snapshot(self.store.root, limits=self.limits)

    def drawing_group_safe_maintenance(self) -> dict[str, Any]:
        return drawing_group_safe_view(self.maintenance_snapshot())

    def _prepare_saveable_config(self, config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if not config:
            return {}, None
        try:
            sanitize_v2_config(config)
        except V2ApiError as exc:
            raise V2TemplateApiError(
                "v2_config_rejected",
                "配置包含脚本、JSX、自然语言规则或未开放字段，草稿未保存。",
                suggestion="请删除脚本、自然语言规则、未知字段或错误类型后再保存。",
                cause=exc,
            ) from exc
        controlled_config = dict(config)
        validation = validate_v2_template_configuration(controlled_config)
        if not validation["can_save"]:
            raise V2TemplateApiError(
                "v2_config_rejected",
                "配置没有通过 V2 白名单契约，草稿未保存。",
                suggestion="请删除脚本、自然语言规则、未知字段或错误类型后再保存。",
            )
        return controlled_config, validation

    def _ensure_config_template_matches(self, template_id: str, validation: Mapping[str, Any] | None) -> None:
        if not validation:
            return
        contract = validation.get("contract")
        template = contract.get("template", {}) if isinstance(contract, Mapping) else {}
        config_template_id = str(dict(template).get("template_id") or "").strip()
        if config_template_id and config_template_id != template_id:
            raise V2TemplateApiError(
                "v2_template_id_mismatch",
                "配置中的模板 ID 与当前草稿模板 ID 不一致，草稿未保存。",
                suggestion="请确认 URL 中的模板 ID 和配置 template.template_id 使用同一个值。",
            )

    def _apply_trusted_scan_audit(self, config: dict[str, Any], scan: Mapping[str, Any]) -> None:
        if not config:
            return
        audit = dict(config.get("audit") or {})
        audit["scan_version"] = str(scan.get("scan_version") or scan.get("version") or "")
        audit["template_sha256"] = str(scan.get("template_sha256") or scan.get("sha256") or "")
        config["audit"] = audit

    def _record_audit(
        self,
        event: str,
        state: Mapping[str, Any],
        draft: Mapping[str, Any] | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            self.audit_recorder.append(audit_event_from_state(event, state, draft, details=details or {}))
        except OSError:
            pass

__all__ = ["V2TemplateApi", "V2TemplateApiError", "handle_v2_template_api"]
