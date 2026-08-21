from copy import deepcopy
import json

import pytest

from src.service.v2_preview_worker_auth import (
    V2PreviewWorkerAuthError,
    sign_preview_worker_challenge,
)
from src.service.v2_template_api import V2TemplateApiError
from tests.v2_publication_support import (
    TEST_WORKER_ID,
    TEST_WORKER_SECRET,
    prepared_draft,
    preview_evidence_for,
    publication_api,
)


ROWS = [{"Name": "Amy", "Font": "F1", "Size": "small"}]


def challenge_and_proof(api, draft, evidence=None):
    revision = draft["manifest"]["draft_revision"]
    evidence = evidence or preview_evidence_for(draft, ROWS)
    challenge = api.preview_challenge(
        "V2API001",
        {"expected_draft_revision": revision, "worker_id": TEST_WORKER_ID},
    )["challenge"]
    proof = sign_preview_worker_challenge(
        TEST_WORKER_SECRET,
        challenge,
        template_id="V2API001",
        draft_revision=revision,
        sample_rows=ROWS,
        evidence=evidence,
        worker_id=TEST_WORKER_ID,
    )
    return challenge, proof, evidence


def registration_payload(draft, evidence, proof):
    return {
        "expected_draft_revision": draft["manifest"]["draft_revision"],
        "sample_rows": ROWS,
        "evidence": evidence,
        "worker_proof": proof,
    }


def test_missing_secret_is_business_rejection(tmp_path, monkeypatch):
    monkeypatch.delenv("DRAWFLOW_PREVIEW_WORKER_SECRET", raising=False)
    api = publication_api(tmp_path, secret=None)
    draft = prepared_draft(api)
    with pytest.raises(V2TemplateApiError) as error:
        api.preview_challenge(
            "V2API001",
            {"expected_draft_revision": draft["manifest"]["draft_revision"]},
        )
    assert error.value.status == 503
    assert "安全配置" in str(error.value)
    assert TEST_WORKER_SECRET not in str(error.value)


def test_environment_secret_issues_challenge_without_exposing_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAWFLOW_PREVIEW_WORKER_SECRET", TEST_WORKER_SECRET)
    api = publication_api(tmp_path, secret=None)
    draft = prepared_draft(api)
    result = api.preview_challenge(
        "V2API001",
        {"expected_draft_revision": draft["manifest"]["draft_revision"]},
    )
    assert result["challenge"]["challenge_id"]
    assert TEST_WORKER_SECRET not in json.dumps(result, ensure_ascii=False)


def test_self_consistent_browser_json_without_worker_proof_is_rejected(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    evidence = preview_evidence_for(draft, ROWS)
    with pytest.raises(V2TemplateApiError, match="凭证无效"):
        api.register_preview_proof(
            "V2API001",
            {
                "expected_draft_revision": draft["manifest"]["draft_revision"],
                "sample_rows": ROWS,
                "evidence": evidence,
            },
        )
    assert api.read_draft("V2API001")["manifest"]["draft_revision"] == draft["manifest"]["draft_revision"]


def test_forged_signature_consumes_challenge_and_replay_is_rejected(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    forged = dict(proof)
    forged["signature"] = ("0" if proof["signature"][0] != "0" else "1") + proof["signature"][1:]
    with pytest.raises(V2TemplateApiError, match="凭证无效"):
        api.register_preview_proof("V2API001", registration_payload(draft, evidence, forged))
    with pytest.raises(V2TemplateApiError, match="凭证无效"):
        api.register_preview_proof("V2API001", registration_payload(draft, evidence, proof))


def test_evidence_tampering_after_signature_is_rejected(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    tampered = deepcopy(evidence)
    tampered["warnings"] = ["签名后被修改"]
    with pytest.raises(V2TemplateApiError, match="凭证无效"):
        api.register_preview_proof("V2API001", registration_payload(draft, tampered, proof))


def test_expired_challenge_is_rejected(tmp_path):
    now = [100.0]
    api = publication_api(tmp_path, clock=lambda: now[0], ttl_seconds=2)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    now[0] = 102.0
    with pytest.raises(V2TemplateApiError, match="凭证无效"):
        api.register_preview_proof("V2API001", registration_payload(draft, evidence, proof))


@pytest.mark.parametrize("tampered_part", ["template", "worker", "nonce", "sample"])
def test_challenge_rejects_each_bound_input_tampering(tmp_path, tampered_part):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    revision = draft["manifest"]["draft_revision"]
    template_id = "V2API001"
    rows = ROWS
    submitted = dict(proof)
    if tampered_part == "template":
        template_id = "V2API002"
    elif tampered_part == "worker":
        submitted["worker_id"] = "another-worker"
    elif tampered_part == "nonce":
        submitted["nonce"] = "tampered-nonce"
    else:
        rows = [{"Name": "Bob", "Font": "F1", "Size": "small"}]
    with pytest.raises(V2PreviewWorkerAuthError):
        api.preview_worker_auth.verify_and_consume(
            submitted,
            template_id=template_id,
            draft_revision=revision,
            sample_rows=rows,
            evidence=evidence,
        )


def test_challenge_binds_revision_and_is_one_shot(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    revision = draft["manifest"]["draft_revision"]
    with pytest.raises(V2PreviewWorkerAuthError):
        api.preview_worker_auth.verify_and_consume(
            proof,
            template_id="V2API001",
            draft_revision="d9999",
            sample_rows=ROWS,
            evidence=evidence,
        )
    with pytest.raises(V2PreviewWorkerAuthError):
        api.preview_worker_auth.verify_and_consume(
            proof,
            template_id="V2API001",
            draft_revision=revision,
            sample_rows=ROWS,
            evidence=evidence,
        )


def test_correct_challenge_can_be_consumed_only_once(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    _challenge, proof, evidence = challenge_and_proof(api, draft)
    revision = draft["manifest"]["draft_revision"]
    api.preview_worker_auth.verify_and_consume(
        proof,
        template_id="V2API001",
        draft_revision=revision,
        sample_rows=ROWS,
        evidence=evidence,
    )
    with pytest.raises(V2PreviewWorkerAuthError):
        api.preview_worker_auth.verify_and_consume(
            proof,
            template_id="V2API001",
            draft_revision=revision,
            sample_rows=ROWS,
            evidence=evidence,
        )
