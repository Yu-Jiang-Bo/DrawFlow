"""V2 template API orchestration with sanitized business responses."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Mapping
from urllib.parse import unquote

from .paths import V2_TEMPLATE_DATA_DIR
from .v2_template_store import V2TemplateStore, V2TemplateStoreError
from .v2_template_store_utils import read_json
from .v2_template_validation import validate_v2_template_configuration


@dataclass(frozen=True)
class V2ApiResult:
    payload: dict[str, Any]
    status: HTTPStatus = HTTPStatus.OK


class V2TemplateApiError(ValueError):
    def __init__(
        self,
        code: str,
        reason: str,
        *,
        status: HTTPStatus = HTTPStatus.BAD_REQUEST,
        title: str = "V2 模板请求无法处理",
        suggestion: str = "请检查模板 ID、草稿内容和受控配置字段后重试。",
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.status = status
        self.title = title
        self.suggestion = suggestion

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "title": self.title,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }


class V2TemplateApi:
    def __init__(self, store: V2TemplateStore | None = None) -> None:
        self.store = store or V2TemplateStore(V2_TEMPLATE_DATA_DIR)

    def handle(self, method: str, parts: list[str], payload: Mapping[str, Any] | None = None) -> V2ApiResult:
        if len(parts) == 3 and parts == ["api", "v2", "templates"]:
            if method == "GET":
                return V2ApiResult({"templates": self.list_templates()})
            if method == "POST":
                return V2ApiResult(self.create_template(payload or {}), HTTPStatus.CREATED)
        if len(parts) == 5 and parts[:3] == ["api", "v2", "templates"]:
            template_id = unquote(parts[3])
            action = parts[4]
            if method == "GET" and action == "draft":
                return V2ApiResult({"draft": self.read_draft(template_id)})
            if method == "POST" and action == "draft":
                return V2ApiResult(self.save_draft(template_id, payload or {}))
            if method == "GET" and action == "scan":
                return V2ApiResult(self.read_scan(template_id))
            if method == "POST" and action == "validate":
                return V2ApiResult(self.validate_config(payload or {}))
            if method == "GET" and action == "versions":
                return V2ApiResult(self.read_versions(template_id))
        raise V2TemplateApiError(
            "v2_route_not_found",
            "请求的 V2 模板接口不存在。",
            status=HTTPStatus.NOT_FOUND,
            suggestion="请使用 /api/v2/templates 及其草稿、扫描、校验或版本子接口。",
        )

    def list_templates(self) -> list[dict[str, Any]]:
        if not self.store.root.exists():
            return []
        states = []
        for state_path in sorted(self.store.root.glob("*/state.json")):
            states.append(_state_summary(read_json(state_path)))
        return states

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        template_id = _required_text(payload, "template_id", "请填写模板 ID。")
        metadata = _metadata_from_payload(template_id, payload, None)
        state = self.store.save_draft(template_id, metadata=metadata)
        return {"template": state["template"], "state": _state_summary(state)}

    def save_draft(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        current = self.store.get_state(template_id)
        metadata = _metadata_from_payload(template_id, payload, current)
        config = _optional_mapping(payload, "config")
        scan = _optional_mapping(payload, "scan", "scan_result")
        validation = self._validate_saveable_config(config)
        self._ensure_config_template_matches(template_id, validation)
        state = self.store.save_draft(template_id, metadata=metadata, config=config, scan=scan)
        return {
            "state": _state_summary(state),
            "draft": self.store.read_draft(template_id),
            "validation": validation,
        }

    def read_draft(self, template_id: str) -> dict[str, Any]:
        try:
            return self.store.read_draft(template_id)
        except V2TemplateStoreError as exc:
            raise _not_found(str(exc)) from exc

    def read_scan(self, template_id: str) -> dict[str, Any]:
        draft = self.read_draft(template_id)
        return {
            "template_id": template_id,
            "draft_revision": draft["manifest"].get("draft_revision", ""),
            "scan": draft["scan"],
        }

    def validate_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        config = payload.get("config", payload)
        if not isinstance(config, Mapping):
            raise V2TemplateApiError("v2_config_invalid", "校验内容必须是 JSON 对象。")
        return {"validation": validate_v2_template_configuration(dict(config))}

    def read_versions(self, template_id: str) -> dict[str, Any]:
        state = self.store.get_state(template_id)
        return {
            "template_id": state["template_id"],
            "publication": state["publication"],
            "versions": state["versions"],
        }

    def _validate_saveable_config(self, config: Mapping[str, Any]) -> dict[str, Any] | None:
        if not config:
            return None
        validation = validate_v2_template_configuration(dict(config))
        if not validation["can_save"]:
            raise V2TemplateApiError(
                "v2_config_rejected",
                "配置没有通过 V2 白名单契约，草稿未保存。",
                suggestion="请删除脚本、自然语言规则、未知字段或错误类型后再保存。",
            )
        return validation

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


def handle_v2_template_api(handler: Any, method: str, path: str, parts: list[str]) -> bool:
    if len(parts) < 3 or parts[:3] != ["api", "v2", "templates"]:
        return False
    try:
        payload = handler._read_json() if method == "POST" else None
        result = handler.v2_template_api.handle(method, parts, payload)
        handler._send_json(result.payload, result.status)
    except V2TemplateApiError as exc:
        handler._send_json({"error": exc.to_payload()}, exc.status)
    except (TypeError, ValueError, V2TemplateStoreError) as exc:
        error = V2TemplateApiError("v2_invalid_request", _safe_reason(exc))
        handler._send_json({"error": error.to_payload()}, error.status)
    except Exception:
        error = V2TemplateApiError(
            "v2_internal_error",
            "服务处理 V2 模板请求时失败，技术详情已保留在服务日志。",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            title="V2 模板服务异常",
            suggestion="请稍后重试；如果持续失败，请联系维护人员查看服务日志。",
        )
        handler._send_json({"error": error.to_payload()}, error.status)
    return True


def _metadata_from_payload(
    template_id: str,
    payload: Mapping[str, Any],
    current_state: Mapping[str, Any] | None,
) -> dict[str, str]:
    template = current_state.get("template", {}) if isinstance(current_state, Mapping) else {}
    name = str(payload.get("name") or dict(template).get("name") or "").strip()
    if not name:
        raise V2TemplateApiError("v2_template_name_required", "请填写模板名称。")
    return {
        "template_id": template_id,
        "name": name,
        "shop_name": str(payload.get("shop_name") or dict(template).get("shop_name") or "").strip(),
    }


def _optional_mapping(payload: Mapping[str, Any], key: str, fallback_key: str = "") -> dict[str, Any]:
    value = payload.get(key, payload.get(fallback_key, {})) if fallback_key else payload.get(key, {})
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise V2TemplateApiError("v2_payload_invalid", f"{key} 必须是 JSON 对象。")
    return dict(value)


def _required_text(payload: Mapping[str, Any], key: str, reason: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise V2TemplateApiError("v2_required_field_missing", reason)
    return value


def _state_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_id": state.get("template_id", ""),
        "template": dict(state.get("template", {})),
        "draft": dict(state["draft"]) if isinstance(state.get("draft"), Mapping) else None,
        "publication": dict(state.get("publication", {})),
        "versions": [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)],
    }


def _not_found(reason: str) -> V2TemplateApiError:
    return V2TemplateApiError(
        "v2_template_not_found",
        reason,
        status=HTTPStatus.NOT_FOUND,
        suggestion="请确认模板 ID 是否存在，或先创建模板草稿。",
    )


def _safe_reason(exc: BaseException) -> str:
    reason = str(exc).strip() or "请求内容不符合 V2 模板接口要求。"
    for marker in (":\\", "/", "Traceback", "HTTPStatus"):
        if marker in reason:
            return "请求内容不符合 V2 模板接口要求。"
    return reason


__all__ = ["V2TemplateApi", "V2TemplateApiError", "handle_v2_template_api"]
