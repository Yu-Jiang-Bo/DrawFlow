"""Small, business-safe helpers for local V2 sample rendering."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

from .runtime_templates import sha256_file
from .v2_font_inventory import default_font_dirs, missing_required_fonts
from .v2_preview_worker_auth import sign_preview_worker_challenge
from .v2_template_store_utils import safe_segment


class V2TrialRenderError(RuntimeError):
    def __init__(self, message: str, *, code: str, technical_message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.technical_message = technical_message


_FONT_OPTION_MARKER_RE = re.compile(r"^F[1-9]\d*$", re.IGNORECASE)


def sample_row(value: Mapping[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for key, raw in value.items():
        header = str(key or "").strip()
        if not header or len(header) > 160:
            continue
        if isinstance(raw, (Mapping, list, tuple, set)):
            raise V2TrialRenderError("样例订单只能填写文字或数字。", code="v2_trial_sample_invalid")
        text = "" if raw is None else str(raw).strip()
        if len(text) > 4000:
            raise V2TrialRenderError("样例订单内容过长，请缩短后重试。", code="v2_trial_sample_invalid")
        row[header] = text
    return row


def first_business_issue(result: Mapping[str, Any], fallback: str) -> str:
    issues = result.get("issues")
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, Mapping):
            continue
        reason = str(issue.get("reason") or "").strip()
        if reason and not any(marker in reason for marker in (":\\", "Traceback", "$.")):
            return reason
    return fallback


def required_fonts(config: Mapping[str, Any], scan: Mapping[str, Any]) -> list[str]:
    fonts: set[str] = set()
    dependencies = scan.get("dependencies")
    scan_fonts = dict(dependencies).get("fonts", []) if isinstance(dependencies, Mapping) else []
    for item in scan_fonts if isinstance(scan_fonts, list) else []:
        name = str(item.get("font_name") or item.get("name") or "").strip() if isinstance(item, Mapping) else str(item or "").strip()
        if name:
            fonts.add(name)
    outputs = config.get("outputs")
    for output in outputs if isinstance(outputs, list) else []:
        if not isinstance(output, Mapping):
            continue
        for group_name in ("design", "font"):
            group = output.get(group_name)
            options = dict(group).get("options", []) if isinstance(group, Mapping) else []
            for option in options if isinstance(options, list) else []:
                if not isinstance(option, Mapping):
                    continue
                _add_strings(fonts, option.get("font_dependencies"), group_name=group_name, option=option)
                slots = option.get("slots")
                for slot in slots if isinstance(slots, list) else []:
                    if isinstance(slot, Mapping):
                        _add_strings(fonts, slot.get("font_dependencies"), group_name=group_name, option=option)
    return sorted(fonts, key=str.casefold)


def logical_values(config: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(logical): str(row.get(str(header), "") or "").strip()
        for logical, header in dict(config.get("field_bindings") or {}).items()
        if str(logical or "").strip() and str(header or "").strip()
    }


def selections(preflight: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    rows = preflight.get("preflight_rows")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise V2TrialRenderError("样例订单预检结果不完整，请重新试渲染。", code="v2_trial_preflight_failed")
    outputs = rows[0].get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise V2TrialRenderError("样例订单没有可渲染的效果图。", code="v2_trial_preflight_failed")
    result: dict[str, dict[str, str]] = {}
    for output in outputs:
        if not isinstance(output, Mapping) or not str(output.get("output") or "").strip():
            continue
        result[str(output["output"]).strip()] = {
            group: str(output.get(group) or "").strip()
            for group in ("style", "design", "font")
            if str(output.get(group) or "").strip()
        }
    return result


def output_labels(config: Mapping[str, Any]) -> dict[str, str]:
    outputs = config.get("outputs")
    return {
        str(output.get("key") or "").strip(): str(output.get("display_name") or "").strip() or f"效果图 {index}"
        for index, output in enumerate(outputs if isinstance(outputs, list) else [], start=1)
        if isinstance(output, Mapping) and str(output.get("key") or "").strip()
    }


def current_template_asset(manifest: Mapping[str, Any]) -> dict[str, Any]:
    assets = [dict(item) for item in manifest.get("assets", []) if isinstance(item, Mapping)]
    preferred = [
        item for item in assets
        if str(item.get("role") or "").strip().lower() == "template"
        and str(item.get("extension") or "").strip().lower() == ".ai"
    ]
    if preferred:
        return preferred[-1]
    return next((item for item in reversed(assets) if str(item.get("file_name") or "").lower() == "template.ai"), {})


def read_draft(central: Any, template_id: str) -> dict[str, Any]:
    if hasattr(central, "get_v2_draft"):
        return dict(central.get_v2_draft(template_id))
    if hasattr(central, "read_draft"):
        return dict(central.read_draft(template_id))
    raise V2TrialRenderError("中央服务版本过旧，请更新后再试。", code="v2_trial_not_supported")


def download_asset(central: Any, template_id: str, asset: Mapping[str, Any], target: Path) -> None:
    file_name = str(asset.get("file_name") or "template.ai")
    expected = str(asset.get("sha256") or "").strip().lower()
    target.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(central, "download_v2_draft_asset"):
        central.download_v2_draft_asset(template_id, file_name, target, expected_sha256=expected)
    elif hasattr(central, "draft_asset_path"):
        source = central.draft_asset_path(template_id, file_name)
        source_path = source[0] if isinstance(source, tuple) else source
        shutil.copyfile(Path(source_path), target)
    else:
        raise V2TrialRenderError("中央服务版本过旧，请更新后再试。", code="v2_trial_not_supported")
    if not target.is_file() or sha256_file(target) != expected:
        raise V2TrialRenderError("当前模板文件校验未通过，请重新上传并扫描。", code="v2_draft_asset_hash_mismatch")


def request_challenge(central: Any, template_id: str, revision: str, worker_id: str) -> dict[str, Any]:
    if hasattr(central, "request_v2_preview_challenge"):
        return dict(
            central.request_v2_preview_challenge(
                template_id,
                expected_draft_revision=revision,
                worker_id=worker_id,
            )
        )
    if hasattr(central, "preview_challenge"):
        response = central.preview_challenge(
            template_id,
            {"expected_draft_revision": revision, "worker_id": worker_id},
        )
        challenge = dict(response).get("challenge") if isinstance(response, Mapping) else None
        if isinstance(challenge, Mapping):
            return dict(challenge)
    raise V2TrialRenderError("中央服务版本过旧，请更新后再试。", code="v2_trial_not_supported")


def worker_proof(
    secret: str | bytes,
    challenge: Mapping[str, Any],
    template_id: str,
    revision: str,
    rows: list[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    worker_id: str,
) -> dict[str, str]:
    return sign_preview_worker_challenge(
        secret,
        challenge,
        template_id=template_id,
        draft_revision=revision,
        sample_rows=rows,
        evidence=evidence,
        worker_id=worker_id,
    )


def submit_proof(
    central: Any,
    template_id: str,
    revision: str,
    rows: list[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    signed_worker_proof: Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(central, "submit_v2_preview_proof"):
        return dict(
            central.submit_v2_preview_proof(
                template_id,
                expected_draft_revision=revision,
                sample_rows=rows,
                evidence=evidence,
                worker_proof=signed_worker_proof,
            )
        )
    if hasattr(central, "register_preview_proof"):
        return dict(
            central.register_preview_proof(
                template_id,
                {
                    "expected_draft_revision": revision,
                    "sample_rows": [dict(row) for row in rows],
                    "evidence": dict(evidence),
                    "worker_proof": dict(signed_worker_proof),
                },
            )
        )
    raise V2TrialRenderError("中央服务版本过旧，请更新后再试。", code="v2_trial_not_supported")


def read_warnings(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        warnings = json.loads(path.read_text(encoding="utf-8")).get("warnings", [])
    except (OSError, ValueError, AttributeError):
        return ["效果图已生成，但排版检查结果无法读取，请人工核对。"]
    messages = []
    for item in warnings if isinstance(warnings, list) else []:
        code = str(dict(item).get("code") or "") if isinstance(item, Mapping) else str(item or "")
        message = "部分文字已大幅缩小，请核对实际效果。" if code in {"text_fit_extreme", "path_text_fit_extreme"} else "效果图有排版提示，请人工核对。"
        if message not in messages:
            messages.append(message)
    return messages


def _add_strings(
    target: set[str],
    value: Any,
    *,
    group_name: str = "",
    option: Mapping[str, Any] | None = None,
) -> None:
    for item in value if isinstance(value, list) else []:
        text = str(item or "").strip()
        if text and not _is_font_option_self_dependency(group_name, option, text):
            target.add(text)


def _is_font_option_self_dependency(
    group_name: str,
    option: Mapping[str, Any] | None,
    value: str,
) -> bool:
    if group_name != "font" or not isinstance(option, Mapping):
        return False
    dependency = str(value or "").strip().casefold()
    for key in ("key", "label"):
        option_value = str(option.get(key) or "").strip()
        if (
            _FONT_OPTION_MARKER_RE.fullmatch(option_value)
            and dependency == option_value.casefold()
        ):
            return True
    return False


__all__ = [
    "V2TrialRenderError",
    "current_template_asset",
    "default_font_dirs",
    "download_asset",
    "first_business_issue",
    "logical_values",
    "missing_required_fonts",
    "output_labels",
    "request_challenge",
    "read_draft",
    "read_warnings",
    "required_fonts",
    "sample_row",
    "selections",
    "submit_proof",
    "worker_proof",
]
