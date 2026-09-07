"""Central orchestration for proof-bound V2 preview and publication."""

from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from pathlib import Path
import re
from typing import Any, Mapping

from .template_locks import TEMPLATE_STATE_LOCK
from .v2_preview_proof import (
    V2PreviewProofError,
    compile_preview_render_task,
    expected_preview_output_keys,
    normalize_preview_evidence,
    preview_config_payload,
    preview_config_sha256,
    sample_rows_sha256,
    stable_json_sha256,
    validate_preview_proof_bindings,
)
from .v2_render_task import V2_RENDERER_VERSION, V2RenderTaskError
from .v2_preview_worker_auth import V2PreviewWorkerAuthError
from .v2_template_api_support import (
    V2TemplateApiError,
    current_asset_sources,
    draft_allows_legacy_render_mode,
    draft_source_version,
    ensure_payload_fields,
    metadata_from_state,
    optional_mapping,
    required_text,
)
from .v2_template_store import V2TemplatePublishConflict, V2TemplateStoreError
from .v2_template_publication_support import (
    mark_preview_pending,
    require_revision,
    verified_asset_path,
    verified_payload_sha,
)
from .v2_template_validation import validate_v2_template_configuration
from .v2_template_validation import block_validation_with_content_issues
from .v2_tail_profile_proof import tail_profile_issues


class V2TemplatePublicationService:
    def __init__(self, api: Any) -> None:
        self.api = api

    def draft_asset_path(self, template_id: str, file_name: str) -> tuple[Path, dict[str, Any]]:
        draft = self.api.read_draft(template_id)
        asset = self.api._current_template_ai_asset(draft)
        requested = str(file_name or "").strip()
        registered = str(asset.get("file_name") or asset.get("filename") or "").strip()
        if not requested or requested != registered or Path(requested).name != requested:
            raise V2TemplateApiError(
                "v2_template_ai_asset_missing",
                "当前草稿没有可下载的模板 AI 文件。",
                status=HTTPStatus.NOT_FOUND,
                suggestion="请先上传模板 AI 文件，再执行扫描或样例渲染。",
            )
        try:
            path = verified_asset_path(self.api, template_id, draft, asset)
        except V2PreviewProofError as exc:
            raise V2TemplateApiError(
                "v2_template_ai_asset_invalid",
                "当前草稿的模板 AI 文件校验未通过。",
                status=HTTPStatus.CONFLICT,
                suggestion="请重新上传模板 AI 文件后再试。",
                cause=exc,
            ) from exc
        return path, dict(asset)

    def preview_challenge(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"expected_draft_revision", "worker_id"})
        expected = required_text(payload, "expected_draft_revision", "当前草稿版本已缺失，请重新打开模板后再试。")
        with TEMPLATE_STATE_LOCK:
            draft = self.api.read_draft(template_id)
            require_revision(draft, expected)
            try:
                challenge = self.api.preview_worker_auth.issue(
                    template_id,
                    expected,
                    worker_id=str(payload.get("worker_id") or ""),
                )
            except V2PreviewWorkerAuthError as exc:
                raise self._worker_auth_error(exc) from exc
        return {"challenge": challenge, "service_contract": self.api._service_contract()}

    def register_preview_proof(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"expected_draft_revision", "sample_rows", "evidence", "worker_proof"})
        expected = required_text(payload, "expected_draft_revision", "当前草稿版本已缺失，请重新打开模板后再试。")
        rows = payload.get("sample_rows")
        if not isinstance(rows, list) or not rows or any(not isinstance(row, Mapping) for row in rows):
            raise V2TemplateApiError(
                "v2_preview_sample_invalid",
                "请至少填写一行完整的样例订单数据。",
                suggestion="请按当前模板绑定的订单字段填写样例后重新试渲染。",
            )
        with TEMPLATE_STATE_LOCK:
            draft = self.api.read_draft(template_id)
            require_revision(draft, expected)
            core = preview_config_payload(dict(draft.get("config") or {}), rows)
            self.api._apply_trusted_scan_audit(core, dict(draft.get("scan") or {}))
            core, validation = self.api._prepare_saveable_config(core)
            self.api._ensure_config_template_matches(template_id, validation)
            submitted_evidence = optional_mapping(payload, "evidence")
            try:
                self.api.preview_worker_auth.verify_and_consume(
                    optional_mapping(payload, "worker_proof"),
                    template_id=template_id,
                    draft_revision=expected,
                    sample_rows=rows,
                    evidence=submitted_evidence,
                )
            except (V2PreviewWorkerAuthError, V2PreviewProofError) as exc:
                raise self._worker_auth_error(exc) from exc
            evidence, task = self._verify_evidence(template_id, draft, core, submitted_evidence, expected)
            confirmed = deepcopy(core)
            preview = dict(confirmed.get("preview") or {})
            preview["evidence"] = {**evidence, "draft_revision": expected}
            confirmed["preview"] = preview
            checks = dict(confirmed.get("checks") or {})
            checks["preview"] = {"status": "confirmed", "reason": "真实样例渲染已通过。"}
            confirmed["checks"] = checks
            confirmed, _ = self.api._prepare_saveable_config(confirmed)
            metadata = metadata_from_state(template_id, self.api.store.get_state(template_id))
            assets = current_asset_sources(self.api.store, template_id, draft, replace_file_name="")
            state = self.api.store.save_draft(
                template_id,
                metadata=metadata,
                config=confirmed,
                scan=dict(draft.get("scan") or {}),
                assets=assets,
                source_version=draft_source_version(draft),
            )
            next_draft = self.api.store.read_draft(template_id)
            result = self.publication_validation(template_id, next_draft)
            self.api._record_audit(
                "preview_proof_registered", state, next_draft, details={"render_task_sha256": task["task_sha256"]}
            )
            return {
                "draft": next_draft,
                "validation": result,
                "publication": dict(state.get("publication") or {}),
                "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
            }

    def publication_check(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"expected_draft_revision"})
        with TEMPLATE_STATE_LOCK:
            draft = self.api.read_draft(template_id)
            expected = str(payload.get("expected_draft_revision") or "").strip()
            if expected:
                require_revision(draft, expected)
            state = self.api.store.get_state(template_id)
            return {
                "template_id": template_id,
                "draft_revision": str(dict(draft.get("manifest") or {}).get("draft_revision") or ""),
                "validation": self.publication_validation(template_id, draft),
                "publication": dict(state.get("publication") or {}),
                "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
                "service_contract": self.api._service_contract(),
            }

    def publish(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        ensure_payload_fields(payload, {"expected_draft_revision", "note"})
        expected = required_text(payload, "expected_draft_revision", "当前草稿版本已缺失，请重新打开模板后再发布。")
        with TEMPLATE_STATE_LOCK:
            draft = self.api.read_draft(template_id)
            require_revision(draft, expected)
            validation = self.publication_validation(template_id, draft)
            if not validation.get("can_publish"):
                raise V2TemplateApiError(
                    "v2_publication_blocked",
                    "当前模板仍有未完成的发布核验项，暂时不能发布。",
                    status=HTTPStatus.CONFLICT,
                    suggestion="请按发布核验中的提示完成修改，并重新试渲染后再发布。",
                )
            try:
                state = self.api.store.publish_draft(
                    template_id,
                    note=str(payload.get("note") or "").strip(),
                    expected_revision=expected,
                )
            except V2TemplatePublishConflict as exc:
                raise V2TemplateApiError(
                    "v2_draft_revision_conflict",
                    "该草稿修订已经发布，当前正式版本已变化，本次没有重复发布。",
                    status=HTTPStatus.CONFLICT,
                    suggestion="请刷新页面确认当前正式版本后再继续。",
                    cause=exc,
                ) from exc
            version = str(dict(state.get("publication") or {}).get("current_version") or "")
            self.api._record_audit("draft_published", state, draft, details={"version": version})
            return {
                "template_id": template_id,
                "version": version,
                "publication": dict(state.get("publication") or {}),
                "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
                "validation": validation,
            }

    def publication_validation(self, template_id: str, draft: Mapping[str, Any]) -> dict[str, Any]:
        config = dict(draft.get("config") or {})
        validation = validate_v2_template_configuration(
            config,
            legacy_render_mode_allowed=draft_allows_legacy_render_mode(draft),
        )
        validation = block_validation_with_content_issues(
            validation,
            tail_profile_issues(config, dict(draft.get("scan") or {})),
        )
        if validation.get("ok"):
            try:
                self._verify_current(template_id, draft)
            except V2TemplateApiError:
                mark_preview_pending(validation)
        return validation

    def verify_submitted_if_current(self, config: Mapping[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        if not validation.get("ok"):
            return validation
        evidence = dict(config.get("preview") or {}).get("evidence")
        if not isinstance(evidence, Mapping) or not evidence:
            return validation
        contract = validation.get("contract")
        template = dict(contract.get("template") or {}) if isinstance(contract, Mapping) else {}
        template_id = str(template.get("template_id") or "").strip()
        try:
            draft = self.api.read_draft(template_id)
            if stable_json_sha256(config) != stable_json_sha256(dict(draft.get("config") or {})):
                raise V2PreviewProofError("preview_proof_stale", "当前填写内容尚未完成真实试渲染。")
            self._verify_current(template_id, draft)
        except (V2TemplateApiError, V2PreviewProofError, V2TemplateStoreError):
            mark_preview_pending(validation)
        return validation

    def _verify_current(self, template_id: str, draft: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        config = dict(draft.get("config") or {})
        evidence = dict(config.get("preview") or {}).get("evidence")
        if not isinstance(evidence, Mapping) or not evidence:
            raise V2TemplateApiError("v2_preview_proof_missing", "当前模板还没有有效的真实样例渲染结果。")
        source = str(evidence.get("draft_revision") or "").strip()
        if not re.fullmatch(r"d\d{4}", source) or not self.api.store._draft_dir(template_id, source).is_dir():
            raise V2TemplateApiError("v2_preview_proof_invalid", "当前样例渲染对应的草稿版本已不可用。")
        return self._verify_evidence(template_id, draft, preview_config_payload(config), evidence, source)

    def _verify_evidence(
        self,
        template_id: str,
        draft: Mapping[str, Any],
        core: Mapping[str, Any],
        evidence: Mapping[str, Any],
        source: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            proof = normalize_preview_evidence(evidence)
            if proof["renderer_version"] != V2_RENDERER_VERSION:
                raise V2PreviewProofError("preview_renderer_stale", "样例渲染器版本已变化。")
            asset = self.api._current_template_ai_asset(draft)
            verified_asset_path(self.api, template_id, draft, asset)
            scan_sha = verified_payload_sha(self.api, template_id, draft, "scan")
            verified_payload_sha(self.api, template_id, draft, "config")
            task = compile_preview_render_task(draft, core, proof["font_check"], template_version=source)
            rows = list(dict(core.get("preview") or {}).get("sample_rows") or [])
            verified = validate_preview_proof_bindings(
                proof,
                template_sha256=str(asset.get("sha256") or ""),
                scan_sha256=scan_sha,
                config_sha256=preview_config_sha256(core),
                sample_sha256=sample_rows_sha256(rows),
                render_task_sha256=str(task.get("task_sha256") or ""),
                output_keys=expected_preview_output_keys(task),
            )
            return verified, task
        except (V2PreviewProofError, V2RenderTaskError, TypeError, ValueError) as exc:
            raise V2TemplateApiError(
                "v2_preview_proof_rejected",
                "样例渲染结果与当前模板、配置、扫描或样例数据不一致，已拒绝使用。",
                status=HTTPStatus.CONFLICT,
                suggestion="请保存当前配置，并使用当前样例数据重新试渲染。",
                cause=exc,
            ) from exc

    @staticmethod
    def _worker_auth_error(exc: BaseException) -> V2TemplateApiError:
        if getattr(exc, "code", "") == "preview_worker_secret_missing":
            return V2TemplateApiError(
                "v2_preview_worker_unavailable",
                "真实试渲染服务尚未完成安全配置，请联系维护人员。",
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                suggestion="请由维护人员完成可信试渲染工作端配置后重试。",
                cause=exc,
            )
        return V2TemplateApiError(
            "v2_preview_worker_rejected",
            "试渲染凭证无效或已失效，本次结果未被保存。",
            status=HTTPStatus.CONFLICT,
            suggestion="请使用当前草稿和样例数据重新试渲染。",
            cause=exc,
        )


__all__ = ["V2TemplatePublicationService"]
