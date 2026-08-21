"""One-shot HMAC challenges for trusted V2 preview workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .v2_preview_proof import normalize_preview_evidence, sample_rows_sha256, stable_json_sha256


PREVIEW_WORKER_SECRET_ENV = "DRAWFLOW_PREVIEW_WORKER_SECRET"
SIGNATURE_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class V2PreviewWorkerAuthError(ValueError):
    """Raised when a trusted preview worker cannot be authenticated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Challenge:
    challenge_id: str
    nonce: str
    template_id: str
    draft_revision: str
    worker_id: str
    expires_at: float


class V2PreviewWorkerChallengeRegistry:
    """Thread-safe, bounded, process-local challenge registry."""

    def __init__(
        self,
        secret: str | bytes | None = None,
        *,
        ttl_seconds: int = 120,
        max_pending: int = 4096,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._secret = _secret_bytes(secret)
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._max_pending = max(1, int(max_pending))
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._pending: dict[str, _Challenge] = {}

    def issue(self, template_id: str, draft_revision: str, *, worker_id: str = "") -> dict[str, Any]:
        self._require_configured()
        normalized_worker = _worker_id(worker_id)
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            if len(self._pending) >= self._max_pending:
                raise V2PreviewWorkerAuthError(
                    "preview_challenge_capacity",
                    "当前试渲染请求较多，请稍后重试。",
                )
            record = _Challenge(
                challenge_id=secrets.token_urlsafe(24),
                nonce=secrets.token_urlsafe(32),
                template_id=str(template_id),
                draft_revision=str(draft_revision),
                worker_id=normalized_worker,
                expires_at=now + self._ttl_seconds,
            )
            self._pending[record.challenge_id] = record
        return _public_challenge(record)

    def verify_and_consume(
        self,
        worker_proof: Mapping[str, Any],
        *,
        template_id: str,
        draft_revision: str,
        sample_rows: Sequence[Mapping[str, Any]],
        evidence: Mapping[str, Any],
    ) -> None:
        self._require_configured()
        submitted = _normalize_worker_proof(worker_proof)
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            record = self._pending.pop(submitted["challenge_id"], None)
            if record is None:
                raise _rejected("preview_challenge_unknown")
            if record.expires_at <= now:
                raise _rejected("preview_challenge_expired")
            if not _challenge_matches(record, submitted, template_id, draft_revision):
                raise _rejected("preview_challenge_mismatch")
            expected = _signature(
                self._secret,
                record.challenge_id,
                record.nonce,
                str(template_id),
                str(draft_revision),
                sample_rows,
                evidence,
                record.worker_id,
            )
            if not hmac.compare_digest(expected, submitted["signature"]):
                raise _rejected("preview_worker_signature_invalid")

    def _prune(self, now: float) -> None:
        expired = [key for key, value in self._pending.items() if value.expires_at <= now]
        for key in expired:
            self._pending.pop(key, None)

    def _require_configured(self) -> None:
        if len(self._secret) < 32:
            raise V2PreviewWorkerAuthError(
                "preview_worker_secret_missing",
                "真实试渲染服务尚未完成安全配置，请联系维护人员。",
            )


def sign_preview_worker_challenge(
    secret: str | bytes,
    challenge: Mapping[str, Any],
    *,
    template_id: str,
    draft_revision: str,
    sample_rows: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    worker_id: str = "",
) -> dict[str, str]:
    """Build the proof object submitted by a trusted local worker."""

    secret_bytes = _secret_bytes(secret, use_environment=False)
    if len(secret_bytes) < 32:
        raise V2PreviewWorkerAuthError("preview_worker_secret_invalid", "试渲染工作端安全配置无效。")
    challenge_id = str(challenge.get("challenge_id") or "").strip()
    nonce = str(challenge.get("nonce") or "").strip()
    bound_worker = _worker_id(worker_id or str(challenge.get("worker_id") or ""))
    if not challenge_id or not nonce:
        raise V2PreviewWorkerAuthError("preview_challenge_invalid", "试渲染凭证内容不完整。")
    signature = _signature(
        secret_bytes,
        challenge_id,
        nonce,
        str(template_id),
        str(draft_revision),
        sample_rows,
        evidence,
        bound_worker,
    )
    return {
        "challenge_id": challenge_id,
        "nonce": nonce,
        "worker_id": bound_worker,
        "signature": signature,
    }


def _signature(
    secret: bytes,
    challenge_id: str,
    nonce: str,
    template_id: str,
    draft_revision: str,
    sample_rows: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    worker_id: str,
) -> str:
    normalized_evidence = normalize_preview_evidence(evidence)
    message = {
        "challenge_id": challenge_id,
        "nonce": nonce,
        "template_id": template_id,
        "draft_revision": draft_revision,
        "sample_sha256": sample_rows_sha256(sample_rows),
        "evidence_sha256": stable_json_sha256(normalized_evidence),
        "worker_id": worker_id,
    }
    encoded = stable_json_sha256(message).encode("ascii")
    return hmac.new(secret, encoded, hashlib.sha256).hexdigest()


def _secret_bytes(value: str | bytes | None, *, use_environment: bool = True) -> bytes:
    if value is not None:
        raw: str | bytes = value
    else:
        raw = os.environ.get(PREVIEW_WORKER_SECRET_ENV, "") if use_environment else ""
    if isinstance(raw, bytes):
        return raw.strip()
    return str(raw).strip().encode("utf-8")


def _worker_id(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized and not WORKER_ID_PATTERN.fullmatch(normalized):
        raise V2PreviewWorkerAuthError("preview_worker_id_invalid", "试渲染工作端标识无效。")
    return normalized


def _normalize_worker_proof(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"challenge_id", "nonce", "worker_id", "signature"}:
        raise _rejected("preview_worker_proof_invalid")
    normalized = {key: str(value.get(key) or "").strip() for key in value}
    if not normalized["challenge_id"] or not normalized["nonce"]:
        raise _rejected("preview_worker_proof_invalid")
    normalized["worker_id"] = _worker_id(normalized["worker_id"])
    normalized["signature"] = normalized["signature"].lower()
    if not SIGNATURE_PATTERN.fullmatch(normalized["signature"]):
        raise _rejected("preview_worker_signature_invalid")
    return normalized


def _challenge_matches(
    record: _Challenge,
    submitted: Mapping[str, str],
    template_id: str,
    draft_revision: str,
) -> bool:
    return (
        submitted["nonce"] == record.nonce
        and submitted["worker_id"] == record.worker_id
        and str(template_id) == record.template_id
        and str(draft_revision) == record.draft_revision
    )


def _public_challenge(record: _Challenge) -> dict[str, Any]:
    expires = datetime.fromtimestamp(record.expires_at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "challenge_id": record.challenge_id,
        "nonce": record.nonce,
        "template_id": record.template_id,
        "expected_draft_revision": record.draft_revision,
        "worker_id": record.worker_id,
        "expires_at": expires,
    }


def _rejected(code: str) -> V2PreviewWorkerAuthError:
    return V2PreviewWorkerAuthError(code, "试渲染凭证无效或已失效，请重新试渲染。")


__all__ = [
    "PREVIEW_WORKER_SECRET_ENV",
    "V2PreviewWorkerAuthError",
    "V2PreviewWorkerChallengeRegistry",
    "sign_preview_worker_challenge",
]
