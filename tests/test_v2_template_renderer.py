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
    assert "output_key" not in execution
    assert "preview_png" not in execution


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


def test_select_style_action_is_renderable_without_final_fit(tmp_path):
    task = compiled_task()
    task["option_mappings"].append(
        {
            "output": "Output_main",
            "group": "style",
            "field": "style",
            "source_value": "small",
            "target": "style1",
        }
    )
    task["outputs"][0]["actions"] = [
        {
            "type": "select_style",
            "group": "style",
            "option_key": "style1",
            "object_path": "Template/Output_main/Style/style1",
        }
    ]
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")
    task_path = tmp_path / "task.json"

    result = renderer.render(
        task,
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"style": "small"},
        task_file=task_path,
    )

    assert result == "done.ai"
    assert len(bridge.calls) == 1
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    assert payload["selections"] == {"Output_main": {"style": "style1"}}


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
