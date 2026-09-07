from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import hashlib
import io

import pytest

from src.service import v2_template_api
from src.service.v2_template_api import V2TemplateApi, V2TemplateApiError, handle_v2_template_api
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_template_limits import V2TemplateLimitConfig, V2UploadConcurrencyGate
from src.service.v2_template_store import V2TemplateStore, V2TemplateStoreError
from src.service.v2_scan_worker_auth import scan_evidence_sha256, sign_scan_worker_challenge


def saveable_config(template_id="V2API001"):
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": template_id, "name": "API Demo"},
        "outputs": [
            {
                "key": "Output_main",
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "content_preset": "direct_text",
                            "slots": [{"key": "slot_name", "source_field": "name", "preset": "direct_text"}],
                        }
                    ],
                },
            }
        ],
        "field_bindings": {"name": "Name", "font": "Font"},
        "option_mappings": [
            {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main", "group": "font"}
        ],
    }


def pua_tail_config(template_id="V2API001"):
    config = saveable_config(template_id)
    config["outputs"][0]["font"]["options"][0]["font_dependencies"] = ["TailFont"]
    slot = config["outputs"][0]["font"]["options"][0]["slots"][0]
    slot["tails"] = [{"key": "tail_name_last_m", "position": "last", "sample": "m", "pua_base": 0xE040}]
    return config


def pua_tail_scan():
    scan = {"outputs": [{"design": {"options": []}, "font": {"options": [{"slots": [{"tails": [{
        "key": "tail_name_last_m", "position": "last", "sample": "m", "pua_base": 0xE040,
        "font_dependencies": ["TailFont"],
        "tail_profile_status": "auto", "tail_profile_coverage": {
            "version": 1, "alphabet": "abcdefghijklmnopqrstuvwxyz", "verified": True,
        },
    }]}]}]}}]}
    scan["tail_profile_proof"] = {
        "version": 1,
        "worker_id": "test-worker",
        "evidence_sha256": scan_evidence_sha256(scan),
    }
    return scan


def scan_evidence(template_sha256):
    return {
        "$schema": "custom-renderer/v2-template-scan",
        "scan_protocol_version": 1,
        "evidence": {
            "template_sha256": template_sha256,
            "scan_protocol_version": 1,
            "illustrator_version": "28.7.1",
            "scanned_at": "2026-08-07T00:00:00Z",
            "object_path_digest": "b" * 64,
        },
        "template": {"path": "Template"},
        "outputs": [{"key": "Output_main", "path": "Template/Output_main"}],
        "issues": [],
    }


def automatic_pua_scan_evidence(template_sha256):
    evidence = scan_evidence(template_sha256)
    evidence["outputs"][0]["font"] = {"options": [{"slots": [{"tails": [{
        "key": "tail_name_last_m",
        "position": "last",
        "sample": "m",
        "pua_base": 0xE040,
        "font_dependencies": ["TailFont"],
        "tail_profile_status": "auto",
        "tail_profile_coverage": {
            "version": 1,
            "alphabet": "abcdefghijklmnopqrstuvwxyz",
            "verified": True,
        },
    }]}]}]}
    return evidence




def api_for(tmp_path):
    return V2TemplateApi(V2TemplateStore(tmp_path / "v2"))


def trusted_tail_api(tmp_path):
    return V2TemplateApi(
        V2TemplateStore(tmp_path / "v2"),
        scan_worker_secret="test-scan-worker-secret-32-bytes-minimum---",
    )


def test_v2_api_creates_lists_and_reads_draft_with_optional_shop(tmp_path):
    api = api_for(tmp_path)

    created = api.handle(
        "POST",
        ["api", "v2", "templates"],
        {"template_id": "V2API001", "name": "API Demo", "shop_name": ""},
    )
    listed = api.handle("GET", ["api", "v2", "templates"]).payload
    draft = api.handle("GET", ["api", "v2", "templates", "V2API001", "draft"]).payload["draft"]

    assert created.status == HTTPStatus.CREATED
    assert created.payload["template"] == {"template_id": "V2API001", "name": "API Demo", "shop_name": ""}
    assert listed["templates"][0]["template"]["name"] == "API Demo"
    assert listed["templates"][0]["publication"]["status"] == "draft"
    assert draft["metadata"]["shop_name"] == ""
    api.store.publish_draft("V2API001")
    published_listed = api.handle("GET", ["api", "v2", "templates"]).payload

    assert published_listed["templates"][0]["template"]["name"] == "API Demo"
    assert published_listed["templates"][0]["publication"]["status"] == "active"
    assert not any("path" in key.lower() for key in published_listed["templates"][0])


def test_v2_api_reads_published_template_configuration_without_reading_the_local_ai(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2SHARED001", "name": "Shared demo"})
    api.store.save_draft(
        "V2SHARED001",
        metadata={"name": "Shared demo"},
        config=saveable_config("V2SHARED001"),
        scan={"outputs": [{"key": "Output_main", "path": "Template/Output_main"}]},
        assets=[{"filename": "template.ai", "role": "template", "content": b"ai-bytes"}],
    )
    api.store.publish_draft("V2SHARED001")

    response = api.handle("GET", ["api", "v2", "templates", "V2SHARED001", "published"])

    assert response.payload["published"]["config"]["template"]["template_id"] == "V2SHARED001"
    assert response.payload["published"]["scan"]["outputs"][0]["key"] == "Output_main"
    assert response.payload["published"]["manifest"]["version"] == "v0001"
    assert "published_template_read" in V2TemplateApi(api.store)._service_contract()["capabilities"]


def test_v2_api_preserves_source_version_for_writes_to_a_published_draft(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2SHARED001", "name": "Shared demo"})
    api.store.save_draft(
        "V2SHARED001",
        metadata={"name": "Shared demo"},
        config=saveable_config("V2SHARED001"),
        scan={"outputs": [{"key": "Output_main", "path": "Template/Output_main"}]},
        assets=[{"filename": "template.ai", "role": "template", "content": b"ai-bytes"}],
    )
    api.store.publish_draft("V2SHARED001")

    response = api.handle("POST", ["api", "v2", "templates", "V2SHARED001", "draft-from-published"])

    assert response.status == HTTPStatus.CREATED
    assert response.payload["draft"]["manifest"]["source_version"] == "v0001"
    assert response.payload["draft"]["config"]["template"]["template_id"] == "V2SHARED001"
    assert response.payload["draft"]["manifest"]["assets"][0]["file_name"] == "template.ai"

    saved = api.save_draft("V2SHARED001", {"config": response.payload["draft"]["config"]})
    assert saved["draft"]["manifest"]["source_version"] == "v0001"

    uploaded = api.upload_asset(
        "V2SHARED001",
        "template.ai",
        TrackingStream(b"updated-ai-bytes"),
        content_length=len(b"updated-ai-bytes"),
        headers={},
    )
    assert uploaded["draft"]["manifest"]["source_version"] == "v0001"

    scanned = api.submit_scan(
        "V2SHARED001",
        {"evidence": scan_evidence(uploaded["asset"]["sha256"])},
    )
    assert scanned["draft"]["manifest"]["source_version"] == "v0001"


def test_v2_api_returns_a_public_error_when_shared_version_is_unavailable(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2DRAFT001", "name": "Draft only"})

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("GET", ["api", "v2", "templates", "V2DRAFT001", "published"])

    assert exc_info.value.problem.code == "v2_published_template_unavailable"


def test_v2_api_does_not_reset_existing_template_for_case_only_id_change(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "Test", "name": "Original"})
    uploaded = api.upload_asset("Test", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    api.store.publish_draft("Test")
    before = api.read_draft("Test")
    versions_before = api.read_versions("Test")

    reused = api.create_template({"template_id": "test", "name": "Replacement"})
    after = api.read_draft("Test")

    assert reused["template"]["template_id"] == "Test"
    assert reused["template"]["name"] == "Original"
    assert after["manifest"]["draft_revision"] == before["manifest"]["draft_revision"]
    assert after["manifest"]["assets"][0]["sha256"] == uploaded["asset"]["sha256"]
    assert api.read_versions("Test") == versions_before


def test_v2_api_case_only_concurrent_creates_keep_one_template_state(tmp_path):
    api = api_for(tmp_path)

    def create(template_id):
        return api.create_template({"template_id": template_id, "name": template_id})

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(create, ["Test", "test"]))

    templates = api.list_templates()
    assert len(templates) == 1
    assert {item["template"]["template_id"] for item in created} == {templates[0]["template"]["template_id"]}
    assert api.read_draft(templates[0]["template"]["template_id"])["manifest"]["draft_revision"] == "d0001"


def test_v2_api_creates_distinct_template_ids_independently(tmp_path):
    api = api_for(tmp_path)

    first = api.create_template({"template_id": "TestA", "name": "First"})
    second = api.create_template({"template_id": "TestB", "name": "Second"})

    assert first["template"]["template_id"] == "TestA"
    assert second["template"]["template_id"] == "TestB"
    assert {item["template"]["template_id"] for item in api.list_templates()} == {"TestA", "TestB"}


def test_v2_api_saves_draft_config_without_accepting_untrusted_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    saved = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "draft"],
        {"config": saveable_config()},
    ).payload
    scan = api.handle("GET", ["api", "v2", "templates", "V2API001", "scan"]).payload

    assert saved["validation"]["can_save"] is True
    assert saved["validation"]["can_publish"] is False
    assert any(issue["code"] == "render_mode_pending" for issue in saved["validation"]["issues"])
    assert saved["draft"]["config"]["template"]["template_id"] == "V2API001"
    assert "render_mode" not in saved["draft"]["config"]
    assert scan == {"template_id": "V2API001", "draft_revision": "d0002", "scan": {}}

    with pytest.raises(V2TemplateApiError, match="未开放"):
        api.save_draft("V2API001", {"config": saveable_config(), "scan": {"scan_version": "fake"}})

    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rejects_unproven_pua_tail_and_accepts_exact_auto_scan_proof(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    with pytest.raises(V2TemplateApiError, match="尾巴字形缺少"):
        api.save_draft("V2API001", {"config": pua_tail_config()})
    validation = api.validate_config({"config": pua_tail_config()})["validation"]
    assert validation["can_save"] is False
    assert any(issue["code"] == "tail_pua_profile_unverified" for issue in validation["issues"])

    api.store.save_draft(
        "V2API001",
        metadata={"template_id": "V2API001", "name": "API Demo"},
        scan=pua_tail_scan(),
    )
    saved = api.save_draft("V2API001", {"config": pua_tail_config()})

    assert saved["validation"]["can_save"] is True
    assert saved["draft"]["config"]["outputs"][0]["font"]["options"][0]["slots"][0]["tails"][0]["pua_base"] == 0xE040


def test_v2_api_rejects_signed_tail_profile_when_render_font_is_changed(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.store.save_draft(
        "V2API001",
        metadata={"template_id": "V2API001", "name": "API Demo"},
        scan=pua_tail_scan(),
    )
    config = pua_tail_config()
    config["outputs"][0]["font"]["options"][0]["font_dependencies"] = ["UnrelatedFont"]

    with pytest.raises(V2TemplateApiError, match="尾巴字形缺少"):
        api.save_draft("V2API001", {"config": config})
    validation = api.validate_config({"config": config})["validation"]
    assert any(issue["code"] == "tail_font_dependency_unverified" for issue in validation["issues"])


def test_v2_api_rejects_forged_auto_pua_scan_and_accepts_signed_current_scan(tmp_path):
    api = trusted_tail_api(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = automatic_pua_scan_evidence(uploaded["asset"]["sha256"])

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.submit_scan("V2API001", {"evidence": evidence})
    assert exc_info.value.problem.code == "v2_required_field_missing"
    assert api.read_draft("V2API001")["scan"] == {}

    revision = api.read_draft("V2API001")["manifest"]["draft_revision"]
    challenge = api.scan_challenge(
        "V2API001",
        {"expected_draft_revision": revision, "worker_id": "windows-scanner-test"},
    )["challenge"]
    proof = sign_scan_worker_challenge(
        "test-scan-worker-secret-32-bytes-minimum---",
        challenge,
        template_id="V2API001",
        draft_revision=revision,
        evidence=evidence,
        worker_id="windows-scanner-test",
    )
    stored = api.submit_scan(
        "V2API001",
        {
            "evidence": evidence,
            "expected_draft_revision": revision,
            "worker_proof": proof,
        },
    )
    assert stored["scan"]["tail_profile_proof"]["worker_id"] == "windows-scanner-test"
    assert stored["scan"]["tail_profile_proof"]["evidence_sha256"] == scan_evidence_sha256(evidence)

    saved = api.save_draft("V2API001", {"config": pua_tail_config()})
    assert saved["validation"]["can_save"] is True


def test_v2_api_rebuilds_config_scan_audit_from_trusted_draft_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.store.save_draft(
        "V2API001",
        metadata={"template_id": "V2API001", "name": "API Demo"},
        scan={"scan_version": "trusted-scan", "template_sha256": "trusted-sha"},
    )
    forged = saveable_config()
    forged["audit"] = {
        "scan_version": "browser-forged-scan",
        "template_sha256": "browser-forged-sha",
        "config_version": 4,
    }

    saved = api.save_draft("V2API001", {"config": forged})

    assert saved["draft"]["config"]["audit"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
        "config_version": 4,
    }
    assert saved["validation"]["contract"]["audit"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
        "config_version": 4,
    }
    assert api.read_draft("V2API001")["scan"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
    }


def test_v2_api_accepts_trusted_local_scan_for_current_ai_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = scan_evidence(uploaded["asset"]["sha256"])

    result = api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": evidence}).payload

    assert result["state"]["draft"]["revision"] == "d0003"
    assert result["scan"] == evidence
    assert result["draft"]["scan"] == evidence
    assert result["draft"]["manifest"]["assets"][0]["sha256"] == uploaded["asset"]["sha256"]


def test_v2_api_save_config_preserves_uploaded_ai_and_trusted_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = scan_evidence(uploaded["asset"]["sha256"])
    api.submit_scan("V2API001", {"evidence": evidence})

    saved = api.save_draft("V2API001", {"config": saveable_config()})

    assets = saved["draft"]["manifest"]["assets"]
    assert len(assets) == 1
    assert assets[0]["file_name"] == "template.ai"
    assert assets[0]["sha256"] == uploaded["asset"]["sha256"]
    assert saved["draft"]["scan"] == evidence
    stored = api.store._draft_dir("V2API001", saved["draft"]["manifest"]["draft_revision"]) / assets[0]["path"]
    assert stored.read_bytes() == b"ai-bytes"


def test_v2_api_validation_advertises_current_workbench_capabilities(tmp_path):
    api = api_for(tmp_path)

    result = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "validate"],
        {"config": saveable_config()},
    ).payload

    assert result["service_contract"]["version"] == 6
    assert "mixed_slot_processing" in result["service_contract"]["capabilities"]
    assert "editable_validation_targets" in result["service_contract"]["capabilities"]
    assert "trusted_preview_worker" in result["service_contract"]["capabilities"]
    assert "trusted_tail_profile_scanner" in result["service_contract"]["capabilities"]
    assert "published_template_read" in result["service_contract"]["capabilities"]


def test_v2_api_validates_and_saves_legacy_font_slots_as_clean_config(tmp_path):
    api = api_for(tmp_path)
    config = saveable_config()
    output = config["outputs"][0]
    output["path"] = "Template/Output_main"
    output["font"]["path"] = "Template/Output_main/Font"
    output["font"]["options"] = [
        {
            "key": f"F{index}",
            "content_preset": "direct_text",
            "path": f"Template/Output_main/Font/F{index}",
            "fixed_object_count": 0,
            "fixed_objects": [],
            "slots": [
                {
                    "key": "slot_name",
                    "source_field": "name",
                    "preset": "direct_text",
                    "path": f"Template/Output_main/Font/F{index}/slot_name",
                    "type": "TextFrame",
                    "text_kind": "point_text",
                    "visible_bounds": [1, 2, 3, 4],
                    "dimensions": {"width_mm": 15.619, "height_mm": 8.49},
                }
            ],
        }
        for index in range(1, 13)
    ]
    config["option_mappings"] = [
        {"field": "font", "source_value": f"F{index}", "target": f"F{index}", "output": "Output_main", "group": "font"}
        for index in range(1, 13)
    ]

    validation = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "validate"],
        {"config": config},
    ).payload["validation"]

    assert validation["can_save"] is True
    assert not any(issue["code"] == "contract_invalid" for issue in validation["issues"])

    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    saved = api.save_draft("V2API001", {"config": config})

    fonts = saved["draft"]["config"]["outputs"][0]["font"]["options"]
    assert saved["validation"]["can_save"] is True
    assert len(fonts) == 12
    for font in fonts:
        assert len(font["slots"]) == 1
        slot = font["slots"][0]
        assert slot["key"] == "slot_name"
        assert slot["source_field"] == "name"
        assert slot["dimension_rule"] == {"mode": "slot", "width_mm": 15.619, "height_mm": 8.49}
        assert not {"path", "type", "text_kind", "visible_bounds", "dimensions"} & set(slot)


def test_v2_api_rejects_scan_missing_trusted_contract_fields(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    forged = {
        "evidence": {"template_sha256": uploaded["asset"]["sha256"]},
        "outputs": [{"key": "Output_main", "path": "Template/Output_main"}],
        "issues": [],
    }

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": forged})

    assert exc_info.value.problem.code == "v2_scan_evidence_invalid"
    assert api.read_draft("V2API001")["scan"] == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("illustrator_version", "x"),
        ("illustrator_version", "29.beta"),
        ("scanned_at", "not-a-time"),
        ("scanned_at", "2026-08-07T00:00:00"),
        ("scanned_at", "2026-08-07 00:00:00+00:00"),
        ("scanned_at", "2026-08-07X00:00:00+00:00"),
    ],
)
def test_v2_api_rejects_scan_with_malformed_trusted_contract_fields(tmp_path, field, value):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = scan_evidence(uploaded["asset"]["sha256"])
    evidence["evidence"][field] = value

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": evidence})

    assert exc_info.value.problem.code == "v2_scan_evidence_invalid"
    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_reuploading_template_ai_clears_stale_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"old-ai"), content_length=6, headers={})
    evidence = scan_evidence(uploaded["asset"]["sha256"])
    api.submit_scan("V2API001", {"evidence": evidence})

    result = api.upload_asset("V2API001", "template.ai", TrackingStream(b"new-ai"), content_length=6, headers={})

    assert result["draft"]["scan"] == {}
    assert api.read_draft("V2API001")["scan"] == {}
    assert result["asset"]["sha256"] == hashlib.sha256(b"new-ai").hexdigest()
    assert result["asset"]["sha256"] != uploaded["asset"]["sha256"]


def test_v2_api_rejects_scan_sha_mismatch_without_replacing_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    mismatch = scan_evidence("0" * 64)

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": mismatch})

    assert exc_info.value.problem.code == "v2_scan_template_sha_mismatch"
    assert exc_info.value.status == HTTPStatus.CONFLICT
    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rejects_scan_without_uploaded_template_ai_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": scan_evidence("a" * 64)})

    assert exc_info.value.problem.code == "v2_template_ai_asset_missing"
    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rejects_scan_without_template_sha_or_structure(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    missing_sha = scan_evidence("")

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": missing_sha})
    assert exc_info.value.problem.code == "v2_scan_template_sha_missing"

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": {"template_sha256": "a" * 64}})
    assert exc_info.value.problem.code == "v2_scan_evidence_empty"
    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rejects_blocked_scan_evidence(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    blocked = scan_evidence(uploaded["asset"]["sha256"])
    blocked["blocked"] = True
    blocked["issues"] = [{"status": "blocked", "code": "template_root_missing", "reason": "缺少 Template 根组。"}]

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": blocked})

    assert exc_info.value.problem.code == "v2_scan_evidence_blocked"
    assert api.read_draft("V2API001")["scan"] == {}


@pytest.mark.parametrize(
    "issue",
    [
        {"status": "blocked", "code": "duplicate_name", "reason": "同一作用域名称重复。"},
        {"status": "blocking", "code": "duplicate_name", "reason": "同一作用域名称重复。"},
        {"status": "failed", "code": "scan_failed", "reason": "扫描失败。"},
        {"severity": "error", "code": "scan_failed", "reason": "扫描失败。"},
    ],
)
def test_v2_api_rejects_scan_evidence_with_blocking_issue_status(tmp_path, issue):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = scan_evidence(uploaded["asset"]["sha256"])
    evidence["blocked"] = False
    evidence["issues"] = [issue]

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": evidence})

    assert exc_info.value.problem.code == "v2_scan_evidence_blocked"
    assert api.read_draft("V2API001")["scan"] == {}


@pytest.mark.parametrize(
    "shell",
    [
        {"template": {"path": "Template"}},
        {"recommendations": [{"status": "pending", "preset": "direct_text"}]},
        {"dependencies": {"fonts": [{"font_name": "Milkshake"}]}},
    ],
)
def test_v2_api_rejects_scan_shells_without_outputs(tmp_path, shell):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    uploaded = api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai-bytes"), content_length=8, headers={})
    evidence = {"evidence": {"template_sha256": uploaded["asset"]["sha256"]}, **shell}

    with pytest.raises(V2TemplateApiError) as exc_info:
        api.handle("POST", ["api", "v2", "templates", "V2API001", "scan"], {"evidence": evidence})

    assert exc_info.value.problem.code == "v2_scan_evidence_empty"
    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rejects_malicious_config_without_changing_current_draft(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})

    with pytest.raises(V2TemplateApiError, match="草稿未保存"):
        api.save_draft("V2API001", {"config": {"natural_text": "Name odd red even white"}})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {}


def test_v2_api_rejects_config_template_id_mismatch_without_saving(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})
    mismatched = saveable_config("V2OTHER001")

    with pytest.raises(V2TemplateApiError, match="模板 ID 不一致"):
        api.save_draft("V2API001", {"config": mismatched})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {}


def test_v2_validation_endpoint_does_not_create_template_state(tmp_path):
    api = api_for(tmp_path)

    result = api.handle(
        "POST",
        ["api", "v2", "templates", "V2NOOP001", "validate"],
        {"config": {"natural_text": "Name odd red even white"}},
    ).payload

    assert result["validation"]["can_save"] is False
    assert api.list_templates() == []


def test_v2_api_versions_include_current_and_rollback(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.store.publish_draft("V2API001")
    api.save_draft("V2API001", {"config": saveable_config()})
    api.store.publish_draft("V2API001")

    versions = api.handle("GET", ["api", "v2", "templates", "V2API001", "versions"]).payload

    assert versions["publication"] == {"status": "active", "current_version": "v0002", "rollback_version": "v0001"}
    assert [item["version"] for item in versions["versions"]] == ["v0001", "v0002"]


def test_v2_api_concurrent_draft_reads_are_stable(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})

    def read_revision():
        draft = api.handle("GET", ["api", "v2", "templates", "V2API001", "draft"]).payload["draft"]
        return draft["manifest"]["draft_revision"], draft["config"]["template"]["template_id"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: read_revision(), range(20)))

    assert set(results) == {("d0002", "V2API001")}


def test_v2_http_bridge_handles_only_v2_routes_and_sanitizes_errors(tmp_path):
    handler = FakeHandler(api_for(tmp_path), {"template_id": "V2API001", "name": "API Demo"})

    assert handle_v2_template_api(handler, "GET", "/api/templates", ["api", "templates"]) is False
    assert handle_v2_template_api(handler, "POST", "/api/v2/templates", ["api", "v2", "templates"]) is True
    assert handler.sent[-1][1] == HTTPStatus.CREATED

    handler.payload = {"config": {"natural_text": "Name odd red even white"}}
    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/draft",
        ["api", "v2", "templates", "V2API001", "draft"],
    )
    error = handler.sent[-1][0]["error"]
    assert handler.sent[-1][1] == HTTPStatus.BAD_REQUEST
    assert error["code"] == "v2_config_rejected"
    assert "Traceback" not in str(error)
    assert "C:" not in str(error)


def test_v2_api_uploads_ai_asset_as_stream_and_records_manifest_metadata(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    stream = TrackingStream(b"ai-bytes")

    result = api.upload_asset(
        "V2API001",
        "template.ai",
        stream,
        content_length=len(b"ai-bytes"),
        headers={
            "Content-Type": "application/illustrator",
            "X-DrawFlow-Asset-Role": "template",
            "X-DrawFlow-Scan-Version": "scan-1",
        },
    )

    asset = result["asset"]
    assert stream.read_sizes == [1024 * 1024, 1024 * 1024]
    assert asset["file_name"] == "template.ai"
    assert asset["path"] == "assets/template.ai"
    assert asset["size_bytes"] == len(b"ai-bytes")
    assert asset["sha256"] == hashlib.sha256(b"ai-bytes").hexdigest()
    assert asset["mime_type"] == "application/illustrator"
    assert asset["scan_version"] == "scan-1"
    assert asset["draft_revision"] == result["state"]["draft"]["revision"]
    assert (tmp_path / "v2" / "audit.jsonl").read_text(encoding="utf-8")


def test_v2_api_uses_a_short_upload_staging_path(tmp_path, monkeypatch):
    store = V2TemplateStore(tmp_path / "central" / "v2-templates")
    api = V2TemplateApi(store)
    api.create_template({"template_id": "JJMB202511201110061195", "name": "API Demo"})
    captured = {}

    def record_destination(*args, **kwargs):
        captured["directory"] = args[1]
        raise V2TemplateStoreError("upload staging captured")

    monkeypatch.setattr(v2_template_api, "receive_ai_stream", record_destination)
    with pytest.raises(V2TemplateStoreError, match="upload staging captured"):
        api.upload_asset(
            "JJMB202511201110061195",
            "JJMB202511201110061195.ai",
            TrackingStream(b"ai-bytes"),
            content_length=8,
            headers={},
        )

    assert captured["directory"].parent == tmp_path / "central" / "_tmp"
    assert "JJMB202511201110061195" not in {path.name for path in captured["directory"].parents}


def test_v2_http_upload_reads_only_declared_content_length(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai-extra-bytes")
    handler.headers = {"Content-Length": "2"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    asset = handler.sent[-1][0]["asset"]
    assert handler.sent[-1][1] == HTTPStatus.CREATED
    assert asset["size_bytes"] == 2
    assert asset["sha256"] == hashlib.sha256(b"ai").hexdigest()
    assert handler.rfile.tell() == 2
    assert handler.rfile.read_sizes == [2]


def test_v2_http_upload_short_body_fails_without_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai")
    handler.headers = {"Content-Length": "4"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "stream_interrupted"
    assert api.read_draft("V2API001")["manifest"]["assets"] == []


def test_v2_upload_interruption_does_not_replace_current_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"old-ai"), content_length=6, headers={})
    previous = api.read_draft("V2API001")

    with pytest.raises(Exception):
        api.upload_asset(
            "V2API001",
            "template.ai",
            TrackingStream(b"new-ai", fail_on_read=1),
            content_length=6,
            headers={},
        )

    current = api.read_draft("V2API001")
    assert current["manifest"]["draft_revision"] == previous["manifest"]["draft_revision"]
    assert current["manifest"]["assets"][0]["sha256"] == hashlib.sha256(b"old-ai").hexdigest()


def test_v2_upload_limits_return_public_chinese_problem_payload(tmp_path):
    api = V2TemplateApi(
        V2TemplateStore(tmp_path / "v2"),
        limits=V2TemplateLimitConfig(max_file_size_bytes=4, temp_dir=tmp_path / "tmp", min_free_space_bytes=0),
    )
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"too-large")
    handler.headers = {"Content-Length": "9"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert error["error"]["code"] == "v2_file_too_large"
    assert "Traceback" not in str(error)
    assert "C:" not in str(error)
    assert handler.rfile.read_sizes == []


def test_v2_upload_concurrency_returns_conflict_without_consuming_body(tmp_path):
    limits = V2TemplateLimitConfig(max_concurrent_uploads=1, temp_dir=tmp_path / "tmp", min_free_space_bytes=0)
    gate = V2UploadConcurrencyGate(limits)
    api = V2TemplateApi(V2TemplateStore(tmp_path / "v2"), limits=limits, upload_gate=gate)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai")
    handler.headers = {"Content-Length": "2"}

    with gate.acquire():
        assert handle_v2_template_api(
            handler,
            "POST",
            "/api/v2/templates/V2API001/assets/template.ai",
            ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
        )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.CONFLICT
    assert error["error"]["code"] == "v2_upload_concurrency_exceeded"
    assert handler.rfile.read_sizes == []


def test_v2_upload_rejects_official_order_output_without_consuming_body(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"finished-order")
    handler.headers = {"Content-Length": "14", "X-DrawFlow-Asset-Role": "official_order_output"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/finished-order.ai",
        ["api", "v2", "templates", "V2API001", "assets", "finished-order.ai"],
    )

    error, status = handler.sent[-1]
    draft = api.read_draft("V2API001")
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "v2_official_order_output_upload_forbidden"
    assert "正式订单成品" in error["error"]["reason"]
    assert handler.rfile.read_sizes == []
    assert draft["manifest"]["assets"] == []


def test_v2_http_bridge_logs_internal_code_and_cause_chain(tmp_path, caplog):
    handler = FakeHandler(api_for(tmp_path), {"unknown": "field"})

    assert handle_v2_template_api(handler, "POST", "/api/v2/templates", ["api", "v2", "templates"])

    error, status = handler.sent[-1]
    log_text = caplog.text
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "v2_payload_rejected"
    assert "internal_code" in log_text
    assert "v2_payload_rejected" in log_text
    assert "cause_chain" in log_text
    assert "V2TemplateApiError" in log_text


def test_v2_http_bridge_logs_streamed_asset_io_cause_without_exposing_path(caplog):
    private_path = r"C:\\private\\v2\\template.ai"

    class FailingApi:
        def handle(self, method, parts, payload):
            try:
                raise FileNotFoundError(private_path)
            except FileNotFoundError as exc:
                raise V2TemplateStoreError("V2 storage write failed") from exc

    handler = FakeHandler(FailingApi(), {})

    assert handle_v2_template_api(handler, "GET", "/api/v2/templates", ["api", "v2", "templates"])

    error, status = handler.sent[-1]
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "v2_invalid_request"
    assert private_path not in str(error)
    assert "FileNotFoundError" in caplog.text
    assert private_path in caplog.text


def test_v2_bundle_download_bridge_streams_zip_file(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai"), content_length=2, headers={})
    api.store.publish_draft("V2API001")
    handler = FakeHandler(api, {})

    assert handle_v2_template_api(
        handler,
        "GET",
        "/api/v2/templates/V2API001/versions/v0001/bundle",
        ["api", "v2", "templates", "V2API001", "versions", "v0001", "bundle"],
    )

    sent_file = handler.sent_files[-1]
    assert sent_file["content_type"] == "application/zip"
    assert sent_file["path"].name == "template-bundle.zip"
    assert sent_file["extra_headers"]["X-DrawFlow-SHA256"]
    assert not handler.sent


def test_v2_maintenance_endpoint_does_not_pollute_template_list(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    listed = api.handle("GET", ["api", "v2", "templates"]).payload
    maintenance = api.handle("GET", ["api", "v2", "templates", "maintenance"]).payload["maintenance"]

    assert [item["template_id"] for item in listed["templates"]] == ["V2API001"]
    assert maintenance["summary"]["total"] == 1
    assert not any(
        marker in str(maintenance).lower()
        for marker in ("disk", "free_bytes", "used_bytes", "capacity", "c:\\", "/users/")
    )


class FakeHandler:
    def __init__(self, api, payload):
        self.v2_template_api = api
        self.payload = payload
        self.sent = []
        self.sent_files = []
        self.headers = {}
        self.rfile = io.BytesIO()

    def _read_json(self):
        return self.payload

    def _send_json(self, payload, status=HTTPStatus.OK):
        self.sent.append((payload, status))

    def _send_file_stream(self, path, *, content_type, download_name, extra_headers=None):
        self.sent_files.append(
            {
                "path": path,
                "content_type": content_type,
                "download_name": download_name,
                "extra_headers": extra_headers or {},
            }
        )


class TrackingStream(io.BytesIO):
    def __init__(self, payload: bytes, *, fail_on_read: int | None = None):
        super().__init__(payload)
        self.fail_on_read = fail_on_read
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("V2 upload must not use unbounded read()")
        if self.fail_on_read is not None and len(self.read_sizes) >= self.fail_on_read:
            raise OSError("stream dropped")
        return super().read(size)
