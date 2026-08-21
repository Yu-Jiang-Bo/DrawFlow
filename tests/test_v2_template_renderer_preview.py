import json

import pytest

from src.renderer.v2_template_renderer import (
    V2TemplateRenderer,
    V2TemplateRendererError,
    build_v2_execution_task,
)
from tests.test_v2_template_renderer import FakeBridge, compiled_task


def compiled_multi_output_task():
    task = compiled_task()
    side_b = json.loads(json.dumps(task["outputs"][0]))
    side_b["key"] = "Output_SideB"
    for action in side_b["actions"]:
        action["object_path"] = str(action["object_path"]).replace("Output_main", "Output_SideB")
    task["outputs"].append(side_b)
    task["option_mappings"].extend(
        {**item, "output": "Output_SideB"}
        for item in list(task["option_mappings"])
    )
    return task


def test_builds_single_output_preview_execution_with_warning_file(tmp_path):
    preview_png = tmp_path / "preview.png"
    warning_file = tmp_path / "warnings.json"

    execution = build_v2_execution_task(
        compiled_multi_output_task(),
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "F10", "design": "03", "name": "Alice"},
        output_key="Output_SideB",
        preview_png=preview_png,
        layout_warning_file=warning_file,
    )

    assert execution["output_key"] == "Output_SideB"
    assert execution["preview_png"] == str(preview_png)
    assert execution["layout_warning_file"] == str(warning_file)
    assert set(execution["selections"]) == {"Output_main", "Output_SideB"}


@pytest.mark.parametrize(
    ("output_key", "preview_png", "code"),
    [
        ("Output_missing", None, "output_key_unknown"),
        (None, "preview.png", "preview_output_key_missing"),
    ],
)
def test_rejects_invalid_preview_output_contract(tmp_path, output_key, preview_png, code):
    with pytest.raises(V2TemplateRendererError) as exc_info:
        build_v2_execution_task(
            compiled_task(),
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "out.ai",
            values={"font": "F10", "design": "03", "name": "Alice"},
            output_key=output_key,
            preview_png=tmp_path / preview_png if preview_png else None,
        )

    assert exc_info.value.code == code


def test_selected_output_ignores_invalid_unselected_output(tmp_path):
    task = compiled_multi_output_task()
    task["outputs"][0]["actions"] = []

    execution = build_v2_execution_task(
        task,
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "F10", "design": "03", "name": "Alice"},
        output_key="Output_SideB",
    )

    assert execution["output_key"] == "Output_SideB"


def test_required_split_part_missing_does_not_enter_illustrator(tmp_path):
    task = compiled_task()
    action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_name")
    action.update({"preset": "split_by_pipe", "source_part_index": 1})
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

    assert exc_info.value.code == "required_slot_empty"
    assert bridge.calls == []
