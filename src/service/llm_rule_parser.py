"""Optional LLM adapter for natural-language rule drafting."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict


class LlmRuleParser:
    """OpenAI-compatible rule parser with deterministic fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("CUSTOM_RENDERER_LLM_API_KEY", "")
        self.base_url = base_url if base_url is not None else os.getenv("CUSTOM_RENDERER_LLM_BASE_URL", "")
        self.model = model if model is not None else os.getenv("CUSTOM_RENDERER_LLM_MODEL", "rule-parser")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("CUSTOM_RENDERER_LLM_TIMEOUT_SECONDS", "30")
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def parse(
        self,
        *,
        kind: str,
        natural_text: str,
        context: Dict[str, Any],
        fallback: Dict[str, Any],
        require_llm: bool = False,
    ) -> Dict[str, Any]:
        if not self.configured:
            if require_llm:
                raise RuntimeError("LLM 规则编译未配置，请设置 CUSTOM_RENDERER_LLM_API_KEY 和 CUSTOM_RENDERER_LLM_BASE_URL")
            return with_parser_meta(fallback, source="local", configured=False)
        try:
            parsed = self._call_llm(kind=kind, natural_text=natural_text, context=context)
        except Exception as exc:
            if require_llm:
                raise RuntimeError(f"LLM 规则编译失败: {exc}") from exc
            draft = with_parser_meta(fallback, source="local", configured=True)
            draft["parser"]["llm_error"] = str(exc)
            return draft
        merged = merge_drafts(fallback, parsed)
        return with_parser_meta(merged, source="llm", configured=True)

    def _call_llm(self, *, kind: str, natural_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = self._endpoint()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是制图规则解析器。只返回 JSON，不要返回解释。"
                        "不得编造业务字段，不确定的字段留空数组或空字符串。"
                        "如果规则提到输出 RGB 或 CMYK，请在 output.color_mode 中返回 RGB 或 CMYK。"
                        "模板规则 JSON 字段必须尽量使用：version, template_id, mode, status, rule_source, raw_text, "
                        "capabilities, font_options, style_options, design_options, defaults, transforms, dimensions, "
                        "output, slots, assets。"
                        "如果业务把 F10-F12 这类字体选项描述为独立设计/设计款，也要保留在 font_options，"
                        "并在 design_options 或 design_font_options 中表达这些设计型字体选项。"
                        "如果规则提到 Text1/Text2/Text3 等变量，slots 中必须分别返回 replace_text 槽位。"
                        "如果规则提到 Style1-5 或作图区尺寸框，style_options 必须返回 Style1 等规范值。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "rule_kind": kind,
                            "natural_text": natural_text,
                            "context": context,
                            "required_output": "structured_rule_draft_json",
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        raw = json.loads(body)
        content = raw
        if isinstance(raw, dict) and raw.get("choices"):
            content = raw["choices"][0].get("message", {}).get("content", "")
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ValueError("LLM 返回内容不是 JSON 字符串")
        return extract_json_object(content)

    def _endpoint(self) -> str:
        value = self.base_url.rstrip("/")
        if value.endswith("/chat/completions"):
            return value
        if value.endswith("/v1"):
            return f"{value}/chat/completions"
        return f"{value}/v1/chat/completions"


def merge_drafts(fallback: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(fallback)
    for key, value in parsed.items():
        if value not in ("", [], {}, None):
            merged[key] = value
    return merged


def with_parser_meta(draft: Dict[str, Any], *, source: str, configured: bool) -> Dict[str, Any]:
    result = dict(draft)
    result["parser"] = {
        "source": source,
        "llm_configured": configured,
    }
    return result


def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON 顶层必须是对象")
    return payload
