import json
import hashlib
import zipfile

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


def test_render_mode_provenance_distinguishes_new_and_historical_drafts(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")

    store.save_draft("V2NEWMODE", metadata={"name": "New"}, config={})
    new_draft = store.read_draft("V2NEWMODE")
    assert new_draft["manifest"]["legacy_render_mode_allowed"] is False

    store.save_draft(
        "V2EXPLICIT",
        metadata={"name": "Explicit"},
        config={"render_mode": "single_customization"},
    )
    explicit_draft = store.read_draft("V2EXPLICIT")
    assert explicit_draft["manifest"]["legacy_render_mode_allowed"] is False

    store.save_draft("V2LEGACY", metadata={"name": "Legacy"}, config={})
    legacy_manifest_path = tmp_path / "v2/V2LEGACY/drafts/d0001/manifest.json"
    legacy_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
    legacy_manifest.pop("legacy_render_mode_allowed")
    legacy_manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")

    store.save_draft("V2LEGACY", metadata={"name": "Legacy"}, config={})
    migrated_legacy_draft = store.read_draft("V2LEGACY")
    assert migrated_legacy_draft["manifest"]["legacy_render_mode_allowed"] is True

    store.save_draft(
        "V2LEGACY",
        metadata={"name": "Legacy"},
        config={"render_mode": "multi_customization"},
    )
    migrated_explicit_draft = store.read_draft("V2LEGACY")
    assert migrated_explicit_draft["manifest"]["legacy_render_mode_allowed"] is False


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


def test_read_published_returns_current_immutable_scan_and_configuration(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2SHARED001",
        metadata={"name": "Shared demo"},
        config={"template": {"template_id": "V2SHARED001"}, "field_bindings": {"name": "Name"}},
        scan={"outputs": [{"key": "Output_main"}]},
        assets=[{"filename": "template.ai", "role": "template", "content": b"ai-v1"}],
    )
    store.publish_draft("V2SHARED001")
    store.save_draft(
        "V2SHARED001",
        metadata={"name": "Changed only in draft"},
        config={"template": {"template_id": "V2SHARED001"}, "field_bindings": {"name": "Changed"}},
        scan={"outputs": [{"key": "Output_changed"}]},
    )

    published = store.read_published("V2SHARED001")

    assert published["manifest"]["version"] == "v0001"
    assert published["config"]["field_bindings"] == {"name": "Name"}
    assert published["scan"]["outputs"] == [{"key": "Output_main"}]


def test_read_published_rejects_a_template_without_an_active_shared_version(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft("V2DRAFT001", metadata={"name": "Draft only"}, config={"template": {}}, scan={"outputs": []})

    with pytest.raises(V2TemplateStoreError, match="尚未发布"):
        store.read_published("V2DRAFT001")


def test_read_published_rejects_a_version_without_a_template_ai_asset(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2MISSINGAI",
        metadata={"name": "Missing source"},
        config={"template": {"template_id": "V2MISSINGAI"}},
        scan={"outputs": [{"key": "Output_main"}]},
    )
    store.publish_draft("V2MISSINGAI")

    with pytest.raises(V2TemplateStoreError, match="缺少可用的 .ai 源文件"):
        store.read_published("V2MISSINGAI")


def test_read_published_rejects_a_template_ai_asset_without_sha256(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2MISSINGSHA",
        metadata={"name": "Missing checksum"},
        config={"template": {"template_id": "V2MISSINGSHA"}},
        scan={"outputs": [{"key": "Output_main"}]},
        assets=[{"filename": "template.ai", "role": "template", "content": b"ai-v1"}],
    )
    store.publish_draft("V2MISSINGSHA")
    manifest_path = tmp_path / "v2/V2MISSINGSHA/versions/v0001/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["sha256"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(V2TemplateStoreError, match="缺少可用的 .ai 源文件"):
        store.read_published("V2MISSINGSHA")


def test_version_bundle_contains_manifest_payload_and_assets(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo"},
        config={"version": 1},
        scan={"scan_version": "scan-1"},
        assets=[{"filename": "template.ai", "content": b"ai-v1"}],
    )
    store.publish_draft("V2DEMO001")

    bundle_path = store.version_bundle_path("V2DEMO001", "v0001")

    with zipfile.ZipFile(bundle_path) as archive:
        assert archive.testzip() is None
        assert {"manifest.json", "metadata.json", "config.json", "scan.json", "assets/template.ai"} <= set(
            archive.namelist()
        )
        assert archive.read("assets/template.ai") == b"ai-v1"


def test_save_draft_accepts_streamed_source_path_asset_metadata(tmp_path):
    source = tmp_path / "upload-cache" / "template.ai"
    source.parent.mkdir()
    source.write_bytes(b"streamed-ai")
    store = V2TemplateStore(tmp_path / "v2")

    store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo"},
        assets=[
            {
                "filename": "template.ai",
                "role": "template",
                "source_path": source,
                "sha256": hashlib.sha256(b"streamed-ai").hexdigest(),
                "mime_type": "application/illustrator",
                "scan_version": "scan-2",
                "draft_revision": "d0001",
            }
        ],
    )
    draft = store.read_draft("V2DEMO001")

    asset = draft["manifest"]["assets"][0]
    assert asset["path"] == "assets/template.ai"
    assert asset["size_bytes"] == len(b"streamed-ai")
    assert asset["sha256"] == hashlib.sha256(b"streamed-ai").hexdigest()
    assert asset["mime_type"] == "application/illustrator"
    assert asset["scan_version"] == "scan-2"
    assert (tmp_path / "v2/V2DEMO001/drafts/d0001/assets/template.ai").read_bytes() == b"streamed-ai"


def test_create_draft_from_version_streams_assets_without_reading_ai_bytes(tmp_path, monkeypatch):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo"},
        assets=[{"filename": "template.ai", "content": b"ai-v1"}],
    )
    store.publish_draft("V2DEMO001")
    original_read_bytes = type(tmp_path).read_bytes

    def fail_ai_read_bytes(self):
        if self.suffix == ".ai":
            raise AssertionError("AI assets must be copied as streams, not read_bytes()")
        return original_read_bytes(self)

    monkeypatch.setattr(type(tmp_path), "read_bytes", fail_ai_read_bytes)

    state = store.create_draft_from_version("V2DEMO001")

    assert state["draft"]["source_version"] == "v0001"
    assert store.read_draft("V2DEMO001")["manifest"]["assets"][0]["sha256"]


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
