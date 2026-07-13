import json
from concurrent.futures import ThreadPoolExecutor

from src.service.template_inspector import TemplateInspector
from src.service.template_onboarding import TemplateOnboardingStore
from src.service.template_registry import TemplateRegistry


class FakeBridge:
    def __init__(self, *, visible=False, fail=False):
        self.visible = visible
        self.fail = fail

    def render(self, script, task_path):
        if self.fail:
            raise RuntimeError("Illustrator unavailable")
        task = json.loads(task_path.read_text(encoding="utf-8"))
        scan = {
            "layers": [{"name": "Template"}],
            "items": [
                {"type": "GroupItem", "name": "Design1", "path": "Template/Design1"},
                {"type": "TextFrame", "name": "Name1", "path": "Template/Name1"},
            ],
        }
        with open(task["output_json"], "w", encoding="utf-8") as handle:
            json.dump(scan, handle)


def registered_template(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai_path = registry.save_uploaded_ai("DEMO001", "template.ai", b"fake ai")
    template = registry.upsert_template(
        {
            "template_id": "DEMO001",
            "name": "Demo",
            "template_type": "pure_text_color_design",
            "status": "draft",
            "template_ai": registry.to_config_path(ai_path),
        }
    )
    return registry, template


def test_inspector_persists_real_scan_draft_for_onboarding(tmp_path):
    registry, template = registered_template(tmp_path)
    store = TemplateOnboardingStore(registry.storage_dir)

    state = TemplateInspector(lambda **kwargs: FakeBridge(**kwargs)).scan(template, store)

    assert state["scan_ok"] is True
    assert state["draft"]["template"]["template_id"] == "DEMO001"
    assert state["draft"]["structure"]["scan_version"]
    assert state["draft"]["structure"]["evidence"]["item_count"] == 2
    assert state["scan_evidence"]["items"][0]["name"] == "Design1"
    scan_record = next((registry.storage_dir / "DEMO001" / "onboarding" / "scans").glob("*.json"))
    assert json.loads(scan_record.read_text(encoding="utf-8"))["raw_scan"]["items"][1]["name"] == "Name1"


def test_inspector_persists_failed_scan_as_blocked_draft(tmp_path):
    registry, template = registered_template(tmp_path)
    store = TemplateOnboardingStore(registry.storage_dir)

    state = TemplateInspector(lambda **kwargs: FakeBridge(**kwargs, fail=True)).scan(template, store)

    assert state["scan_ok"] is False
    assert "Illustrator unavailable" in state["scan_error"]
    assert {item["code"] for item in state["draft"]["validation"]["unresolved_items"]} >= {
        "scan_failed",
        "profile",
    }


def test_inspector_injects_registered_assets_into_rule_pack(tmp_path):
    registry, template = registered_template(tmp_path)
    assets = registry.save_uploaded_assets(
        "DEMO001", [{"filename": "design-1.ai", "content": b"asset"}]
    )
    template = registry.upsert_template({**template.to_json_dict(), "assets": assets})

    state = TemplateInspector(lambda **kwargs: FakeBridge(**kwargs)).scan(
        template, TemplateOnboardingStore(registry.storage_dir)
    )

    assert state["draft"]["assets"]["items"][0]["file_name"] == "design-1.ai"
    assert state["draft"]["assets"]["policy"]["mode"] == "split_ai"


def test_inspector_scans_primary_and_registered_asset_sources(tmp_path):
    registry, template = registered_template(tmp_path)
    assets = registry.save_uploaded_assets(
        "DEMO001", [{"filename": "design-1.ai", "content": b"asset"}], role="独立设计模板"
    )
    template = registry.upsert_template({**template.to_json_dict(), "assets": assets})

    state = TemplateInspector(lambda **kwargs: FakeBridge(**kwargs)).scan(
        template, TemplateOnboardingStore(registry.storage_dir)
    )

    sources = state["scan_evidence"]["source_files"]
    assert [source["source_role"] for source in sources] == ["尺寸/作图区模板", "独立设计模板"]
    assert len(state["scan_evidence"]["items"]) == 4
    assert {item["source_role"] for item in state["scan_evidence"]["items"]} == {
        "尺寸/作图区模板",
        "独立设计模板",
    }


def test_inspector_keeps_primary_results_when_asset_scan_fails(tmp_path):
    registry, template = registered_template(tmp_path)
    assets = registry.save_uploaded_assets(
        "DEMO001", [{"filename": "design-1.ai", "content": b"asset"}], role="独立设计模板"
    )
    template = registry.upsert_template({**template.to_json_dict(), "assets": assets})

    class PartialBridge(FakeBridge):
        def render(self, script, task_path):
            task = json.loads(task_path.read_text(encoding="utf-8"))
            if str(task["input_ai"]).endswith("design-1.ai"):
                raise RuntimeError("asset scan failed")
            super().render(script, task_path)

    state = TemplateInspector(lambda **kwargs: PartialBridge(**kwargs)).scan(
        template, TemplateOnboardingStore(registry.storage_dir)
    )

    assert state["scan_ok"] is False
    assert "asset scan failed" in state["scan_error"]
    assert state["scan_evidence"]["items"][0]["source_role"] == "尺寸/作图区模板"
    assert state["scan_evidence"]["source_files"][0]["scan_ok"] is True
    assert state["scan_evidence"]["source_files"][1]["scan_ok"] is False


def test_concurrent_scans_use_distinct_task_directories(tmp_path):
    registry, template = registered_template(tmp_path)
    task_paths = []

    class RecordingBridge(FakeBridge):
        def render(self, script, task_path):
            task_paths.append(task_path)
            super().render(script, task_path)

    inspector = TemplateInspector(lambda **kwargs: RecordingBridge(**kwargs))
    store = TemplateOnboardingStore(registry.storage_dir)
    with ThreadPoolExecutor(max_workers=2) as executor:
        states = list(executor.map(lambda _: inspector.scan(template, store), range(2)))

    assert all(state["scan_ok"] for state in states)
    assert len({path.parent for path in task_paths}) == 2
