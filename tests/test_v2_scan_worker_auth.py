import pytest

from src.service.v2_scan_worker_auth import (
    V2ScanWorkerAuthError,
    V2ScanWorkerChallengeRegistry,
    sign_scan_worker_challenge,
)


SECRET = "test-scan-worker-secret-32-bytes-minimum---"
EVIDENCE = {"template_sha256": "a" * 64, "outputs": [{"key": "Output_main"}]}


def test_scan_worker_uses_its_own_secret_not_preview_secret(monkeypatch):
    monkeypatch.setenv("DRAWFLOW_PREVIEW_WORKER_SECRET", "preview-secret-which-must-not-authorize-scans")
    monkeypatch.delenv("DRAWFLOW_SCAN_WORKER_SECRET", raising=False)

    with pytest.raises(V2ScanWorkerAuthError) as error:
        V2ScanWorkerChallengeRegistry().issue("T1", "d0001", worker_id="scanner-1")

    assert error.value.code == "scan_worker_secret_missing"


def test_scan_worker_challenge_binds_current_draft_and_complete_evidence():
    registry = V2ScanWorkerChallengeRegistry(SECRET)
    challenge = registry.issue("T1", "d0001", worker_id="scanner-1")
    proof = sign_scan_worker_challenge(
        SECRET,
        challenge,
        template_id="T1",
        draft_revision="d0001",
        evidence=EVIDENCE,
        worker_id="scanner-1",
    )

    assert registry.verify_and_consume(
        proof,
        template_id="T1",
        draft_revision="d0001",
        evidence=EVIDENCE,
    ) == "scanner-1"
