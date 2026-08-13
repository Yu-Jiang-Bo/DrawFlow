"""Deterministic binding helpers for real V2 preview render evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .v2_render_task import V2_RENDERER_VERSION, compile_v2_render_task


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class V2PreviewProofError(ValueError):
    """Raised when preview evidence cannot be bound to the current draft."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preview_config_payload(
    config: Mapping[str, Any],
    sample_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = deepcopy(dict(config))
    preview = dict(normalized.get("preview") or {})
    if sample_rows is not None:
        preview["sample_rows"] = [deepcopy(dict(row)) for row in sample_rows]
    else:
        preview["sample_rows"] = [
            deepcopy(dict(row))
            for row in preview.get("sample_rows", [])
            if isinstance(row, Mapping)
        ]
    preview["evidence"] = {}
    normalized["preview"] = preview

    checks = dict(normalized.get("checks") or {})
    checks["preview"] = {"status": "pending", "reason": ""}
    normalized["checks"] = checks
    return normalized


def preview_config_sha256(config: Mapping[str, Any]) -> str:
    return stable_json_sha256(preview_config_payload(config))


def sample_rows_sha256(sample_rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = [deepcopy(dict(row)) for row in sample_rows]
    return stable_json_sha256(normalized)


def expected_preview_output_keys(render_task: Mapping[str, Any]) -> list[str]:
    outputs = render_task.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise V2PreviewProofError("preview_output_missing", "当前模板没有可用于样例渲染的效果图。")
    keys: list[str] = []
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, Mapping):
            raise V2PreviewProofError("preview_output_invalid", "样例渲染的效果图信息不完整。")
        key = str(output.get("key") or "").strip()
        if not key or key in seen:
            raise V2PreviewProofError("preview_output_invalid", "样例渲染的效果图信息不完整或重复。")
        seen.add(key)
        keys.append(key)
    return keys


def canonical_preview_outputs(outputs: Any) -> list[dict[str, str]]:
    if not isinstance(outputs, list) or not outputs:
        raise V2PreviewProofError("preview_output_missing", "样例渲染没有返回任何效果图。")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, Mapping):
            raise V2PreviewProofError("preview_output_invalid", "样例渲染结果格式不完整。")
        key = str(output.get("key") or "").strip()
        ai_sha256 = _required_sha256(output.get("ai_sha256"), "样例 AI 文件校验值无效。")
        png_sha256 = _required_sha256(output.get("png_sha256"), "样例效果图校验值无效。")
        if not key or key in seen:
            raise V2PreviewProofError("preview_output_invalid", "样例渲染结果里的效果图编号为空或重复。")
        seen.add(key)
        normalized.append({"key": key, "ai_sha256": ai_sha256, "png_sha256": png_sha256})
    return sorted(normalized, key=lambda item: item["key"])


def preview_outputs_sha256(outputs: Any) -> str:
    """Aggregate every rendered output hash into one preview hash."""

    return stable_json_sha256(canonical_preview_outputs(outputs))


def compile_preview_render_task(
    draft: Mapping[str, Any],
    config: Mapping[str, Any],
    font_check: Mapping[str, Any],
    *,
    template_version: str = "",
) -> dict[str, Any]:
    """Compile the identical proof-bound task on local and central services."""

    manifest = dict(draft.get("manifest") or {})
    scan = draft.get("scan")
    if not isinstance(scan, Mapping):
        raise V2PreviewProofError("preview_scan_missing", "当前草稿缺少可用的模板扫描结果。")
    asset = _current_template_ai_asset(manifest)
    if not asset:
        raise V2PreviewProofError("preview_template_missing", "当前草稿缺少可用的模板 AI 文件。")
    template_sha256 = _required_sha256(asset.get("sha256"), "当前模板文件校验值无效。")
    scan_sha256 = _required_sha256(manifest.get("scan_sha256"), "当前扫描结果校验值无效。")
    core_config = preview_config_payload(config)
    template = dict(core_config.get("template") or {})
    metadata = dict(draft.get("metadata") or {})
    template_id = str(template.get("template_id") or metadata.get("template_id") or "").strip()
    revision = str(template_version or manifest.get("draft_revision") or "").strip()
    if not template_id or not revision:
        raise V2PreviewProofError("preview_draft_invalid", "当前模板草稿信息不完整，请重新打开后再试。")
    config_version = str(dict(core_config.get("audit") or {}).get("config_version") or "")
    return compile_v2_render_task(
        core_config,
        scan,
        template_id=template_id,
        template_version=revision,
        template_sha256=template_sha256,
        config_version=config_version,
        config_sha256=preview_config_sha256(core_config),
        scan_sha256=scan_sha256,
        renderer_version=V2_RENDERER_VERSION,
        font_check=font_check,
    )


def normalize_preview_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Validate proof shape and return its canonical representation."""

    if not isinstance(evidence, Mapping):
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染证据格式无效。")
    allowed = {
        "draft_revision",
        "template_sha256",
        "scan_sha256",
        "config_sha256",
        "sample_sha256",
        "render_task_sha256",
        "preview_sha256",
        "renderer_version",
        "font_check",
        "warnings",
        "rendered_at",
        "outputs",
    }
    if set(evidence) - allowed:
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染证据包含未开放的内容。")
    required_hashes = (
        "template_sha256",
        "scan_sha256",
        "config_sha256",
        "sample_sha256",
        "render_task_sha256",
        "preview_sha256",
    )
    normalized = {
        key: _required_sha256(evidence.get(key), "样例渲染证据校验值无效。")
        for key in required_hashes
    }
    renderer_version = str(evidence.get("renderer_version") or "").strip()
    rendered_at = str(evidence.get("rendered_at") or "").strip()
    if not renderer_version:
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染缺少渲染器版本。")
    if not _valid_utc_timestamp(rendered_at):
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染完成时间无效。")
    font_check = evidence.get("font_check")
    if not isinstance(font_check, Mapping):
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染缺少字体检查结果。")
    missing = font_check.get("missing")
    if font_check.get("ok") is not True or not isinstance(missing, list) or any(not isinstance(item, str) for item in missing):
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染的字体检查未通过。")
    missing_fonts = [str(item).strip() for item in missing if str(item).strip()]
    if missing_fonts:
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染仍缺少模板所需字体。")
    warnings = evidence.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise V2PreviewProofError("preview_proof_invalid", "样例渲染提示格式无效。")
    outputs = canonical_preview_outputs(evidence.get("outputs"))
    aggregate = preview_outputs_sha256(outputs)
    if normalized["preview_sha256"] != aggregate:
        raise V2PreviewProofError("preview_proof_mismatch", "样例效果图汇总校验未通过，请重新试渲染。")
    normalized.update(
        {
            "renderer_version": renderer_version,
            "font_check": {"ok": True, "missing": []},
            "warnings": [str(item).strip() for item in warnings if str(item).strip()],
            "rendered_at": rendered_at,
            "outputs": outputs,
        }
    )
    return normalized


def validate_preview_proof_bindings(
    evidence: Mapping[str, Any],
    *,
    template_sha256: str,
    scan_sha256: str,
    config_sha256: str,
    sample_sha256: str,
    render_task_sha256: str,
    output_keys: Sequence[str],
) -> dict[str, Any]:
    """Validate every binding that makes a proof current-draft specific."""

    normalized = normalize_preview_evidence(evidence)
    expected = {
        "template_sha256": _required_sha256(template_sha256, "当前模板文件校验值无效。"),
        "scan_sha256": _required_sha256(scan_sha256, "当前扫描结果校验值无效。"),
        "config_sha256": _required_sha256(config_sha256, "当前模板配置校验值无效。"),
        "sample_sha256": _required_sha256(sample_sha256, "当前样例数据校验值无效。"),
        "render_task_sha256": _required_sha256(render_task_sha256, "当前渲染任务校验值无效。"),
    }
    if any(normalized[key] != value for key, value in expected.items()):
        raise V2PreviewProofError("preview_proof_stale", "模板、配置、扫描或样例数据已变化，请重新试渲染。")
    actual_keys = [item["key"] for item in normalized["outputs"]]
    wanted_keys = sorted(str(key) for key in output_keys)
    if actual_keys != wanted_keys:
        raise V2PreviewProofError("preview_output_incomplete", "样例渲染未覆盖当前模板的全部效果图。")
    return normalized


def _required_sha256(value: Any, reason: str) -> str:
    normalized = str(value or "").strip().lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise V2PreviewProofError("preview_proof_invalid", reason)
    return normalized


def utc_timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_utc_timestamp(value: str) -> bool:
    if not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return parsed <= datetime.now(timezone.utc)


def _current_template_ai_asset(manifest: Mapping[str, Any]) -> dict[str, Any]:
    assets = [dict(item) for item in manifest.get("assets", []) if isinstance(item, Mapping)]
    template_assets = [
        item
        for item in assets
        if str(item.get("role") or "").strip().lower() == "template"
        and str(item.get("extension") or "").strip().lower() == ".ai"
    ]
    if template_assets:
        return template_assets[-1]
    for item in assets:
        file_name = str(item.get("file_name") or item.get("filename") or "").strip().lower()
        if file_name == "template.ai" and str(item.get("extension") or "").strip().lower() == ".ai":
            return item
    return {}


__all__ = [
    "V2PreviewProofError",
    "canonical_preview_outputs",
    "compile_preview_render_task",
    "expected_preview_output_keys",
    "normalize_preview_evidence",
    "preview_config_payload",
    "preview_config_sha256",
    "preview_outputs_sha256",
    "sample_rows_sha256",
    "stable_json_sha256",
    "utc_timestamp_now",
    "validate_preview_proof_bindings",
]
