from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from src.service.local_client import LocalClientError, LocalDrawFlowClient
from src.service.v2_preview_worker_auth import V2PreviewWorkerAuthError
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_trial_render_support import download_asset, required_fonts


WORKER_SECRET = "preview-worker-secret-for-tests-1234567890"


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def make_draft(template_digest):
    config = {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": "V2TRIAL001", "name": "Trial demo"},
        "outputs": [{
            "key": "Output_main",
            "display_name": "主效果图",
            "font": {"field": "font", "options": [{
                "key": "F1", "content_preset": "direct_text", "font_dependencies": [],
                "slots": [{
                    "key": "slot_name", "source_field": "name", "required": True,
                    "preset": "direct_text", "font_dependencies": [],
                }],
            }]},
        }],
        "field_bindings": {"font": "Font", "name": "Name"},
        "option_mappings": [{
            "field": "font", "source_value": "F1", "target": "F1",
            "output": "Output_main", "group": "font",
        }],
        "audit": {
            "scan_version": "scan-1", "template_sha256": template_digest, "config_version": 7,
        },
    }
    scan = {
        "$schema": "custom-renderer/v2-template-scan", "scan_protocol_version": 1,
        "evidence": {
            "template_sha256": template_digest, "scan_protocol_version": 1,
            "illustrator_version": "29.0", "scanned_at": "2026-08-12T00:00:00Z",
            "object_path_digest": "c" * 64,
        },
        "template": {"path": "Template"},
        "outputs": [{
            "key": "Output_main", "path": "Template/Output_main", "styles": [], "designs": [],
            "fonts": [{
                "key": "F1", "path": "Template/Output_main/Font/F1",
                "slots": [{"key": "slot_name", "path": "Template/Output_main/Font/F1/slot_name"}],
                "anchors": [], "tails": [],
            }],
        }],
        "dependencies": {"fonts": []}, "issues": [], "blocked": False,
    }
    return {
        "manifest": {
            "draft_revision": "d0004", "scan_sha256": "b" * 64,
            "assets": [{
                "file_name": "template.ai", "role": "template",
                "extension": ".ai", "sha256": template_digest,
            }],
        },
        "metadata": {"template_id": "V2TRIAL001", "name": "Trial demo"},
        "config": config, "scan": scan,
    }


def make_multi_output_draft(template_digest):
    draft = make_draft(template_digest)
    config = draft["config"]
    scan = draft["scan"]
    base_config_output = config["outputs"][0]
    base_scan_output = scan["outputs"][0]
    outputs = []
    scan_outputs = []
    mappings = []
    bindings = {}
    for side, display_name in (("A", "正面效果图"), ("B", "背面效果图")):
        output_key = f"Output_Side{side}"
        font_field = f"font_{side.lower()}"
        name_field = f"name_{side.lower()}"
        output = deepcopy(base_config_output)
        output["key"] = output_key
        output["display_name"] = display_name
        output["font"]["field"] = font_field
        output["font"]["options"][0]["slots"][0]["source_field"] = name_field
        outputs.append(output)
        scan_output = deepcopy(base_scan_output)
        scan_output["key"] = output_key
        scan_output["path"] = f"Template/{output_key}"
        scan_output["fonts"][0]["path"] = f"Template/{output_key}/Font/F1"
        scan_output["fonts"][0]["slots"][0]["path"] = (
            f"Template/{output_key}/Font/F1/slot_name"
        )
        scan_outputs.append(scan_output)
        mappings.append({
            "field": font_field,
            "source_value": "F1",
            "target": "F1",
            "output": output_key,
            "group": "font",
        })
        bindings[font_field] = f"Font {side}"
        bindings[name_field] = f"Name {side}"
    config["outputs"] = outputs
    config["field_bindings"] = bindings
    config["option_mappings"] = mappings
    scan["outputs"] = scan_outputs
    return draft


def test_required_fonts_ignores_font_option_marker_self_dependencies():
    draft = make_draft("a" * 64)
    option = draft["config"]["outputs"][0]["font"]["options"][0]
    option["font_dependencies"] = ["F1", "Adelia"]
    option["slots"][0]["font_dependencies"] = ["F1", "Adelia"]

    assert required_fonts(draft["config"], draft["scan"]) == ["Adelia"]


class TrialCentral:
    def __init__(self, draft, template_bytes):
        self.draft = draft
        self.template_bytes = template_bytes
        self.proof = None
        self.challenge_requests = []

    def get_v2_draft(self, template_id):
        assert template_id == "V2TRIAL001"
        return self.draft

    def download_v2_draft_asset(self, template_id, file_name, target_path, *, expected_sha256):
        assert (template_id, file_name) == ("V2TRIAL001", "template.ai")
        assert expected_sha256 == sha256_bytes(self.template_bytes)
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(self.template_bytes)

    def request_v2_preview_challenge(self, template_id, *, expected_draft_revision, worker_id):
        self.challenge_requests.append((template_id, expected_draft_revision, worker_id))
        return {
            "challenge_id": "challenge-1",
            "nonce": "nonce-1",
            "template_id": template_id,
            "expected_draft_revision": expected_draft_revision,
            "worker_id": worker_id,
        }

    def submit_v2_preview_proof(
        self,
        template_id,
        *,
        expected_draft_revision,
        sample_rows,
        evidence,
        worker_proof,
    ):
        self.proof = {
            "template_id": template_id, "expected_draft_revision": expected_draft_revision,
            "sample_rows": sample_rows, "evidence": evidence, "worker_proof": worker_proof,
        }
        return {
            "draft": {"manifest": {"draft_revision": "d0005"}},
            "validation": {"can_publish": True},
            "publication": {"status": "draft", "current_version": ""}, "versions": [],
        }


class TrialRenderer:
    def __init__(self):
        self.calls = []

    def render(self, render_task, **kwargs):
        self.calls.append({"render_task": render_task, **kwargs})
        Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_ai"]).write_bytes(b"rendered-ai")
        Path(kwargs["preview_png"]).write_bytes(b"rendered-png")
        Path(kwargs["layout_warning_file"]).write_text('{"warnings": []}', encoding="utf-8")
        return str(kwargs["output_ai"])


def test_trial_download_accepts_direct_api_asset_path_tuple(tmp_path):
    source = tmp_path / "central" / "template.ai"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"real-template-ai")
    digest = sha256_bytes(source.read_bytes())

    class DirectCentralApi:
        def draft_asset_path(self, template_id, file_name):
            assert (template_id, file_name) == ("V2TRIAL001", "template.ai")
            return source, {"file_name": file_name, "sha256": digest}

    target = tmp_path / "local" / "template.ai"
    download_asset(
        DirectCentralApi(),
        "V2TRIAL001",
        {"file_name": "template.ai", "sha256": digest},
        target,
    )

    assert target.read_bytes() == b"real-template-ai"


def test_trial_render_uses_sample_and_every_scanned_output(tmp_path):
    template_bytes = b"real-template-ai"
    central = TrialCentral(make_draft(sha256_bytes(template_bytes)), template_bytes)
    renderer = TrialRenderer()
    client = LocalDrawFlowClient(
        central,
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
        preview_worker_secret=WORKER_SECRET,
        preview_worker_id="test-worker",
    )

    result = client.trial_render("V2TRIAL001", {
        "expected_draft_revision": "d0004",
        "sample_row": {"Font": "F1", "Name": "Alice|Bob"},
    })

    assert result["trial"]["status"] == "passed"
    assert [item["key"] for item in result["trial"]["outputs"]] == ["Output_main"]
    assert result["trial"]["outputs"][0]["display_name"] == "主效果图"
    assert len(renderer.calls) == 1
    assert renderer.calls[0]["output_key"] == "Output_main"
    assert renderer.calls[0]["values"]["name"] == "Alice|Bob"
    assert renderer.calls[0]["selections"] == {"Output_main": {"font": "F1"}}
    assert central.proof["sample_rows"] == [{"Font": "F1", "Name": "Alice|Bob"}]
    assert central.proof["expected_draft_revision"] == "d0004"
    assert central.challenge_requests == [("V2TRIAL001", "d0004", "test-worker")]
    assert central.proof["worker_proof"]["challenge_id"] == "challenge-1"
    assert central.proof["worker_proof"]["worker_id"] == "test-worker"
    assert len(central.proof["worker_proof"]["signature"]) == 64
    evidence = central.proof["evidence"]
    assert evidence["render_task_sha256"] == renderer.calls[0]["render_task"]["task_sha256"]
    assert evidence["outputs"][0]["png_sha256"] == sha256_bytes(b"rendered-png")
    assert client.trial_preview_path(result["trial"]["id"], "Output_main").read_bytes() == b"rendered-png"


def test_trial_render_rejects_stale_draft_before_illustrator(tmp_path):
    class StaleCentral:
        def get_v2_draft(self, template_id):
            return {"manifest": {"draft_revision": "d0009"}}

    class MustNotRender:
        def render(self, *args, **kwargs):
            raise AssertionError("stale drafts must not enter Illustrator")

    client = LocalDrawFlowClient(
        StaleCentral(), tmp_path / "local", v2_renderer=MustNotRender(), font_dirs=[]
    )
    with pytest.raises(LocalClientError, match="已在其他操作中更新") as exc_info:
        client.trial_render("V2TRIAL001", {
            "expected_draft_revision": "d0004", "sample_row": {"Name": "Alice"},
        })
    assert exc_info.value.code == "v2_trial_draft_changed"
    assert not (tmp_path / "local" / "v2-trials").exists()


def test_trial_render_requires_trusted_worker_secret_before_illustrator(tmp_path):
    template_bytes = b"real-template-ai"
    central = TrialCentral(make_draft(sha256_bytes(template_bytes)), template_bytes)

    class MustNotRender:
        def render(self, *args, **kwargs):
            raise AssertionError("an unconfigured worker must not enter Illustrator")

    client = LocalDrawFlowClient(
        central,
        tmp_path / "local",
        v2_renderer=MustNotRender(),
        font_dirs=[],
        preview_worker_secret="",
    )
    with pytest.raises(LocalClientError, match="安全配置") as exc_info:
        client.trial_render(
            "V2TRIAL001",
            {"expected_draft_revision": "d0004", "sample_row": {"Name": "Alice"}},
        )

    assert exc_info.value.code == "v2_trial_worker_unavailable"


def test_trial_render_rejects_invalid_worker_id_before_illustrator(tmp_path):
    template_bytes = b"real-template-ai"
    central = TrialCentral(make_draft(sha256_bytes(template_bytes)), template_bytes)

    class MustNotRender:
        def render(self, *args, **kwargs):
            raise AssertionError("invalid worker configuration must not enter Illustrator")

    client = LocalDrawFlowClient(
        central,
        tmp_path / "local",
        v2_renderer=MustNotRender(),
        font_dirs=[],
        preview_worker_secret=WORKER_SECRET,
        preview_worker_id="invalid worker id",
    )
    with pytest.raises(LocalClientError, match="安全配置无效") as exc_info:
        client.trial_render(
            "V2TRIAL001",
            {"expected_draft_revision": "d0004", "sample_row": {"Name": "Alice"}},
        )
    assert exc_info.value.code == "v2_trial_worker_unavailable"
    assert exc_info.value.technical_message == "preview_worker_id_invalid"
    assert not central.challenge_requests


def test_trial_render_maps_worker_auth_error_to_stable_business_error(tmp_path):
    template_bytes = b"real-template-ai"

    class RejectingCentral(TrialCentral):
        def request_v2_preview_challenge(self, *args, **kwargs):
            raise V2PreviewWorkerAuthError("preview_worker_rejected", "internal detail")

    central = RejectingCentral(make_draft(sha256_bytes(template_bytes)), template_bytes)
    client = LocalDrawFlowClient(
        central,
        tmp_path / "local",
        v2_renderer=TrialRenderer(),
        font_dirs=[],
        preview_worker_secret=WORKER_SECRET,
        preview_worker_id="test-worker",
    )
    with pytest.raises(LocalClientError, match="安全配置无效") as exc_info:
        client.trial_render(
            "V2TRIAL001",
            {
                "expected_draft_revision": "d0004",
                "sample_row": {"Font": "F1", "Name": "Alice"},
            },
        )
    assert exc_info.value.code == "v2_trial_worker_unavailable"
    assert "preview_worker_rejected" in exc_info.value.technical_message
    assert not list((tmp_path / "local" / "v2-trials").rglob("trial.json"))


def test_trial_render_follows_two_scanned_outputs_with_independent_evidence(tmp_path):
    template_bytes = b"real-template-ai"
    central = TrialCentral(make_multi_output_draft(sha256_bytes(template_bytes)), template_bytes)

    class PerOutputRenderer(TrialRenderer):
        def render(self, render_task, **kwargs):
            self.calls.append({"render_task": render_task, **kwargs})
            output_key = kwargs["output_key"]
            Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
            Path(kwargs["output_ai"]).write_bytes(f"ai:{output_key}".encode())
            Path(kwargs["preview_png"]).write_bytes(f"png:{output_key}".encode())
            Path(kwargs["layout_warning_file"]).write_text(
                '{"warnings": []}', encoding="utf-8"
            )
            return str(kwargs["output_ai"])

    renderer = PerOutputRenderer()
    client = LocalDrawFlowClient(
        central,
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
        preview_worker_secret=WORKER_SECRET,
        preview_worker_id="test-worker",
    )
    result = client.trial_render("V2TRIAL001", {
        "expected_draft_revision": "d0004",
        "sample_row": {
            "Font A": "F1", "Name A": "Alice",
            "Font B": "F1", "Name B": "Manager",
        },
    })

    output_keys = [item["key"] for item in result["trial"]["outputs"]]
    assert output_keys == ["Output_SideA", "Output_SideB"]
    assert [item["display_name"] for item in result["trial"]["outputs"]] == [
        "正面效果图", "背面效果图",
    ]
    assert [call["output_key"] for call in renderer.calls] == output_keys
    expected_values = {
        "font_a": "F1", "name_a": "Alice",
        "font_b": "F1", "name_b": "Manager",
    }
    assert [call["values"] for call in renderer.calls] == [expected_values, expected_values]
    evidence = central.proof["evidence"]["outputs"]
    assert [item["key"] for item in evidence] == output_keys
    assert evidence[0]["ai_sha256"] == sha256_bytes(b"ai:Output_SideA")
    assert evidence[1]["ai_sha256"] == sha256_bytes(b"ai:Output_SideB")
    assert evidence[0]["png_sha256"] == sha256_bytes(b"png:Output_SideA")
    assert evidence[1]["png_sha256"] == sha256_bytes(b"png:Output_SideB")
    assert evidence[0]["png_sha256"] != evidence[1]["png_sha256"]
    assert result["trial"]["outputs"][0]["preview_url"].endswith(
        "/outputs/Output_SideA.png"
    )
    assert result["trial"]["outputs"][1]["preview_url"].endswith(
        "/outputs/Output_SideB.png"
    )
