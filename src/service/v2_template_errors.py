"""Unified V2 API errors and whitelist sanitizers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from http import HTTPStatus
import re
from typing import Any, Iterable, Mapping, MutableMapping

from .v2_template_contract import V2ContractError, normalize_v2_template_contract


V2_PUBLIC_ERROR_FIELDS = ("code", "title", "reason", "suggestion")

V2_ERROR_STATUS = {
    "v2_invalid_request": HTTPStatus.BAD_REQUEST,
    "v2_config_rejected": HTTPStatus.BAD_REQUEST,
    "v2_payload_rejected": HTTPStatus.BAD_REQUEST,
    "v2_required_field_missing": HTTPStatus.BAD_REQUEST,
    "v2_revision_conflict": HTTPStatus.CONFLICT,
    "v2_upload_conflict": HTTPStatus.CONFLICT,
    "v2_payload_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    "v2_storage_insufficient": HTTPStatus.INSUFFICIENT_STORAGE,
    "v2_internal_error": HTTPStatus.INTERNAL_SERVER_ERROR,
}

V2_CONFIG_TOP_LEVEL_FIELDS = frozenset(
    {
        "$schema",
        "schema_version",
        "template",
        "outputs",
        "colors",
        "field_bindings",
        "option_mappings",
        "render_mode",
        "multi_name_customization",
        "render_layout",
        "output",
        "checks",
        "preview",
        "audit",
    }
)
_V2_LEGACY_OUTPUT_SCAN_FIELDS = frozenset({"path", "order", "styles", "designs", "fonts", "summary"})
_V2_LEGACY_GROUP_SCAN_FIELDS = frozenset({"path"})
_V2_LEGACY_STYLE_OPTION_SCAN_FIELDS = frozenset({"path", "closed_dimension_box", "visible_bounds", "summary"})
_V2_LEGACY_CONTENT_OPTION_SCAN_FIELDS = frozenset(
    {
        "path",
        "anchors",
        "tails",
        "dimensions",
        "visible_bounds",
        "type",
        "text_kind",
        "fixed_object_count",
        "fixed_object_type_counts",
        "fixed_objects",
        "summary",
    }
)
_V2_LEGACY_SLOT_SCAN_FIELDS = frozenset({"path", "type", "text_kind", "visible_bounds", "dimensions", "closed_dimension_box"})
_V2_LEGACY_ASSET_SCAN_FIELDS = frozenset({"path", "type", "file_name", "filename", "stored_path", "extension", "sha256"})

_DEFAULT_TITLE = "V2 模板请求无法处理"
_DEFAULT_REASON = "请求内容不符合 V2 模板接口要求。"
_DEFAULT_SUGGESTION = "请检查模板 ID、草稿内容和受控配置字段后重试。"
_TECHNICAL_TITLE = "V2 模板服务异常"
_TECHNICAL_REASON = "服务处理请求时失败，技术详情已保留在服务日志。"
_TECHNICAL_SUGGESTION = "请稍后重试；如果持续失败，请联系维护人员查看服务日志。"
_CONFIG_TITLE = "V2 配置未通过白名单校验"
_CONFIG_REASON = "配置包含脚本内容、自由表达式或未开放字段，已拒绝保存。"
_CONFIG_SUGGESTION = "请删除自然语言规则、脚本字段和未受控字段后再保存。"

_SAFE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_WINDOWS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>]+")
_POSIX_PATH_RE = re.compile(r"(?<![A-Za-z0-9])/(?:Users|home|root|var|tmp|etc|opt|mnt|srv|workspace|app)(?:/[^\s\"'<>]*)?", re.I)
_STACK_RE = re.compile(
    r"(Traceback \(most recent call last\)|File \"[^\"]+\", line \d+|line \d+, in |\b[A-Za-z_][\w.]+(?:Error|Exception)\s*[:(])",
    re.I,
)
_HTTP_RAW_RE = re.compile(
    r"(\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/\S+\s+HTTP/\d(?:\.\d)?|HTTP/\d(?:\.\d)?\s+\d{3}|(?:Host|Authorization|Cookie|User-Agent):\s*)",
    re.I,
)
_EXECUTION_TEXT_RE = re.compile(
    r"(?:\.jsx\b|<script\b|javascript:|eval\s*\(|exec\s*\(|function\s*\(|=>|[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\s*\()",
    re.I,
)
_EXECUTION_FIELD_NAMES = frozenset(
    {
        "natural_language_script",
        "natural_language_rule",
        "natural_text",
        "raw_text",
        "special_rules_text",
        "rule_ast",
        "jsx",
        "jsx_path",
        "script",
        "expression",
        "eval",
        "evaluate",
        "function",
        "function_body",
        "free_expression",
    }
)
_EXECUTION_FIELD_COMPACT_NAMES = frozenset(re.sub(r"[^a-z0-9]+", "", item) for item in _EXECUTION_FIELD_NAMES)


@dataclass(frozen=True)
class V2ApiProblem:
    code: str
    title: str
    reason: str
    suggestion: str

    def to_response_payload(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in V2_PUBLIC_ERROR_FIELDS}


class V2ApiError(RuntimeError):
    """Error that keeps technical context out of the browser payload."""

    def __init__(
        self,
        code: str,
        reason: str = "",
        *,
        status: HTTPStatus | int | None = None,
        title: str = _DEFAULT_TITLE,
        suggestion: str = _DEFAULT_SUGGESTION,
        cause: BaseException | None = None,
        internal_code: str | None = None,
    ) -> None:
        safe_code = _safe_code(code)
        self.internal_code = _safe_code(internal_code or safe_code)
        self.status = _normalize_status(status or status_for_code(safe_code))
        self.problem = V2ApiProblem(
            code=safe_code,
            title=sanitize_public_text(title, _DEFAULT_TITLE),
            reason=sanitize_public_text(reason or _DEFAULT_REASON, _DEFAULT_REASON),
            suggestion=sanitize_public_text(suggestion, _DEFAULT_SUGGESTION),
        )
        super().__init__(self.problem.reason)
        if cause is not None:
            self.__cause__ = cause

    @classmethod
    def from_exception(
        cls,
        code: str,
        exc: BaseException,
        *,
        status: HTTPStatus | int | None = None,
        title: str = _TECHNICAL_TITLE,
        reason: str = _TECHNICAL_REASON,
        suggestion: str = _TECHNICAL_SUGGESTION,
    ) -> "V2ApiError":
        return cls(code, reason, status=status or status_for_code(code), title=title, suggestion=suggestion, cause=exc)

    def to_response_payload(self) -> dict[str, str]:
        return self.problem.to_response_payload()

    def to_log_context(self) -> dict[str, Any]:
        cause = self.__cause__
        return {
            "internal_code": self.internal_code,
            "status": int(self.status),
            "cause_type": type(cause).__name__ if cause is not None else "",
        }


def status_for_code(code: str) -> HTTPStatus:
    safe_code = _safe_code(code)
    if safe_code in V2_ERROR_STATUS:
        return V2_ERROR_STATUS[safe_code]
    if safe_code.endswith("_conflict") or "conflict" in safe_code:
        return HTTPStatus.CONFLICT
    if safe_code.endswith("_too_large") or "too_large" in safe_code:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    if "insufficient" in safe_code or "storage" in safe_code or "disk" in safe_code:
        return HTTPStatus.INSUFFICIENT_STORAGE
    if "internal" in safe_code or "unexpected" in safe_code:
        return HTTPStatus.INTERNAL_SERVER_ERROR
    return HTTPStatus.BAD_REQUEST


def to_response_payload(error: V2ApiError | V2ApiProblem | BaseException) -> dict[str, str]:
    if isinstance(error, V2ApiError):
        return error.to_response_payload()
    if isinstance(error, V2ApiProblem):
        return error.to_response_payload()
    return V2ApiError.from_exception("v2_internal_error", error).to_response_payload()


def sanitize_v2_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a V2 config against execution and contract whitelists."""

    if not isinstance(payload, Mapping):
        raise V2ApiError("v2_config_rejected", _CONFIG_REASON, title=_CONFIG_TITLE, suggestion=_CONFIG_SUGGESTION)
    source = dict(payload)
    unknown = sorted(set(source) - V2_CONFIG_TOP_LEVEL_FIELDS)
    if unknown:
        raise _config_rejected()
    _scan_for_executable_fields(source)
    source = _clean_legacy_v2_scan_fields(source)
    try:
        return normalize_v2_template_contract(deepcopy(source))
    except V2ContractError as exc:
        raise _config_rejected(exc) from exc


def sanitize_v2_business_payload(payload: Mapping[str, Any], allowed_fields: Iterable[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise V2ApiError("v2_payload_rejected", "请求内容格式不正确，请刷新页面后重试。")
    allowed = set(allowed_fields)
    source = dict(payload)
    if sorted(set(source) - allowed):
        raise V2ApiError(
            "v2_payload_rejected",
            "请求包含未开放的字段，已拒绝处理。",
            suggestion="请只提交当前界面允许编辑的字段后重试。",
        )
    _scan_for_executable_fields(source)
    return deepcopy(source)


def contains_sensitive_text(value: str) -> bool:
    return bool(_WINDOWS_PATH_RE.search(value) or _POSIX_PATH_RE.search(value) or _STACK_RE.search(value) or _HTTP_RAW_RE.search(value))


def sanitize_public_text(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if not text or contains_sensitive_text(text):
        return fallback
    return text


def redact_sensitive_text(value: str, replacement: str = "[redacted]") -> str:
    text = str(value or "")
    if contains_sensitive_text(text):
        return replacement
    return text


def _config_rejected(cause: BaseException | None = None) -> V2ApiError:
    return V2ApiError(
        "v2_config_rejected",
        _CONFIG_REASON,
        title=_CONFIG_TITLE,
        suggestion=_CONFIG_SUGGESTION,
        cause=cause,
    )


def _clean_legacy_v2_scan_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    source = deepcopy(dict(payload))
    outputs = source.get("outputs")
    if not isinstance(outputs, list):
        return source
    for output in outputs:
        if not isinstance(output, Mapping):
            continue
        _drop_known_fields(output, _V2_LEGACY_OUTPUT_SCAN_FIELDS)
        for group in ("style", "design", "font"):
            group_data = output.get(group)
            if not isinstance(group_data, Mapping):
                continue
            _drop_known_fields(group_data, _V2_LEGACY_GROUP_SCAN_FIELDS)
            options = group_data.get("options")
            if not isinstance(options, list):
                continue
            for option in options:
                if not isinstance(option, Mapping):
                    continue
                if group == "style":
                    _drop_known_fields(option, _V2_LEGACY_STYLE_OPTION_SCAN_FIELDS)
                    continue
                _drop_known_fields(option, _V2_LEGACY_CONTENT_OPTION_SCAN_FIELDS)
                slots = option.get("slots")
                if isinstance(slots, list):
                    for slot in slots:
                        if isinstance(slot, Mapping):
                            _promote_legacy_slot_dimensions(slot)
                            _drop_known_fields(slot, _V2_LEGACY_SLOT_SCAN_FIELDS)
                assets = option.get("assets")
                if isinstance(assets, list):
                    for asset in assets:
                        if isinstance(asset, Mapping):
                            _drop_known_fields(asset, _V2_LEGACY_ASSET_SCAN_FIELDS)
    return source


def _promote_legacy_slot_dimensions(slot: MutableMapping[str, Any]) -> None:
    if "dimension_rule" in slot or not isinstance(slot.get("dimensions"), Mapping):
        return
    dimensions = dict(slot.get("dimensions") or {})
    promoted = {key: dimensions[key] for key in ("width_mm", "height_mm", "tolerance_mm") if key in dimensions}
    if "mode" in dimensions:
        promoted["mode"] = dimensions["mode"]
    elif promoted:
        promoted["mode"] = "slot"
    if promoted:
        slot["dimension_rule"] = promoted


def _drop_known_fields(data: MutableMapping[str, Any], fields: Iterable[str]) -> None:
    for field in fields:
        if field in data:
            del data[field]


def _scan_for_executable_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key or "").strip()
            if not key_text or _is_execution_field_name(key_text):
                raise _config_rejected()
            _scan_for_executable_fields(item)
        return
    if isinstance(value, list):
        for item in value:
            _scan_for_executable_fields(item)
        return
    if isinstance(value, str) and _EXECUTION_TEXT_RE.search(value):
        raise _config_rejected()
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    raise _config_rejected()


def _is_execution_field_name(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    compact = re.sub(r"[^a-z0-9]+", "", value.strip().casefold())
    return normalized in _EXECUTION_FIELD_NAMES or compact in _EXECUTION_FIELD_COMPACT_NAMES


def _safe_code(code: str) -> str:
    text = str(code or "").strip().casefold()
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return text if _SAFE_CODE_RE.match(text) else "v2_error"


def _normalize_status(value: HTTPStatus | int) -> HTTPStatus:
    return value if isinstance(value, HTTPStatus) else HTTPStatus(int(value))


__all__ = [
    "V2ApiError",
    "V2ApiProblem",
    "V2_CONFIG_TOP_LEVEL_FIELDS",
    "V2_ERROR_STATUS",
    "contains_sensitive_text",
    "redact_sensitive_text",
    "sanitize_public_text",
    "sanitize_v2_business_payload",
    "sanitize_v2_config",
    "status_for_code",
    "to_response_payload",
]
