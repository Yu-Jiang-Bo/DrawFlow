"""Integrity and validation helpers for V2 publication orchestration."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping

from .v2_preview_proof import V2PreviewProofError
from .v2_template_api_support import V2TemplateApiError
from .v2_template_store_utils import sha256_file


def verified_payload_sha(api: Any, template_id: str, draft: Mapping[str, Any], name: str) -> str:
    manifest = dict(draft.get("manifest") or {})
    expected = str(manifest.get(f"{name}_sha256") or "").strip().lower()
    revision = str(manifest.get("draft_revision") or "")
    path = api.store._draft_dir(template_id, revision) / f"{name}.json"
    if not path.is_file() or not expected or sha256_file(path) != expected:
        raise V2PreviewProofError("preview_draft_integrity_failed", "当前草稿内容校验未通过。")
    return expected


def verified_asset_path(
    api: Any,
    template_id: str,
    draft: Mapping[str, Any],
    asset: Mapping[str, Any],
) -> Path:
    manifest = dict(draft.get("manifest") or {})
    revision = str(manifest.get("draft_revision") or "")
    root = api.store._draft_dir(template_id, revision).resolve()
    relative = Path(str(asset.get("path") or ""))
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise V2PreviewProofError("preview_asset_invalid", "当前模板 AI 文件登记信息无效。") from exc
    expected = str(asset.get("sha256") or "").strip().lower()
    if relative.is_absolute() or not candidate.is_file() or not expected or sha256_file(candidate) != expected:
        raise V2PreviewProofError("preview_asset_integrity_failed", "当前模板 AI 文件校验未通过。")
    return candidate


def require_revision(draft: Mapping[str, Any], expected: str) -> None:
    current = str(dict(draft.get("manifest") or {}).get("draft_revision") or "")
    if not expected or expected != current:
        raise V2TemplateApiError(
            "v2_draft_revision_conflict",
            "模板草稿已被更新，本次操作未执行。",
            status=HTTPStatus.CONFLICT,
            suggestion="请刷新页面确认最新配置后再重试。",
        )


def mark_preview_pending(validation: dict[str, Any]) -> None:
    issue = {
        "path": "$.preview.evidence",
        "check": "preview",
        "status": "pending",
        "code": "preview_proof_pending",
        "reason": "当前配置还没有通过真实样例渲染，请重新试渲染。",
    }
    issues = validation.setdefault("issues", [])
    if not any(isinstance(item, Mapping) and item.get("code") == issue["code"] for item in issues):
        issues.append(issue)
    check = dict(validation.setdefault("checks", {}).get("preview") or {})
    check_issues = [dict(item) for item in check.get("issues", []) if isinstance(item, Mapping)]
    if not any(item.get("code") == issue["code"] for item in check_issues):
        check_issues.append(issue)
    reasons = [str(item) for item in check.get("reasons", []) if str(item).strip()]
    if issue["reason"] not in reasons:
        reasons.append(issue["reason"])
    validation["checks"]["preview"] = {
        "status": "pending",
        "issues": check_issues,
        "reasons": reasons,
    }
    validation["can_publish"] = False


__all__ = ["mark_preview_pending", "require_revision", "verified_asset_path", "verified_payload_sha"]
