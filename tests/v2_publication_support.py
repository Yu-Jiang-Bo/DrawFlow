"""Shared fixtures for proof-bound V2 publication tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from src.service.v2_preview_proof import (
    compile_preview_render_task,
    preview_config_payload,
    preview_config_sha256,
    preview_outputs_sha256,
    sample_rows_sha256,
)
from src.service.v2_preview_worker_auth import sign_preview_worker_challenge
from src.service.v2_render_task import V2_RENDERER_VERSION
from src.service.v2_template_api import V2TemplateApi
from src.service.v2_template_contract import V2_VERIFICATION_KEYS
from src.service.v2_template_store import V2TemplateStore
from tests.test_v2_template_api import TrackingStream, saveable_config, scan_evidence


TEST_WORKER_SECRET = "test-preview-worker-secret-32-bytes-minimum"
TEST_WORKER_ID = "windows-renderer-test"


def publication_api(
    tmp_path: Path,
    *,
    secret: str | bytes | None = TEST_WORKER_SECRET,
    clock: Any | None = None,
    ttl_seconds: int = 120,
) -> V2TemplateApi:
    return V2TemplateApi(
        V2TemplateStore(tmp_path / "v2"),
        preview_worker_secret=secret,
        preview_worker_clock=clock,
        preview_challenge_ttl_seconds=ttl_seconds,
    )


def renderable_scan_evidence(template_sha256: str) -> dict[str, Any]:
    evidence = scan_evidence(template_sha256)
    evidence["outputs"] = [
        {
            "key": "Output_main",
            "path": "Template/Output_main",
            "styles": [{"key": "style1", "path": "Template/Output_main/style1"}],
            "fonts": [
                {
                    "key": "F1",
                    "path": "Template/Output_main/F1",
                    "slots": [
                        {
                            "key": "slot_name",
                            "path": "Template/Output_main/F1/slot_name",
                            "text_kind": "point_text",
                        }
                    ],
                    "anchors": [],
                    "tails": [],
                }
            ],
        }
    ]
    return evidence


def publishable_config(template_id: str = "V2API001") -> dict[str, Any]:
    config = saveable_config(template_id)
    config["render_mode"] = "single_customization"
    config["outputs"][0]["style"] = {
        "field": "style",
        "options": [
            {
                "key": "style1",
                "dimensions": {
                    "mode": "fixed",
                    "width_mm": 80,
                    "height_mm": 50,
                    "tolerance_mm": 0.007,
                },
            }
        ],
    }
    font_option = config["outputs"][0]["font"]["options"][0]
    font_option["font_dependencies"] = ["Arial"]
    font_option["slots"][0]["font_dependencies"] = ["Arial"]
    config["field_bindings"]["style"] = "Size"
    config["option_mappings"].append(
        {
            "field": "style",
            "source_value": "small",
            "target": "style1",
            "output": "Output_main",
            "group": "style",
        }
    )
    config["checks"] = {key: "confirmed" for key in V2_VERIFICATION_KEYS}
    config["preview"] = {"sample_rows": [], "evidence": {}}
    config["audit"] = {"scan_version": "", "template_sha256": "", "config_version": 7}
    return config


def prepared_draft(api: V2TemplateApi) -> dict[str, Any]:
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    ai_bytes = b"real-template-ai-source"
    uploaded = api.upload_asset(
        "V2API001",
        "template.ai",
        TrackingStream(ai_bytes),
        content_length=len(ai_bytes),
        headers={},
    )
    api.submit_scan(
        "V2API001",
        {"evidence": renderable_scan_evidence(uploaded["asset"]["sha256"])},
    )
    return api.save_draft("V2API001", {"config": publishable_config()})["draft"]


def preview_evidence_for(
    draft: Mapping[str, Any],
    sample_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    core = preview_config_payload(draft["config"], sample_rows)
    font_check = {"ok": True, "missing": []}
    task = compile_preview_render_task(draft, core, font_check)
    outputs = []
    for output in task["outputs"]:
        key = str(output["key"])
        ai_bytes = b"%!PS-Adobe-3.0\n%%Creator: DrawFlow Preview\n" + key.encode("utf-8")
        png_bytes = b"\x89PNG\r\n\x1a\nDrawFlow Preview Pixels:" + key.encode("utf-8")
        outputs.append(
            {
                "key": key,
                "ai_sha256": hashlib.sha256(ai_bytes).hexdigest(),
                "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
            }
        )
    return {
        "template_sha256": draft["manifest"]["assets"][0]["sha256"],
        "scan_sha256": draft["manifest"]["scan_sha256"],
        "config_sha256": preview_config_sha256(core),
        "sample_sha256": sample_rows_sha256(sample_rows),
        "render_task_sha256": task["task_sha256"],
        "preview_sha256": preview_outputs_sha256(outputs),
        "renderer_version": V2_RENDERER_VERSION,
        "font_check": font_check,
        "warnings": [],
        "rendered_at": "2026-08-12T00:00:00Z",
        "outputs": outputs,
    }


def signed_preview_payload(
    api: V2TemplateApi,
    draft: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    secret: str | bytes = TEST_WORKER_SECRET,
    worker_id: str = TEST_WORKER_ID,
) -> dict[str, Any]:
    revision = str(draft["manifest"]["draft_revision"])
    challenge = api.preview_challenge(
        "V2API001",
        {"expected_draft_revision": revision, "worker_id": worker_id},
    )["challenge"]
    evidence = preview_evidence_for(draft, rows)
    worker_proof = sign_preview_worker_challenge(
        secret,
        challenge,
        template_id="V2API001",
        draft_revision=revision,
        sample_rows=rows,
        evidence=evidence,
        worker_id=worker_id,
    )
    return {
        "expected_draft_revision": revision,
        "sample_rows": [dict(row) for row in rows],
        "evidence": evidence,
        "worker_proof": worker_proof,
    }


__all__ = [
    "TEST_WORKER_ID",
    "TEST_WORKER_SECRET",
    "prepared_draft",
    "preview_evidence_for",
    "publication_api",
    "publishable_config",
    "renderable_scan_evidence",
    "signed_preview_payload",
]
