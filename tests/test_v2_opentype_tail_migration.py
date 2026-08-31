import importlib.util
from pathlib import Path

import pytest

from src.service.v2_opentype_tail_migration import (
    OpenTypeTailMigrationError,
    merge_proven_tail_profiles,
)


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_v2_opentype_tail_profiles.py"
_SCRIPT_SPEC = importlib.util.spec_from_file_location("migrate_v2_opentype_tail_profiles", _SCRIPT_PATH)
assert _SCRIPT_SPEC is not None and _SCRIPT_SPEC.loader is not None
migration_cli = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(migration_cli)


def _config(sample="c"):
    return {
        "outputs": [{
            "design": {"options": [{"slots": [{"tails": [{
                "key": f"tail_name_first_{sample}", "position": "first", "sample": sample,
            }]}]}]},
            "font": {"options": []},
        }],
    }


def test_migration_merges_only_auto_proven_profiles_without_mutating_the_input():
    config = _config()
    evidence = _config()
    evidence["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0].update({
        "tail_profile_status": "auto",
        "opentype_feature": "aalt",
        "opentype_alternate_index": 2,
        "tail_profile_coverage": {
            "version": 1,
            "alphabet": "abcdefghijklmnopqrstuvwxyz",
            "verified": True,
        },
    })

    merged, changes = merge_proven_tail_profiles(config, evidence)

    tail = merged["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    assert tail["opentype_feature"] == "aalt"
    assert tail["opentype_alternate_index"] == 2
    assert "opentype_feature" not in config["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    assert changes == [{
        "locator": [0, "design", 0, 0, 0],
        "key": "tail_name_first_c",
        "position": "first",
        "sample": "c",
        "opentype_feature": "aalt",
        "opentype_alternate_index": 2,
    }]


def test_migration_rejects_profile_when_current_draft_tail_identity_changed():
    config = _config("c")
    evidence = _config("m")
    evidence["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0].update({
        "tail_profile_status": "auto",
        "pua_base": 0xE040,
    })

    with pytest.raises(OpenTypeTailMigrationError, match="尾巴身份不一致"):
        merge_proven_tail_profiles(config, evidence)


def _draft(asset_sha="a" * 64):
    return {
        "manifest": {
            "draft_revision": "d0007",
            "assets": [{"role": "template", "sha256": asset_sha}],
            "template": {"name": "Tail template", "shop_name": "Shop"},
        },
        "config": _config(),
    }


def _evidence():
    evidence = _config()
    evidence["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0].update({
        "tail_profile_status": "auto",
        "opentype_feature": "aalt",
        "opentype_alternate_index": 2,
        "tail_profile_coverage": {
            "version": 1,
            "alphabet": "abcdefghijklmnopqrstuvwxyz",
            "verified": True,
        },
    })
    evidence["evidence"] = {"template_sha256": "a" * 64}
    return evidence


def _run_cli(monkeypatch, tmp_path, request_json, *extra):
    raw = tmp_path / "scan.json"
    raw.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migration_cli, "normalize_v2_template_scan", lambda _raw: _evidence())
    return migration_cli.main([
        "--central-url", "http://central.example", "--template-id", "TAIL001", "--raw-evidence", str(raw), *extra,
    ], request_json=request_json)


def test_cli_reads_published_version_without_creating_a_draft_by_default(monkeypatch, tmp_path):
    calls = []

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/draft"):
            raise migration_cli.CentralRequestError(404, "草稿不存在。")
        if method == "GET" and url.endswith("/published"):
            return {"published": _draft()}
        raise AssertionError(f"unexpected request: {method} {url}")

    assert _run_cli(monkeypatch, tmp_path, request_json) == 0
    assert [(method, url.rsplit("/", 1)[-1]) for method, url, _ in calls] == [
        ("GET", "draft"), ("GET", "published"),
    ]


def test_cli_apply_creates_draft_from_published_then_scans_and_saves_without_publishing(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("DRAWFLOW_SCAN_WORKER_SECRET", "test-scan-worker-secret-32-bytes-minimum---")

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/draft"):
            raise migration_cli.CentralRequestError(404, "草稿不存在。")
        if method == "POST" and url.endswith("/draft-from-published"):
            return {"draft": _draft()}
        if method == "POST" and url.endswith("/validate"):
            return {"validation": {"can_save": True}}
        if method == "POST" and url.endswith("/scan-challenge"):
            return {"challenge": {"challenge_id": "c1", "nonce": "n1", "worker_id": "drawflow-tail-migration"}}
        if method == "POST" and url.endswith("/scan"):
            return {"draft": _draft()}
        if method == "POST" and url.endswith("/draft"):
            return {"draft": _draft()}
        raise AssertionError(f"unexpected request: {method} {url}")

    assert _run_cli(monkeypatch, tmp_path, request_json, "--apply") == 0
    endpoints = [(method, url.rsplit("/", 1)[-1]) for method, url, _ in calls]
    assert endpoints == [
        ("GET", "draft"), ("POST", "draft-from-published"), ("POST", "scan-challenge"), ("POST", "scan"), ("POST", "validate"), ("POST", "draft"),
    ]
    scan_payload = next(payload for method, url, payload in calls if method == "POST" and url.endswith("/scan"))
    assert scan_payload["expected_draft_revision"] == "d0007"
    assert scan_payload["worker_proof"]["challenge_id"] == "c1"
    assert len(scan_payload["worker_proof"]["signature"]) == 64
    assert all(endpoint != "publish" for _, endpoint in endpoints)


def test_cli_rejects_mismatched_ai_before_validation_or_draft_mutation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("DRAWFLOW_SCAN_WORKER_SECRET", "test-scan-worker-secret-32-bytes-minimum---")

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        assert method == "GET" and url.endswith("/draft")
        return {"draft": _draft("b" * 64)}

    with pytest.raises(OpenTypeTailMigrationError, match="模板 AI 校验不一致"):
        _run_cli(monkeypatch, tmp_path, request_json, "--apply")
    assert len(calls) == 1


def test_cli_apply_requires_separate_scan_worker_secret_before_mutation(monkeypatch, tmp_path):
    monkeypatch.delenv("DRAWFLOW_SCAN_WORKER_SECRET", raising=False)
    calls = []

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/draft"):
            return {"draft": _draft()}
        raise AssertionError(f"unexpected request: {method} {url}")

    with pytest.raises(OpenTypeTailMigrationError, match="DRAWFLOW_SCAN_WORKER_SECRET"):
        _run_cli(monkeypatch, tmp_path, request_json, "--apply")
    assert calls == []


def test_cli_apply_missing_scan_secret_never_creates_draft_from_published(monkeypatch, tmp_path):
    monkeypatch.delenv("DRAWFLOW_SCAN_WORKER_SECRET", raising=False)
    calls = []

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        raise AssertionError("missing scan secret must fail before every central request")

    with pytest.raises(OpenTypeTailMigrationError, match="DRAWFLOW_SCAN_WORKER_SECRET"):
        _run_cli(monkeypatch, tmp_path, request_json, "--apply")
    assert calls == []


def test_cli_stops_before_scan_and_save_when_central_validation_rejects(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("DRAWFLOW_SCAN_WORKER_SECRET", "test-scan-worker-secret-32-bytes-minimum---")

    def request_json(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/draft"):
            return {"draft": _draft()}
        if method == "POST" and url.endswith("/scan-challenge"):
            return {"challenge": {"challenge_id": "c1", "nonce": "n1", "worker_id": "drawflow-tail-migration"}}
        if method == "POST" and url.endswith("/scan"):
            return {"draft": _draft()}
        if method == "POST" and url.endswith("/validate"):
            return {"validation": {"can_save": False, "issues": [{"code": "tail_invalid"}]}}
        raise AssertionError(f"unexpected request: {method} {url}")

    with pytest.raises(OpenTypeTailMigrationError, match="拒绝合并"):
        _run_cli(monkeypatch, tmp_path, request_json, "--apply")
    assert [(method, url.rsplit("/", 1)[-1]) for method, url, _ in calls] == [
        ("GET", "draft"), ("POST", "scan-challenge"), ("POST", "scan"), ("POST", "validate"),
    ]
