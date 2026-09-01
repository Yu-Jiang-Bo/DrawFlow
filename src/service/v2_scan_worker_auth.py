"""One-shot HMAC challenges for trusted V2 Illustrator scanners.

The server cannot inspect the fonts installed beside Illustrator.  It therefore
accepts an automatic tail profile only when a configured local scanner signs
the exact scan evidence for the current draft.  The challenge prevents a
browser from replaying or fabricating that assertion.
"""

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
from typing import Any, Callable, Mapping

from .v2_preview_proof import stable_json_sha256


SCAN_WORKER_SECRET_ENV = "DRAWFLOW_SCAN_WORKER_SECRET"
SIGNATURE_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class V2ScanWorkerAuthError(ValueError):
    """Raised when a trusted local scanner cannot be authenticated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _ScanChallenge:
    challenge_id: str
    nonce: str
    template_id: str
    draft_revision: str
    worker_id: str
    expires_at: float


class V2ScanWorkerChallengeRegistry:
    """Thread-safe, one-shot challenge registry for automatic tail scans."""

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
        self._pending: dict[str, _ScanChallenge] = {}

    def issue(self, template_id: str, draft_revision: str, *, worker_id: str = "") -> dict[str, Any]:
        self._require_configured()
        worker = _worker_id(worker_id)
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            if len(self._pending) >= self._max_pending:
                raise V2ScanWorkerAuthError("scan_challenge_capacity", "当前模板扫描请求较多，请稍后重试。")
            record = _ScanChallenge(
                challenge_id=secrets.token_urlsafe(24),
                nonce=secrets.token_urlsafe(32),
                template_id=str(template_id),
                draft_revision=str(draft_revision),
                worker_id=worker,
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
        evidence: Mapping[str, Any],
    ) -> str:
        self._require_configured()
        submitted = _normalize_worker_proof(worker_proof)
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            record = self._pending.pop(submitted["challenge_id"], None)
            if record is None:
                raise _rejected("scan_challenge_unknown")
            if record.expires_at <= now:
                raise _rejected("scan_challenge_expired")
            if not _challenge_matches(record, submitted, template_id, draft_revision):
                raise _rejected("scan_challenge_mismatch")
            expected = _signature(
                self._secret,
                record.challenge_id,
                record.nonce,
                str(template_id),
                str(draft_revision),
                evidence,
                record.worker_id,
            )
            if not hmac.compare_digest(expected, submitted["signature"]):
                raise _rejected("scan_worker_signature_invalid")
            return record.worker_id

    def _prune(self, now: float) -> None:
        for challenge_id in [key for key, value in self._pending.items() if value.expires_at <= now]:
            self._pending.pop(challenge_id, None)

    def _require_configured(self) -> None:
        if len(self._secret) < 32:
            raise V2ScanWorkerAuthError(
                "scan_worker_secret_missing",
                "自动尾巴扫描服务尚未完成安全配置，请联系维护人员。",
            )


def sign_scan_worker_challenge(
    secret: str | bytes,
    challenge: Mapping[str, Any],
    *,
    template_id: str,
    draft_revision: str,
    evidence: Mapping[str, Any],
    worker_id: str = "",
) -> dict[str, str]:
    """Sign the exact automatic Illustrator scan before upload to central."""

    secret_bytes = _secret_bytes(secret, use_environment=False)
    if len(secret_bytes) < 32:
        raise V2ScanWorkerAuthError("scan_worker_secret_invalid", "自动尾巴扫描安全配置无效。")
    challenge_id = str(challenge.get("challenge_id") or "").strip()
    nonce = str(challenge.get("nonce") or "").strip()
    worker = _worker_id(worker_id or str(challenge.get("worker_id") or ""))
    if not challenge_id or not nonce:
        raise V2ScanWorkerAuthError("scan_challenge_invalid", "自动尾巴扫描凭证内容不完整。")
    return {
        "challenge_id": challenge_id,
        "nonce": nonce,
        "worker_id": worker,
        "signature": _signature(secret_bytes, challenge_id, nonce, str(template_id), str(draft_revision), evidence, worker),
    }


def scan_evidence_sha256(evidence: Mapping[str, Any]) -> str:
    """Canonical digest that is signed before central adds its proof receipt."""

    return stable_json_sha256(dict(evidence))


def _signature(
    secret: bytes,
    challenge_id: str,
    nonce: str,
    template_id: str,
    draft_revision: str,
    evidence: Mapping[str, Any],
    worker_id: str,
) -> str:
    message = {
        "purpose": "v2_tail_profile_scan",
        "challenge_id": challenge_id,
        "nonce": nonce,
        "template_id": template_id,
        "draft_revision": draft_revision,
        "scan_evidence_sha256": scan_evidence_sha256(evidence),
        "worker_id": worker_id,
    }
    return hmac.new(secret, stable_json_sha256(message).encode("ascii"), hashlib.sha256).hexdigest()


def _secret_bytes(value: str | bytes | None, *, use_environment: bool = True) -> bytes:
    raw: str | bytes
    if value is not None:
        raw = value
    else:
        raw = os.environ.get(SCAN_WORKER_SECRET_ENV, "") if use_environment else ""
    return raw.strip() if isinstance(raw, bytes) else str(raw).strip().encode("utf-8")


def _worker_id(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized and not WORKER_ID_PATTERN.fullmatch(normalized):
        raise V2ScanWorkerAuthError("scan_worker_id_invalid", "自动尾巴扫描工作端标识无效。")
    return normalized


def _normalize_worker_proof(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"challenge_id", "nonce", "worker_id", "signature"}:
        raise _rejected("scan_worker_proof_invalid")
    normalized = {key: str(value.get(key) or "").strip() for key in value}
    if not normalized["challenge_id"] or not normalized["nonce"]:
        raise _rejected("scan_worker_proof_invalid")
    normalized["worker_id"] = _worker_id(normalized["worker_id"])
    normalized["signature"] = normalized["signature"].lower()
    if not SIGNATURE_PATTERN.fullmatch(normalized["signature"]):
        raise _rejected("scan_worker_signature_invalid")
    return normalized


def _challenge_matches(record: _ScanChallenge, submitted: Mapping[str, str], template_id: str, draft_revision: str) -> bool:
    return (
        submitted["nonce"] == record.nonce
        and submitted["worker_id"] == record.worker_id
        and str(template_id) == record.template_id
        and str(draft_revision) == record.draft_revision
    )


def _public_challenge(record: _ScanChallenge) -> dict[str, Any]:
    expires = datetime.fromtimestamp(record.expires_at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "challenge_id": record.challenge_id,
        "nonce": record.nonce,
        "template_id": record.template_id,
        "expected_draft_revision": record.draft_revision,
        "worker_id": record.worker_id,
        "expires_at": expires,
    }


def _rejected(code: str) -> V2ScanWorkerAuthError:
    return V2ScanWorkerAuthError(code, "自动尾巴扫描凭证无效或已失效，请重新扫描。")


__all__ = [
    "SCAN_WORKER_SECRET_ENV",
    "V2ScanWorkerAuthError",
    "V2ScanWorkerChallengeRegistry",
    "scan_evidence_sha256",
    "sign_scan_worker_challenge",
]
