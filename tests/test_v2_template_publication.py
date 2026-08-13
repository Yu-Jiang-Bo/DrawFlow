import hashlib
import json
from http import HTTPStatus

from src.service.v2_template_api import handle_v2_template_api
from tests.test_v2_template_api import FakeHandler
from tests.v2_publication_support import (
    prepared_draft,
    preview_evidence_for,
    publication_api,
    signed_preview_payload,
)


ROWS = [{"Name": "Amy", "Font": "F1", "Size": "small"}]


def test_trusted_worker_registers_proof_and_publish_retry_is_idempotent(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    challenge_result = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "preview-challenge"],
        {
            "expected_draft_revision": draft["manifest"]["draft_revision"],
            "worker_id": "windows-renderer-test",
        },
    )
    assert challenge_result.status == HTTPStatus.CREATED
    assert "trusted_preview_worker" in challenge_result.payload["service_contract"]["capabilities"]

    previewed = api.register_preview_proof(
        "V2API001",
        signed_preview_payload(api, draft, ROWS),
    )
    proof_draft = previewed["draft"]
    assert proof_draft["manifest"]["draft_revision"] != draft["manifest"]["draft_revision"]
    assert proof_draft["config"]["checks"]["preview"]["status"] == "confirmed"
    assert proof_draft["config"]["preview"]["evidence"]["draft_revision"] == draft["manifest"]["draft_revision"]
    assert previewed["validation"]["can_publish"] is True

    checked = api.publication_check(
        "V2API001",
        {"expected_draft_revision": proof_draft["manifest"]["draft_revision"]},
    )
    assert checked["validation"]["can_publish"] is True
    assert checked["publication"]["status"] == "draft"

    payload = {
        "expected_draft_revision": proof_draft["manifest"]["draft_revision"],
        "note": "样例通过",
    }
    first = api.publish("V2API001", payload)
    retry = api.publish("V2API001", payload)
    assert first["version"] == retry["version"] == "v0001"
    assert [item["version"] for item in retry["versions"]] == ["v0001"]
    version_manifest = json.loads(
        (tmp_path / "v2/V2API001/versions/v0001/manifest.json").read_text(encoding="utf-8")
    )
    assert version_manifest["source_draft_revision"] == proof_draft["manifest"]["draft_revision"]


def test_preview_evidence_hashes_explicit_ai_and_png_bytes(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    evidence = preview_evidence_for(draft, ROWS)
    key = "Output_main"
    ai_bytes = b"%!PS-Adobe-3.0\n%%Creator: DrawFlow Preview\n" + key.encode("utf-8")
    png_bytes = b"\x89PNG\r\n\x1a\nDrawFlow Preview Pixels:" + key.encode("utf-8")
    assert evidence["outputs"] == [
        {
            "key": key,
            "ai_sha256": hashlib.sha256(ai_bytes).hexdigest(),
            "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        }
    ]


def test_normal_save_invalidates_registered_preview_proof(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    previewed = api.register_preview_proof(
        "V2API001",
        signed_preview_payload(api, draft, ROWS),
    )
    resaved = api.save_draft("V2API001", {"config": previewed["draft"]["config"]})
    assert resaved["draft"]["config"]["preview"]["evidence"] == {}
    assert resaved["draft"]["config"]["checks"]["preview"] == {"status": "pending", "reason": ""}
    checked = api.publication_check(
        "V2API001",
        {"expected_draft_revision": resaved["draft"]["manifest"]["draft_revision"]},
    )
    assert checked["validation"]["can_publish"] is False
    assert checked["validation"]["checks"]["preview"]["status"] == "pending"


def test_draft_template_asset_download_is_manifest_bound(tmp_path):
    api = publication_api(tmp_path)
    draft = prepared_draft(api)
    handler = FakeHandler(api, {})
    assert handle_v2_template_api(
        handler,
        "GET",
        "/api/v2/templates/V2API001/draft/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "draft", "assets", "template.ai"],
    )
    sent = handler.sent_files[-1]
    assert sent["path"].read_bytes() == b"real-template-ai-source"
    assert sent["extra_headers"]["X-DrawFlow-SHA256"] == draft["manifest"]["assets"][0]["sha256"]

    bad_handler = FakeHandler(api, {})
    assert handle_v2_template_api(
        bad_handler,
        "GET",
        "/api/v2/templates/V2API001/draft/assets/other.ai",
        ["api", "v2", "templates", "V2API001", "draft", "assets", "other.ai"],
    )
    assert bad_handler.sent[-1][1] == HTTPStatus.NOT_FOUND
    assert not bad_handler.sent_files
