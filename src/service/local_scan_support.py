"""Upload and validation helpers for local Illustrator scans."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .local_client_errors import LocalClientError


def safe_file_name(value: str) -> str:
    name = Path(str(value or "template.ai")).name
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in name
    ).strip("._")
    return cleaned or "template.ai"


def upload_path_or_saved_copy(
    client: Any,
    template_id: str,
    filename: str,
    upload: Mapping[str, Any],
) -> Path:
    path_value = upload.get("path")
    if path_value:
        path = Path(path_value)
        if path.suffix.lower() != ".ai":
            raise LocalClientError(
                "请上传 .ai 模板文件",
                code="v2_scan_ai_required",
            )
        _require_nonempty_ai(path)
        return path
    return client._save_v2_scan_ai(
        template_id,
        filename,
        upload_bytes(upload),
    )


def upload_bytes(upload: Mapping[str, Any]) -> bytes:
    content = upload.get("content")
    if isinstance(content, bytes):
        if not content:
            raise LocalClientError(
                "上传的 .ai 文件为空，请选择有效模板后重试。",
                code="v2_scan_ai_empty",
            )
        return content
    path_value = upload.get("path")
    if path_value:
        path = Path(path_value)
        _require_nonempty_ai(path)
        return path.read_bytes()
    raise LocalClientError(
        "上传的 .ai 文件为空，请选择有效模板后重试。",
        code="v2_scan_ai_empty",
    )


def has_upload_body(upload: Mapping[str, Any]) -> bool:
    return isinstance(upload.get("content"), bytes) or bool(upload.get("path"))


def is_v2_scan_request(fields: Mapping[str, str]) -> bool:
    template_type = str(fields.get("template_type") or "").strip().lower()
    scan_contract = str(fields.get("scan_contract_version") or "").strip().lower()
    return template_type.startswith("v2") or scan_contract.startswith("v2")


def blocked_scan_message(scan: Mapping[str, Any]) -> str:
    issues = scan.get("issues", [])
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            reason = str(issue.get("reason") or "").strip()
            if reason:
                return f"{reason} 请按模板标注规则调整后重新扫描。"
    return "扫描发现模板结构未通过初步验收，请按 Template 标注规则调整后重新扫描。"


def _require_nonempty_ai(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise LocalClientError(
            "上传的 .ai 文件为空，请选择有效模板后重试。",
            code="v2_scan_ai_empty",
        )


__all__ = [
    "blocked_scan_message",
    "has_upload_body",
    "is_v2_scan_request",
    "safe_file_name",
    "upload_bytes",
    "upload_path_or_saved_copy",
]
