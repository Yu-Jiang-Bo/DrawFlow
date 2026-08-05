import json

import pytest

from src.service.v2_template_store import V2TemplateStore, V2TemplateStoreError


def test_save_draft_persists_v2_state_without_touching_legacy_files(tmp_path):
    legacy_config = tmp_path / "templates.json"
    legacy_config.write_bytes(b'{"version":1,"templates":[]}')
    onboarding = tmp_path / "templates/LEGACY001/onboarding/draft.json"
    onboarding.parent.mkdir(parents=True)
    onboarding.write_bytes(b'{"legacy":true}')
    store = V2TemplateStore(tmp_path / "v2-templates")

    state = store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo", "shop_name": ""},
        config={"checks": {"output": "pending"}},
        scan={"scan_version": "scan-1"},
        assets=[{"filename": "template.ai", "role": "template", "content": b"ai-bytes"}],
    )
    draft = store.read_draft("V2DEMO001")

    assert state["template"] == {"template_id": "V2DEMO001", "name": "Demo", "shop_name": ""}
    assert state["draft"]["revision"] == "d0001"
    assert state["publication"] == {"status": "draft", "current_version": "", "rollback_version": ""}
    assert draft["config"] == {"checks": {"output": "pending"}}
    assert draft["scan"] == {"scan_version": "scan-1"}
    assert draft["manifest"]["assets"][0]["path"] == "assets/template.ai"
    assert legacy_config.read_bytes() == b'{"version":1,"templates":[]}'
    assert onboarding.read_bytes() == b'{"legacy":true}'


def test_failed_draft_state_write_keeps_previous_complete_draft(tmp_path, monkeypatch):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 1})
    original_write = store._write_json_atomic

    def fail_state(path, payload):
        if path.name == "state.json":
            raise OSError("disk interruption")
        return original_write(path, payload)

    monkeypatch.setattr(store, "_write_json_atomic", fail_state)

    with pytest.raises(OSError, match="disk interruption"):
        store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 2})

    assert store.read_draft("V2DEMO001")["config"] == {"version": 1}
    assert not (tmp_path / "v2/V2DEMO001/drafts/d0002").exists()


def test_failed_payload_json_write_keeps_previous_complete_draft(tmp_path, monkeypatch):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 1})
    original_write = store._write_json_atomic

    def fail_config(path, payload):
        if path.name == "config.json":
            raise OSError("config write failed")
        return original_write(path, payload)

    monkeypatch.setattr(store, "_write_json_atomic", fail_config)

    with pytest.raises(OSError, match="config write failed"):
        store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 2})

    tmp_dir = tmp_path / "v2/V2DEMO001/_tmp"
    assert store.read_draft("V2DEMO001")["config"] == {"version": 1}
    assert not (tmp_path / "v2/V2DEMO001/drafts/d0002").exists()
    assert not tmp_dir.exists() or not any(tmp_dir.iterdir())


def test_publish_creates_immutable_version_and_edit_copies_to_new_draft(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo"},
        config={"version": 1},
        scan={"scan_version": "scan-1"},
        assets=[{"filename": "template.ai", "content": b"ai-v1"}],
    )
    first = store.publish_draft("V2DEMO001", note="first")
    store.create_draft_from_version("V2DEMO001")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 2})
    second = store.publish_draft("V2DEMO001", note="second")

    first_manifest = json.loads((tmp_path / "v2/V2DEMO001/versions/v0001/manifest.json").read_text(encoding="utf-8"))
    first_config = json.loads((tmp_path / "v2/V2DEMO001/versions/v0001/config.json").read_text(encoding="utf-8"))
    assert first["publication"]["current_version"] == "v0001"
    assert second["publication"] == {"status": "active", "current_version": "v0002", "rollback_version": "v0001"}
    assert first_manifest["immutable"] is True
    assert first_config == {"version": 1}
    assert store.rollback("V2DEMO001")["publication"]["current_version"] == "v0001"


def test_failed_publish_state_write_keeps_previous_active_version(tmp_path, monkeypatch):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 1})
    store.publish_draft("V2DEMO001")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 2})
    original_write = store._write_json_atomic

    def fail_state(path, payload):
        if path.name == "state.json":
            raise OSError("state write failed")
        return original_write(path, payload)

    monkeypatch.setattr(store, "_write_json_atomic", fail_state)

    with pytest.raises(OSError, match="state write failed"):
        store.publish_draft("V2DEMO001")

    assert store.get_state("V2DEMO001")["publication"]["current_version"] == "v0001"
    assert not (tmp_path / "v2/V2DEMO001/versions/v0002").exists()


def test_discard_and_deactivate_do_not_delete_formal_versions(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 1})
    store.publish_draft("V2DEMO001")
    store.save_draft("V2DEMO001", metadata={"name": "Demo"}, config={"version": 2})

    discarded = store.discard_draft("V2DEMO001")
    inactive = store.deactivate_current("V2DEMO001")

    assert discarded["draft"] is None
    assert inactive["publication"]["status"] == "inactive"
    assert (tmp_path / "v2/V2DEMO001/versions/v0001/manifest.json").exists()


def test_rejects_invalid_or_non_ai_assets(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")

    with pytest.raises(V2TemplateStoreError, match=".ai"):
        store.save_draft("V2DEMO001", metadata={"name": "Demo"}, assets=[{"filename": "template.png", "content": b"x"}])


def test_rejects_template_id_outside_contract_charset(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")

    with pytest.raises(V2TemplateStoreError, match="template_id"):
        store.save_draft("模板001", metadata={"name": "Demo"})
