"""V2 template API orchestration with sanitized business responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
import re
from typing import Any, BinaryIO, Mapping
from urllib.parse import unquote
from uuid import uuid4

from .paths import V2_TEMPLATE_DATA_DIR
from .v2_template_api_support import (
    V2TemplateApiError,
    current_asset_sources,
    draft_source_version,
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
from .v2_tail_profile_proof import (
    automatic_tail_profile_coverage_issues,
    scan_needs_trusted_tail_profile_proof,
    tail_profile_issues,
)
from .v2_template_validation import block_validation_with_content_issues
from .v2_template_limits import StreamingWriteGuard, V2TemplateLimitConfig, V2UploadConcurrencyGate
from .v2_template_maintenance import build_maintenance_snapshot, drawing_group_safe_view
from .v2_template_maintenance import require_central_upload_allowed
from .v2_preview_proof import preview_config_payload
from .v2_preview_worker_auth import V2PreviewWorkerChallengeRegistry
from .v2_scan_worker_auth import (
    V2ScanWorkerAuthError,
    V2ScanWorkerChallengeRegistry,
    scan_evidence_sha256,
)
from .template_locks import TEMPLATE_STATE_LOCK
from .v2_template_publication import V2TemplatePublicationService
from .v2_template_store import V2TemplateStore, V2TemplateStoreError
from .v2_template_store_utils import read_json, remove_tree, safe_segment
from .v2_template_transfer import DEFAULT_CHUNK_SIZE, receive_ai_stream
from .v2_template_validation import validate_v2_template_configuration


SCAN_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
V2_WORKBENCH_SERVICE_CONTRACT = {
    "version": 6,
    "capabilities": [
        "mixed_slot_processing",
        "editable_validation_targets",
        "real_preview_proof",
        "draft_asset_download",
        "publication_check",
        "draft_publication",
        "published_template_read",
        "trusted_preview_worker",
        "trusted_tail_profile_scanner",
    ],
}


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
        preview_worker_secret: str | bytes | None = None,
        scan_worker_secret: str | bytes | None = None,
        preview_worker_clock: Any | None = None,
        preview_challenge_ttl_seconds: int = 120,
    ) -> None:
        self.store = store or V2TemplateStore(V2_TEMPLATE_DATA_DIR)
        self.limits = limits or V2TemplateLimitConfig(temp_dir=self.store.root / "_tmp")
        self.upload_gate = upload_gate or V2UploadConcurrencyGate(self.limits)
        self.audit_recorder = audit_recorder or V2AuditRecorder(self.store.root / "audit.jsonl")
        self.preview_worker_auth = V2PreviewWorkerChallengeRegistry(
            preview_worker_secret,
            clock=preview_worker_clock,
            ttl_seconds=preview_challenge_ttl_seconds,
        )
        self.scan_worker_auth = V2ScanWorkerChallengeRegistry(
            scan_worker_secret,
            clock=preview_worker_clock,
            ttl_seconds=preview_challenge_ttl_seconds,
        )
        self.publication = V2TemplatePublicationService(self)

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
            if method == "GET" and action == "published":
                return V2ApiResult({"published": self.read_published(template_id)})
            if method == "POST" and action == "draft-from-published":
                return V2ApiResult(self.create_draft_from_published(template_id), HTTPStatus.CREATED)
            if method == "POST" and action == "draft":
                return V2ApiResult(self.save_draft(template_id, payload or {}))
            if method == "GET" and action == "scan":
                return V2ApiResult(self.read_scan(template_id))
            if method == "POST" and action == "scan":
                return V2ApiResult(self.submit_scan(template_id, payload or {}))
            if method == "POST" and action == "scan-challenge":
                return V2ApiResult(self.scan_challenge(template_id, payload or {}), HTTPStatus.CREATED)
            if method == "POST" and action == "validate":
                return V2ApiResult(self.validate_config(payload or {}))
            if method == "GET" and action == "versions":
                return V2ApiResult(self.read_versions(template_id))
            if method == "POST" and action == "preview-proof":
                return V2ApiResult(self.publication.register_preview_proof(template_id, payload or {}))
            if method == "POST" and action == "preview-challenge":
                return V2ApiResult(self.publication.preview_challenge(template_id, payload or {}), HTTPStatus.CREATED)
            if method == "POST" and action == "publication-check":
                return V2ApiResult(self.publication.publication_check(template_id, payload or {}))
            if method == "POST" and action == "publish":
                return V2ApiResult(self.publication.publish(template_id, payload or {}))
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

    def list_published_templates(self) -> list[dict[str, Any]]:
        return [
            state
            for state in self.list_templates()
            if dict(state.get("publication") or {}).get("status") == "active"
            and str(dict(state.get("publication") or {}).get("current_version") or "").strip()
        ]

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"template_id", "name", "shop_name"})
        template_id = required_text(payload, "template_id", "请填写模板 ID。")
        # Windows template directories are case-insensitive.  Keep lookup and
        # creation under the same lock so a case-only concurrent request cannot
        # replace an existing draft with an empty one.
        with TEMPLATE_STATE_LOCK:
            existing_id = self._casefold_existing_template_id(template_id)
            if existing_id and existing_id != template_id:
                state = self.store.get_state(existing_id)
                return {"template": state["template"], "state": state_summary(state)}
            metadata = metadata_from_payload(template_id, payload, None)
            state = self.store.save_draft(template_id, metadata=metadata)
        self._record_audit("template_created", state)
        return {"template": state["template"], "state": state_summary(state)}

    def _casefold_existing_template_id(self, template_id: str) -> str:
        wanted = str(template_id or "").strip().casefold()
        if not wanted:
            return ""
        for item in self.list_templates():
            existing = str(item.get("template_id") or "").strip()
            if existing and existing.casefold() == wanted:
                return existing
        return ""

    def save_draft(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"name", "shop_name", "config"})
        current = self.store.get_state(template_id)
        metadata = metadata_from_payload(template_id, payload, current)
        config = dict(optional_mapping(payload, "config"))
        current_draft = optional_draft(self.store, template_id)
        scan = dict(current_draft.get("scan", {})) if current_draft else {}
        assets = current_asset_sources(self.store, template_id, current_draft, replace_file_name="")
        self._apply_trusted_scan_audit(config, scan)
        self._require_verified_pua_tail_profiles(config, scan)
        if config:
            config = preview_config_payload(config)
        config, validation = self._prepare_saveable_config(config)
        self._ensure_config_template_matches(template_id, validation)
        state = self.store.save_draft(
            template_id,
            metadata=metadata,
            config=config,
            scan=scan,
            assets=assets,
            source_version=draft_source_version(current_draft),
        )
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
        if config:
            config = preview_config_payload(config)
        headers_by_name = header_map(headers or {})
        asset_role = header(headers_by_name, "x-drawflow-asset-role") or "template"
        require_central_upload_allowed(asset_role)
        scan = {} if asset_role.strip().lower() == "template" else dict(draft.get("scan", {})) if draft else {}
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
                next_state = self.store.save_draft(
                    template_id,
                    metadata=metadata,
                    config=config,
                    scan=scan,
                    assets=assets,
                    source_version=draft_source_version(draft),
                )
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

    def read_version(self, template_id: str, version: str) -> dict[str, Any]:
        try:
            return self.store.read_version(template_id, version)
        except V2TemplateStoreError as exc:
            raise not_found(str(exc)) from exc

    def draft_asset_path(self, template_id: str, file_name: str) -> tuple[Path, dict[str, Any]]:
        return self.publication.draft_asset_path(template_id, file_name)

    def read_draft(self, template_id: str) -> dict[str, Any]:
        try:
            return self.store.read_draft(template_id)
        except V2TemplateStoreError as exc:
            raise not_found(str(exc)) from exc

    def read_published(self, template_id: str) -> dict[str, Any]:
        try:
            return self.store.read_published(template_id)
        except V2TemplateStoreError as exc:
            raise V2TemplateApiError(
                "v2_published_template_unavailable",
                str(exc),
                status=HTTPStatus.NOT_FOUND,
                suggestion="请确认模板已完成发布，或刷新模板列表后重试。",
            ) from exc

    def create_draft_from_published(self, template_id: str) -> dict[str, Any]:
        try:
            state = self.store.create_draft_from_version(template_id)
            draft = self.store.read_draft(template_id)
        except V2TemplateStoreError as exc:
            raise V2TemplateApiError(
                "v2_published_template_unavailable",
                str(exc),
                status=HTTPStatus.NOT_FOUND,
                suggestion="请确认模板已有已发布版本后重试。",
            ) from exc
        self._record_audit("draft_created_from_published", state, draft)
        return {"state": state_summary(state), "draft": draft}

    def read_scan(self, template_id: str) -> dict[str, Any]:
        draft = self.read_draft(template_id)
        return {
            "template_id": template_id,
            "draft_revision": draft["manifest"].get("draft_revision", ""),
            "scan": draft["scan"],
        }

    def submit_scan(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"evidence", "expected_draft_revision", "worker_proof"})
        evidence = optional_mapping(payload, "evidence")
        if "tail_profile_proof" in evidence:
            raise V2TemplateApiError(
                "v2_scan_proof_client_supplied",
                "自动尾巴扫描证明只能由中央服务在验证工作端后写入。",
                suggestion="请通过最新版客户端重新扫描模板。",
            )
        if not evidence:
            raise V2TemplateApiError(
                "v2_scan_evidence_missing",
                "请先完成本地 Illustrator 扫描，再提交扫描证据。",
                suggestion="请重新上传并扫描 .ai 模板，确认扫描完成后再保存结构。",
            )
        if self._has_blocking_scan_issue(evidence):
            raise V2TemplateApiError(
                "v2_scan_evidence_blocked",
                "扫描证据包含阻断问题，不能作为可信结构保存。",
                suggestion="请按扫描提示调整 Template 标注后重新扫描。",
            )
        if not self._has_scan_structure(evidence):
            raise V2TemplateApiError(
                "v2_scan_evidence_empty",
                "扫描证据里没有可用的模板结构，已拒绝保存。",
                suggestion="请通过本地网关重新调用 Illustrator 扫描，不要提交空结构。",
            )
        self._validate_scan_evidence_contract(evidence)
        draft = self.read_draft(template_id)
        asset = self._current_template_ai_asset(draft)
        if not asset:
            raise V2TemplateApiError(
                "v2_template_ai_asset_missing",
                "当前草稿还没有已上传的模板 AI 文件，不能保存扫描证据。",
                suggestion="请先上传 .ai 模板文件，等待文件保存成功后再重新扫描。",
            )
        evidence_sha = self._scan_template_sha256(evidence)
        if not evidence_sha:
            raise V2TemplateApiError(
                "v2_scan_template_sha_missing",
                "扫描证据缺少模板文件哈希，不能绑定到当前草稿。",
                suggestion="请通过本地网关重新扫描已上传的 .ai 模板。",
            )
        asset_sha = str(asset.get("sha256") or "").strip().lower()
        if evidence_sha != asset_sha:
            raise V2TemplateApiError(
                "v2_scan_template_sha_mismatch",
                "扫描证据对应的模板文件与当前草稿里的 AI 文件不一致，已拒绝保存。",
                status=HTTPStatus.CONFLICT,
                suggestion="请重新上传当前 .ai 文件并重新扫描，确保扫描结果来自同一个模板文件。",
            )
        if scan_needs_trusted_tail_profile_proof(evidence):
            coverage_issues = automatic_tail_profile_coverage_issues(evidence)
            if coverage_issues:
                raise V2TemplateApiError(
                    "v2_tail_profile_coverage_missing",
                    "自动尾巴字形缺少完整 a-z 覆盖扫描结果，已拒绝保存。",
                    suggestion="请使用最新版客户端重新扫描当前模板。",
                )
            expected = required_text(
                payload,
                "expected_draft_revision",
                "自动尾巴扫描凭证缺少当前草稿版本，请重新扫描。",
            )
            revision = str(dict(draft.get("manifest") or {}).get("draft_revision") or "").strip()
            if expected != revision:
                raise V2TemplateApiError(
                    "v2_scan_draft_changed",
                    "模板草稿已变化，请重新上传并扫描当前 AI 文件。",
                    status=HTTPStatus.CONFLICT,
                )
            try:
                worker_id = self.scan_worker_auth.verify_and_consume(
                    optional_mapping(payload, "worker_proof"),
                    template_id=template_id,
                    draft_revision=revision,
                    evidence=evidence,
                )
            except V2ScanWorkerAuthError as exc:
                raise self._scan_worker_auth_error(exc) from exc
            evidence = {
                **evidence,
                "tail_profile_proof": {
                    "version": 1,
                    "worker_id": worker_id,
                    "evidence_sha256": scan_evidence_sha256(evidence),
                },
            }
        metadata = metadata_from_state(template_id, self.store.get_state(template_id))
        config = dict(draft.get("config", {}))
        if config:
            config = preview_config_payload(config)
            self._apply_trusted_scan_audit(config, evidence)
            self._require_verified_pua_tail_profiles(config, evidence)
        assets = current_asset_sources(self.store, template_id, draft, replace_file_name="")
        state = self.store.save_draft(
            template_id,
            metadata=metadata,
            config=config,
            scan=evidence,
            assets=assets,
            source_version=draft_source_version(draft),
        )
        next_draft = self.store.read_draft(template_id)
        self._record_audit("scan_submitted", state, next_draft, details={"template_sha256": evidence_sha})
        return {"state": state_summary(state), "draft": next_draft, "scan": next_draft["scan"]}

    def validate_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        config = payload.get("config", payload)
        if not isinstance(config, Mapping):
            raise V2TemplateApiError("v2_config_invalid", "校验内容格式不正确，请刷新页面后重试。")
        controlled_config = self._validation_config(config)
        validation = validate_v2_template_configuration(controlled_config)
        if validation.get("ok"):
            template_id = str(dict(controlled_config.get("template") or {}).get("template_id") or "").strip()
            if template_id:
                try:
                    draft = self.read_draft(template_id)
                except V2TemplateApiError:
                    draft = {}
                validation = block_validation_with_content_issues(
                    validation,
                    tail_profile_issues(controlled_config, dict(draft.get("scan") or {})),
                )
        validation = self.publication.verify_submitted_if_current(controlled_config, validation)
        if validation.get("ok"):
            state = {"template_id": str(dict(validation.get("contract", {}).get("template", {})).get("template_id") or "")}
            self._record_audit("draft_validated", state, details={"can_save": validation.get("can_save", False)})
        return {
            "validation": validation,
            "service_contract": self._service_contract(),
        }

    def read_versions(self, template_id: str) -> dict[str, Any]:
        state = self.store.get_state(template_id)
        return {
            "template_id": state["template_id"],
            "publication": state["publication"],
            "versions": state["versions"],
        }

    def register_preview_proof(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.publication.register_preview_proof(template_id, payload)

    def preview_challenge(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.publication.preview_challenge(template_id, payload)

    def scan_challenge(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"expected_draft_revision", "worker_id"})
        expected = required_text(payload, "expected_draft_revision", "当前草稿版本已缺失，请重新扫描模板。")
        with TEMPLATE_STATE_LOCK:
            draft = self.read_draft(template_id)
            revision = str(dict(draft.get("manifest") or {}).get("draft_revision") or "").strip()
            if expected != revision:
                raise V2TemplateApiError(
                    "v2_scan_draft_changed",
                    "模板草稿已变化，请重新上传并扫描当前 AI 文件。",
                    status=HTTPStatus.CONFLICT,
                )
            try:
                challenge = self.scan_worker_auth.issue(
                    template_id,
                    revision,
                    worker_id=str(payload.get("worker_id") or ""),
                )
            except V2ScanWorkerAuthError as exc:
                raise self._scan_worker_auth_error(exc) from exc
        return {"challenge": challenge, "service_contract": self._service_contract()}

    def publication_check(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.publication.publication_check(template_id, payload)

    def publish(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.publication.publish(template_id, payload)

    def maintenance_snapshot(self) -> dict[str, Any]:
        return build_maintenance_snapshot(self.store.root, limits=self.limits)

    def drawing_group_safe_maintenance(self) -> dict[str, Any]:
        return drawing_group_safe_view(self.maintenance_snapshot())

    def _service_contract(self) -> dict[str, Any]:
        return {
            "version": V2_WORKBENCH_SERVICE_CONTRACT["version"],
            "capabilities": list(V2_WORKBENCH_SERVICE_CONTRACT["capabilities"]),
        }

    def _prepare_saveable_config(self, config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if not config:
            return {}, None
        try:
            controlled_config = sanitize_v2_config(config)
        except V2ApiError as exc:
            raise V2TemplateApiError(
                "v2_config_rejected",
                "配置包含脚本内容、自然语言规则或未开放字段，草稿未保存。",
                suggestion="请删除脚本内容、自然语言规则、未知字段或错误类型后再保存。",
                cause=exc,
            ) from exc
        validation = validate_v2_template_configuration(controlled_config)
        if not validation["can_save"]:
            raise V2TemplateApiError(
                "v2_config_rejected",
                "配置没有通过 V2 白名单契约，草稿未保存。",
                suggestion="请删除脚本、自然语言规则、未知字段或错误类型后再保存。",
            )
        return controlled_config, validation

    def _validation_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return sanitize_v2_config(config)
        except V2ApiError:
            return dict(config)

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
        audit["template_sha256"] = self._scan_template_sha256(scan)
        config["audit"] = audit

    @staticmethod
    def _require_verified_pua_tail_profiles(config: Mapping[str, Any], scan: Mapping[str, Any]) -> None:
        issues = tail_profile_issues(config, scan)
        if not issues:
            return
        raise V2TemplateApiError(
            "v2_tail_profile_unverified",
            "尾巴字形缺少当前模板 AI 的完整字母表扫描证明，草稿未保存。",
            suggestion="请重新扫描当前模板，使用自动识别到的 PUA 尾巴字形后再保存。",
        )

    def _current_template_ai_asset(self, draft: Mapping[str, Any]) -> dict[str, Any]:
        manifest = dict(draft.get("manifest", {}))
        assets = [dict(item) for item in manifest.get("assets", []) if isinstance(item, Mapping)]
        template_assets = [
            item for item in assets
            if str(item.get("role") or "").strip().lower() == "template"
            and str(item.get("extension") or "").strip().lower() == ".ai"
        ]
        if template_assets:
            return template_assets[-1]
        for item in assets:
            file_name = str(item.get("file_name") or item.get("filename") or "").strip().lower()
            extension = str(item.get("extension") or "").strip().lower()
            if file_name == "template.ai" and extension == ".ai":
                return item
        return {}

    def _scan_template_sha256(self, evidence: Mapping[str, Any]) -> str:
        nested = evidence.get("evidence")
        if isinstance(nested, Mapping):
            value = str(nested.get("template_sha256") or "").strip().lower()
            if value:
                return value
        for key in ("template_sha256", "sha256"):
            value = str(evidence.get(key) or "").strip().lower()
            if value:
                return value
        return ""

    def _has_scan_structure(self, evidence: Mapping[str, Any]) -> bool:
        outputs = evidence.get("outputs")
        if not isinstance(outputs, list):
            return False
        return any(
            isinstance(output, Mapping)
            and bool(str(output.get("key") or output.get("path") or "").strip())
            for output in outputs
        )

    def _has_blocking_scan_issue(self, evidence: Mapping[str, Any]) -> bool:
        if evidence.get("blocked") is True:
            return True
        issues = evidence.get("issues")
        if not isinstance(issues, list):
            return False
        blocking = {"blocked", "blocking", "failed", "error"}
        return any(
            isinstance(issue, Mapping)
            and str(issue.get("status") or issue.get("severity") or "").strip().lower() in blocking
            for issue in issues
        )

    def _validate_scan_evidence_contract(self, evidence: Mapping[str, Any]) -> None:
        nested = evidence.get("evidence")
        if evidence.get("$schema") != "custom-renderer/v2-template-scan" or not isinstance(nested, Mapping):
            raise self._invalid_scan_evidence()
        if not self._protocol_version_ok(evidence.get("scan_protocol_version")):
            raise self._invalid_scan_evidence()
        if not self._protocol_version_ok(nested.get("scan_protocol_version")):
            raise self._invalid_scan_evidence()
        if not self._illustrator_version_ok(nested.get("illustrator_version")):
            raise self._invalid_scan_evidence()
        if not self._scanned_at_ok(nested.get("scanned_at")):
            raise self._invalid_scan_evidence()
        digest = str(nested.get("object_path_digest") or "").strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise self._invalid_scan_evidence()

    def _invalid_scan_evidence(self) -> V2TemplateApiError:
        return V2TemplateApiError(
            "v2_scan_evidence_invalid",
            "扫描证据缺少可信协议字段，已拒绝保存。",
            suggestion="请通过本地网关重新调用 Illustrator 扫描，不要提交手写结构。",
        )

    @staticmethod
    def _scan_worker_auth_error(exc: V2ScanWorkerAuthError) -> V2TemplateApiError:
        if exc.code == "scan_worker_secret_missing":
            return V2TemplateApiError(
                "v2_scan_worker_unavailable",
                "自动尾巴扫描服务尚未完成安全配置，请联系维护人员。",
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        return V2TemplateApiError(
            "v2_scan_worker_rejected",
            "自动尾巴扫描凭证无效或已失效，请重新扫描。",
            suggestion="请使用最新版客户端重新扫描当前模板。",
        )

    def _protocol_version_ok(self, value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return int(value) == 1 and float(value) == 1.0
        return str(value or "").strip() in {"1", "1.0"}

    def _illustrator_version_ok(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        parts = text.split(".")
        return bool(parts) and all(part.isdigit() for part in parts)

    def _scanned_at_ok(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not SCAN_TIMESTAMP_PATTERN.fullmatch(text):
            return False
        try:
            datetime.fromisoformat(text[:-1] + "+00:00")
        except ValueError:
            return False
        return True

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
