from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.v2_acceptance_config import (
    build_acceptance_config,
    sample_for_design02,
    split_probe,
)
from scripts.verify_v2_workbench_acceptance import (
    resolve_paths,
    tree_summary,
)


def source_config():
    def slot(key, source, *, tail=False):
        return {
            "key": key,
            "source_field": source,
            "required": True,
            "preset": "direct_text",
            "anchor": f"anchor_{key[5:]}",
            "tails": ([{"key": f"tail_{key[5:]}_last_m", "position": "last", "sample": "m"}] if tail else []),
            "asset_key": "",
            "dimension_rule": {"mode": "anchor", "width_mm": 80, "height_mm": 20, "tolerance_mm": 0.007},
            "font_dependencies": ["Example Font"],
            "color_binding": "",
        }

    def option(key, *, tail=False):
        return {
            "key": key,
            "label": key,
            "content_preset": "direct_text",
            "component_key": "",
            "scope": "local",
            "font_dependencies": ["Example Font"],
            "slots": [slot("slot_name1", "name", tail=tail), slot("slot_name2", "title")],
            "assets": [],
        }

    return {
        "$schema": "custom-renderer/v2-template-contract",
        "schema_version": 1,
        "template": {"template_id": "Source", "name": "Source", "component_key": "main", "scope": "local"},
        "outputs": [{
            "key": "Output_main",
            "display_name": "主效果图",
            "component_key": "main",
            "scope": "local",
            "style": {"field": "", "options": []},
            "design": {"field": "design", "options": [option("Design02", tail=True), option("Design10")]},
            "font": {"field": "", "options": []},
        }],
        "colors": [],
        "field_bindings": {"name": "Name", "name1": "Name", "name2": "Title", "title": "Title", "design": "Design"},
        "option_mappings": [
            {"field": "design", "source_value": "2", "target": "Design02", "output": "Output_main", "group": "design"},
            {"field": "design", "source_value": "10", "target": "Design10", "output": "Output_main", "group": "design"},
        ],
        "checks": {},
        "preview": {"sample_rows": [], "evidence": {}},
        "audit": {"scan_version": "old", "template_sha256": "old", "config_version": 9},
    }


def scan_evidence():
    def scanned_slot(key, *, tail=False):
        suffix = key[5:]
        return {
            "key": key,
            "path": f"Template/Output_main/Design/current/{key}",
            "text_kind": "point_text",
            "preset": "direct_text",
            "anchor": f"anchor_{suffix}",
            "tails": ([{"key": f"tail_{suffix}_last_m", "position": "last", "sample": "m"}] if tail else []),
            "dimensions": {"width_mm": 79, "height_mm": 19},
            "font_dependencies": ["Example Font"],
        }

    def scanned_option(key, *, tail=False):
        slots = [scanned_slot("slot_name1", tail=tail), scanned_slot("slot_name2")]
        return {
            "key": key,
            "path": f"Template/Output_main/Design/{key}",
            "slots": slots,
            "anchors": [
                {"key": "anchor_name1", "dimensions": {"width_mm": 80, "height_mm": 20}},
                {"key": "anchor_name2", "dimensions": {"width_mm": 70, "height_mm": 10}},
            ],
            "tails": deepcopy(slots[0]["tails"]),
            "assets": [],
            "font_dependencies": ["Example Font"],
        }

    return {
        "evidence": {"template_sha256": "a" * 64, "object_path_digest": "b" * 64},
        "outputs": [{
            "key": "Output_main",
            "path": "Template/Output_main",
            "styles": [],
            "designs": [scanned_option("Design02", tail=True), scanned_option("Design10")],
            "fonts": [],
        }],
        "colors": [],
        "issues": [],
        "blocked": False,
    }


def test_build_config_uses_scanned_dual_slots_and_removes_orphan_title():
    original = source_config()
    config = build_acceptance_config(original, scan_evidence(), "V2ACCEPTANCE")

    assert original["template"]["template_id"] == "Source"
    assert config["template"]["template_id"] == "V2ACCEPTANCE"
    assert config["field_bindings"] == {"name": "Name", "name1": "Name", "name2": "Title", "design": "Design"}
    design02 = config["outputs"][0]["design"]["options"][0]
    assert design02["content_preset"] == "mixed_slots"
    assert [(slot["key"], slot["source_field"], slot["preset"]) for slot in design02["slots"]] == [
        ("slot_name1", "name1", "direct_text"),
        ("slot_name2", "name2", "direct_text"),
    ]
    assert design02["slots"][0]["tails"] == [
        {"key": "tail_name1_last_m", "position": "last", "sample": "m"}
    ]
    assert "pua_base" not in design02["slots"][0]["tails"][0]
    assert config["checks"]["preview"]["status"] == "pending"
    assert all(value["status"] == "confirmed" for key, value in config["checks"].items() if key != "preview")


def test_split_probe_uses_memory_clone_and_reports_missing_pipe():
    config = build_acceptance_config(source_config(), scan_evidence(), "V2ACCEPTANCE")
    unchanged = deepcopy(config)

    sample = sample_for_design02(config)
    result = split_probe(config, sample)

    assert sample == {"Design": "2", "Name": "Alice", "Title": "Manager"}
    assert result["option"] == "Design10"
    assert result["with_pipe"] == {"can_render": True}
    assert result["without_pipe"]["can_render"] is False
    assert [item["code"] for item in result["without_pipe"]["issues"]] == ["slot_content_missing"]
    assert "至少 2 个必填槽位" in result["without_pipe"]["issues"][0]["reason"]
    assert config == unchanged


def test_resolve_paths_rejects_output_inside_source_data_tree(tmp_path):
    source_root = tmp_path / "drawflow-data"
    ai = source_root / "v2-templates" / "Demo" / "template.ai"
    config = source_root / "v2-templates" / "Demo" / "config.json"
    ai.parent.mkdir(parents=True)
    ai.write_bytes(b"real-ai")
    config.write_text(json.dumps(source_config()), encoding="utf-8")
    before = tree_summary(source_root)

    with pytest.raises(ValueError, match="源数据树"):
        resolve_paths(ai, config, source_root / "acceptance")

    resolved = resolve_paths(ai, config, tmp_path / "output" / "acceptance")
    assert resolved[3] == source_root.resolve()
    assert tree_summary(source_root) == before


def test_resolve_paths_rejects_nonempty_evidence_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ai, config, output = source / "template.ai", source / "config.json", tmp_path / "output"
    ai.write_bytes(b"real-ai")
    config.write_text("{}", encoding="utf-8")
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="不存在或为空"):
        resolve_paths(ai, config, output)
