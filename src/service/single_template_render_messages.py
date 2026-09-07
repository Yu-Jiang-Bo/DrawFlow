"""Business-safe render failure payloads shared by single-template adapters."""

from __future__ import annotations

from typing import Any


def failed_render(
    request: dict[str, Any],
    code: str,
    message: str,
    *,
    failure_scope: str = "",
    canary: bool = True,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "request": request,
        "outputs": {},
        "stats": {},
        "error_code": code,
        "error": message,
        "failure_scope": failure_scope,
        "canary": canary,
    }


def business_error_message(code: str) -> str:
    messages = {
        "template_rules_invalid": "模板规则不完整，请补齐配置后重新预检。",
        "template_config_missing": "模板配置缺失，请重新发布模板后再试。",
        "template_font_config_missing": "模板字体配置缺失，请重新发布模板后再试。",
        "v2_template_version_unavailable": "预检时固定的模板版本已不可用，请重新预检后再试。",
        "v2_template_asset_invalid": "预检时固定的模板文件已变化，请重新预检后再试。",
        "v2_template_config_invalid": "预检时固定的模板配置已变化，请重新预检后再试。",
        "v2_order_preflight_failed": "该模板的订单字段或选项未通过预检，请检查订单内容。",
    }
    return messages.get(code, "模板订单预检失败，请检查订单字段和模板配置。")


__all__ = ["business_error_message", "failed_render"]
