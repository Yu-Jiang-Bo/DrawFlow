"""V2 template audit event helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .v2_template_errors import contains_sensitive_text


DEFAULT_V2_OPERATOR = "system/local-operator"


@dataclass(frozen=True)
class V2AuditEvent:
    event: str
    template_id: str
    draft_revision: str = ""
    operator: str = DEFAULT_V2_OPERATOR
    template_version: str = ""
    config_version: int | str = ""
    updated_at: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self, now: Callable[[], str] | None = None) -> dict[str, Any]:
        record = {
            "event": _safe_text(self.event),
            "template_id": _safe_text(self.template_id),
            "draft_revision": _safe_text(self.draft_revision),
            "operator": _safe_text(self.operator or DEFAULT_V2_OPERATOR),
            "template_version": _safe_text(self.template_version),
            "config_version": self.config_version if isinstance(self.config_version, int) else _safe_text(self.config_version),
            "updated_at": _safe_text(self.updated_at or (now or utc_now)()),
        }
        details = _sanitize_audit_value(self.details)
        if isinstance(details, Mapping) and details:
            record["details"] = dict(details)
        return record


class V2AuditRecorder:
    def __init__(self, log_path: Path | str, *, now: Callable[[], str] | None = None) -> None:
        self.log_path = Path(log_path)
        self.now = now or utc_now

    def append(self, event: V2AuditEvent) -> dict[str, Any]:
        record = event.to_record(self.now)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        return record

    def record(
        self,
        event: str,
        *,
        template_id: str,
        draft_revision: str = "",
        operator: str = DEFAULT_V2_OPERATOR,
        template_version: str = "",
        config_version: int | str = "",
        updated_at: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append(
            V2AuditEvent(
                event=event,
                template_id=template_id,
                draft_revision=draft_revision,
                operator=operator or DEFAULT_V2_OPERATOR,
                template_version=template_version,
                config_version=config_version,
                updated_at=updated_at,
                details=details or {},
            )
        )


def audit_event_from_state(
    event: str,
    state: Mapping[str, Any],
    draft: Mapping[str, Any] | None = None,
    *,
    operator: str = DEFAULT_V2_OPERATOR,
    updated_at: str = "",
    details: Mapping[str, Any] | None = None,
) -> V2AuditEvent:
    draft_record = state.get("draft", {})
    publication = state.get("publication", {})
    draft_payload = draft or {}
    manifest = draft_payload.get("manifest", {}) if isinstance(draft_payload, Mapping) else {}
    config = draft_payload.get("config", {}) if isinstance(draft_payload, Mapping) else {}
    audit = config.get("audit", {}) if isinstance(config, Mapping) else {}
    return V2AuditEvent(
        event=event,
        template_id=str(state.get("template_id") or ""),
        draft_revision=str(_mapping_get(draft_record, "revision") or _mapping_get(manifest, "draft_revision") or ""),
        operator=operator or DEFAULT_V2_OPERATOR,
        template_version=str(_mapping_get(publication, "current_version") or ""),
        config_version=_mapping_get(audit, "config_version") or "",
        updated_at=updated_at,
        details=details or {},
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mapping_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else ""


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    if contains_sensitive_text(text):
        return "[redacted]"
    return text


def _sanitize_audit_value(value: Any) -> Any:
    if isinstance(value, BaseException):
        return "[redacted]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        return [_sanitize_audit_value(item) for item in value]
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = _safe_text(key)
            if not key_text:
                continue
            sanitized[key_text] = _sanitize_audit_value(item)
        return sanitized
    return "[redacted]"


__all__ = [
    "DEFAULT_V2_OPERATOR",
    "V2AuditEvent",
    "V2AuditRecorder",
    "audit_event_from_state",
    "utc_now",
]
