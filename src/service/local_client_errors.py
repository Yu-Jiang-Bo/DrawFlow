"""Stable business errors shared by local DrawFlow client services."""

from __future__ import annotations

import json
from typing import Mapping


class LocalClientError(RuntimeError):
    """Raised when the local client cannot complete a request."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "local_client_error",
        technical_message: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.technical_message = technical_message


def central_error_detail(value: str) -> str:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return "中央服务未提供可读的错误说明"
    error = payload.get("error") if isinstance(payload, Mapping) else None
    if isinstance(error, Mapping):
        error = error.get("message") or error.get("code")
    detail = str(error or "").strip()
    return detail[:180] if detail else "中央服务未提供可读的错误说明"


def template_sync_error(
    template_id: str,
    phase: str,
    cause: LocalClientError,
) -> LocalClientError:
    if cause.code == "central_unreachable":
        return LocalClientError(
            f"无法连接中央服务，模板 {template_id} 未能同步：{cause}",
            code="central_unreachable",
        )
    if phase == "manifest" and cause.code == "central_http_404":
        return LocalClientError(
            f"模板 {template_id} 尚未在中央服务发布可用版本，请管理员发布该模板后再试",
            code="template_not_published",
        )
    if phase == "bundle" and cause.code == "central_http_404":
        return LocalClientError(
            f"模板 {template_id} 的中央运行包不可用，请管理员重新发布该模板后再试",
            code="template_bundle_unavailable",
        )
    return LocalClientError(
        f"模板 {template_id} 同步 {phase} 失败：{cause}",
        code=f"template_{phase}_failed",
    )


__all__ = ["LocalClientError", "central_error_detail", "template_sync_error"]
