import json
from pathlib import Path

import pytest

from src.renderer.v2_template_renderer import (
    V2_RENDER_EXECUTION_SCHEMA,
    V2TemplateRenderer,
    V2TemplateRendererError,
    build_v2_execution_task,
)
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA


def compiled_task():
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "f" * 64,
        "option_mappings": [
            {"output": "Output_main", "group": "font", "field": "font", "source_value": "F10", "target": "F10"},
            {"output": "Output_main", "group": "design", "field": "design", "source_value": "03", "target": "Design03"},
        ],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "copy_option_group",
                        "group": "font",
                        "option_key": "F10",
                        "object_path": "Template/Output_main/Font/F10",
                    },
                    {
                        "type": "replace_slot_text",
                        "group": "font",
                        "option_key": "F10",
                        "slot_key": "slot_name",
                        "object_path": "Template/Output_main/Font/F10/slot_name",
                        "source_field": "name",
                        "required": True,
                        "preset": "direct_text",
                        "tail_paths": [],
                    },
                    {
                        "type": "copy_option_group",
                        "group": "design",
                        "option_key": "Design03",
                        "object_path": "Template/Output_main/Design/Design03",
                    },
                    {
                        "type": "replace_slot_text",
                        "group": "design",
                        "option_key": "Design03",
                        "slot_key": "slot_year",
                        "object_path": "Template/Output_main/Design/Design03/slot_year",
                        "source_field": "year",
                        "required": False,
                        "preset": "direct_text",
                        "tail_paths": [],
                    },
                ],
            }
        ],
    }


def initial_render_task():
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "e" * 64,
        "option_mappings": [
            {"output": "Output_main", "group": "design", "field": "design", "source_value": "03", "target": "Design03"},
        ],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "copy_option_group",
                        "group": "design",
                        "option_key": "Design03",
                        "object_path": "Template/Output_main/Design/Design03",
                        "content_preset": "initial_with_text",
                    },
                    {
                        "type": "replace_slot_text",
                        "group": "design",
                        "option_key": "Design03",
                        "slot_key": "slot_name",
                        "object_path": "Template/Output_main/Design/Design03/slot_name",
                        "source_field": "personalization",
                        "required": True,
                        "preset": "direct_text",
                        "tail_paths": [],
                        "value_key": "Output_main|design|Design03|slot|slot_name",
                    },
                    {
                        "type": "bind_asset_library",
                        "group": "design",
                        "option_key": "Design03",
                        "asset_key": "initial",
                        "slot_key": "slot_initial",
                        "object_path": "Template/Output_main/Design/Design03/Assets/initial",
                        "target_path": "Template/Output_main/Design/Design03/slot_initial",
                        "source_field": "personalization",
                        "required": True,
                        "supported_values": ["A", "B", "K"],
                        "value_key": "Output_main|design|Design03|asset|initial",
                    },
                ],
            }
        ],
    }


def multi_initial_render_task():
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "d" * 64,
        "option_mappings": [
            {"output": "Output_main", "group": "design", "field": "design", "source_value": "03", "target": "Design03"},
        ],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "copy_option_group",
                        "group": "design",
                        "option_key": "Design03",
                        "object_path": "Template/Output_main/Design/Design03",
                        "content_preset": "multi_initials",
                    },
                    {
                        "type": "bind_asset_library",
                        "group": "design",
                        "option_key": "Design03",
                        "asset_key": "initial_top",
                        "slot_key": "slot_initial_top",
                        "object_path": "Template/Output_main/Design/Design03/Assets/initial_top",
                        "target_path": "Template/Output_main/Design/Design03/slot_initial_top",
                        "source_field": "names",
                        "required": True,
                        "supported_values": ["A", "B", "C"],
                        "value_key": "Output_main|design|Design03|asset|initial_top",
                    },
                    {
                        "type": "bind_asset_library",
                        "group": "design",
                        "option_key": "Design03",
                        "asset_key": "initial_middle",
                        "slot_key": "slot_initial_middle",
                        "object_path": "Template/Output_main/Design/Design03/Assets/initial_middle",
                        "target_path": "Template/Output_main/Design/Design03/slot_initial_middle",
                        "source_field": "names",
                        "required": True,
                        "supported_values": ["A", "B", "C"],
                        "value_key": "Output_main|design|Design03|asset|initial_middle",
                    },
                    {
                        "type": "bind_asset_library",
                        "group": "design",
                        "option_key": "Design03",
                        "asset_key": "initial_bottom",
                        "slot_key": "slot_initial_bottom",
                        "object_path": "Template/Output_main/Design/Design03/Assets/initial_bottom",
                        "target_path": "Template/Output_main/Design/Design03/slot_initial_bottom",
                        "source_field": "names",
                        "required": True,
                        "supported_values": ["A", "B", "C"],
                        "value_key": "Output_main|design|Design03|asset|initial_bottom",
                    },
                ],
            }
        ],
    }


class FakeBridge:
    def __init__(self):
        self.calls = []

    def render(self, script_path, task_path):
        self.calls.append({"script_path": Path(script_path), "task_path": Path(task_path)})
        return "done.ai"


def test_builds_execution_task_with_derived_option_selections(tmp_path):
    execution = build_v2_execution_task(
        compiled_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "F10", "design": "03", "name": "Alice"},
    )

    assert execution["$schema"] == V2_RENDER_EXECUTION_SCHEMA
    assert execution["render_task_sha256"] == "f" * 64
    assert execution["selections"] == {"Output_main": {"font": "F10", "design": "Design03"}}
    assert execution["values"]["name"] == "Alice"
    assert execution["resolved_values"] == {}


@pytest.mark.parametrize(
    ("personalization", "initial", "body"),
    [
        ("K|Kenneth", "K", "Kenneth"),
        ("Back|K", "K", "Back"),
        ("Kenneth", "K", "Kenneth"),
    ],
)
def test_builds_execution_task_with_resolved_initial_and_body_text(tmp_path, personalization, initial, body):
    execution = build_v2_execution_task(
        initial_render_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"design": "03", "personalization": personalization},
    )

    assert execution["resolved_values"] == {
        "Output_main|design|Design03|asset|initial": initial,
        "Output_main|design|Design03|slot|slot_name": body,
    }


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("Amy|Bob|Chris", ["A", "B", "C"]),
        ("A|B|C", ["A", "B", "C"]),
        ("ABC", ["A", "B", "C"]),
        ("Amy|B|Chris", ["A", "B", "C"]),
    ],
)
def test_builds_execution_task_with_resolved_multi_initials(tmp_path, names, expected):
    execution = build_v2_execution_task(
        multi_initial_render_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"design": "03", "names": names},
    )

    assert list(execution["resolved_values"].values()) == expected


@pytest.mark.parametrize(("personalization", "code"), [("A|B", "initial_content_ambiguous"), ("Zelda", "asset_value_missing")])
def test_ambiguous_or_unsupported_initial_content_does_not_enter_illustrator(tmp_path, personalization, code):
    with pytest.raises(V2TemplateRendererError) as exc_info:
        build_v2_execution_task(
            initial_render_task(),
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"design": "03", "personalization": personalization},
        )

    assert exc_info.value.code == code


def test_explicit_option_selections_are_accepted_without_mapping_values(tmp_path):
    execution = build_v2_execution_task(
        compiled_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "unknown", "design": "unknown", "name": "Alice"},
        selections={"Output_main": {"font": "F10", "design": "Design03"}},
    )

    assert execution["selections"] == {"Output_main": {"font": "F10", "design": "Design03"}}


@pytest.mark.parametrize(
    ("task_patch", "code"),
    [
        (lambda task: task.update({"outputs": []}), "render_task_empty"),
        (lambda task: task["outputs"][0].update({"actions": []}), "render_task_empty"),
    ],
)
def test_empty_render_task_does_not_enter_illustrator(tmp_path, task_patch, code):
    task = compiled_task()
    task_patch(task)
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            task,
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"font": "F10", "design": "03", "name": "Alice"},
            task_file=tmp_path / "task.json",
        )

    assert exc_info.value.code == code
    assert bridge.calls == []
    assert not (tmp_path / "task.json").exists()


def test_missing_output_path_does_not_enter_illustrator(tmp_path):
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            compiled_task(),
            template_ai=tmp_path / "template.ai",
            output_ai="",
            values={"font": "F10", "design": "03", "name": "Alice"},
            task_file=tmp_path / "task.json",
        )

    assert exc_info.value.code == "output_ai_missing"
    assert bridge.calls == []
    assert not (tmp_path / "task.json").exists()


def test_required_slot_empty_does_not_enter_illustrator(tmp_path):
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            compiled_task(),
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"font": "F10", "design": "03", "name": "   "},
            task_file=tmp_path / "task.json",
        )

    assert exc_info.value.code == "required_slot_empty"
    assert bridge.calls == []
    assert not (tmp_path / "task.json").exists()


def test_missing_option_selection_does_not_enter_illustrator(tmp_path):
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            compiled_task(),
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"font": "F10", "design": "unknown", "name": "Alice"},
            task_file=tmp_path / "task.json",
        )

    assert exc_info.value.code == "option_selection_missing"
    assert bridge.calls == []
    assert not (tmp_path / "task.json").exists()


def test_missing_style_selection_for_final_fit_does_not_enter_illustrator(tmp_path):
    task = compiled_task()
    task["outputs"][0]["actions"].append(
        {
            "type": "fit_output_bounds",
            "group": "style",
            "style_key": "style1",
            "dimensions": {"mode": "style", "width_mm": 80, "height_mm": 50},
        }
    )
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            task,
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"font": "F10", "design": "03", "name": "Alice"},
            task_file=tmp_path / "task.json",
        )

    assert exc_info.value.code == "option_selection_missing"
    assert bridge.calls == []
    assert not (tmp_path / "task.json").exists()


def test_optional_empty_slot_is_passed_to_jsx_for_removal(tmp_path):
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")
    task_path = tmp_path / "task.json"

    result = renderer.render(
        compiled_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "F10", "design": "03", "name": "Alice", "year": ""},
        task_file=task_path,
    )

    assert result == "done.ai"
    assert len(bridge.calls) == 1
    assert bridge.calls[0]["script_path"].name == "render_v2_template.jsx"
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    assert payload["values"]["year"] == ""
    assert payload["selections"]["Output_main"]["design"] == "Design03"
