import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.service.template_onboarding import TemplateOnboardingStore
from src.service.template_publication import TemplatePublicationService
from src.service.template_registry import TemplateRegistry
from src.service.template_scan import build_rule_draft_from_scan


def setup_publication(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai_path = registry.save_uploaded_ai("DEMO001", "template.ai", b"ai")
    registry.upsert_template(
        {
            "template_id": "DEMO001",
            "name": "Demo",
            "template_type": "pure_text_color_design",
            "status": "draft",
            "template_ai": registry.to_config_path(ai_path),
        }
    )
    store = TemplateOnboardingStore(registry.storage_dir)
    pack = build_rule_draft_from_scan(
        {
            "scan_version": "scan-1",
            "document": {"source_ai": str(ai_path)},
            "items": [
                {"type": "GroupItem", "name": "F1", "path": "Template/F1"},
                {"type": "TextFrame", "name": "Name1", "path": "Template/Name1"},
            ],
        },
        template_id="DEMO001",
    )
    pack["validation"]["unresolved_items"] = []
    pack["validation"]["sample"] = {"input": {"Custom": "Alice"}, "expected": {"Name1": "Alice"}}
    pack["rules"]["order_bindings"] = {"text": "Custom"}
    pack["rules"]["text_policies"] = {"fit": "scale_to_box"}
    store.save_scan_draft("DEMO001", pack)
    return registry, store, pack


def test_publication_rolls_back_every_file_when_registry_publish_fails(tmp_path, monkeypatch):
    registry, store, pack = setup_publication(tmp_path)
    draft_before = store.get_state("DEMO001")["draft"]
    monkeypatch.setattr(
        registry,
        "apply_confirmed_rule_pack",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk failure")),
    )

    with pytest.raises(OSError, match="disk failure"):
        TemplatePublicationService(registry, store).confirm("DEMO001", pack, change_summary="fail")

    state = store.get_state("DEMO001")
    assert state["draft"] == draft_before
    assert state["confirmed"] is None
    assert state["versions"] == []
    assert registry.get_template("DEMO001").status == "draft"


def test_concurrent_publications_keep_runtime_and_confirmed_pack_consistent(tmp_path):
    registry, store, pack = setup_publication(tmp_path)
    publisher = TemplatePublicationService(registry, store)

    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(
            executor.map(
                lambda summary: publisher.confirm("DEMO001", pack, change_summary=summary)["version"],
                ["first", "second"],
            )
        )

    state = store.get_state("DEMO001")
    runtime = json.loads(registry.get_template("DEMO001").template_rules_config.read_text(encoding="utf-8"))
    assert sorted(versions) == [1, 2]
    assert runtime == state["confirmed"]["pack"]


def test_executable_rule_pack_switches_legacy_template_to_generic_pipeline(tmp_path):
    registry, store, pack = setup_publication(tmp_path)

    published = TemplatePublicationService(registry, store).confirm(
        "DEMO001", pack, change_summary="publish generic"
    )

    assert published["template"].pipeline == "generic_rules_only"


def test_publication_rechecks_asset_file_inside_transaction(tmp_path):
    registry, store, pack = setup_publication(tmp_path)
    missing_path = tmp_path / "missing.ai"
    template = registry.get_template("DEMO001")
    registry.upsert_template(
        {
            **template.to_json_dict(),
            "status": "draft",
            "assets": [{"file_name": "missing.ai", "stored_path": str(missing_path)}],
        }
    )
    pack["assets"] = {
        "items": [{"file_name": "missing.ai", "stored_path": str(missing_path)}],
        "policy": {"mode": "split_ai"},
    }
    pack["rules"]["design_options"] = ["Design1"]
    pack["rules"]["asset_mappings"] = [{"option": "Design1", "asset": "missing.ai"}]

    with pytest.raises(ValueError, match="file is missing"):
        TemplatePublicationService(registry, store).confirm("DEMO001", pack, change_summary="missing")

    assert store.get_state("DEMO001")["versions"] == []
