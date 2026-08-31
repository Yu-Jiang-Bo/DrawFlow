import json
from pathlib import Path

from src.renderer.v2_template_renderer import (
    V2TemplateRenderer,
    build_v2_color_frames_task,
    build_v2_order_column_task,
    build_v2_png_master_pages_task,
)


class FakeBridge:
    def __init__(self):
        self.calls = []

    def render(self, script_path, task_path):
        self.calls.append({"script_path": script_path, "task_path": task_path})
        return "done.ai"


def test_order_column_task_keeps_unannotated_components_distinct_from_final_labels(tmp_path):
    component_task = build_v2_order_column_task(
        input_ai_files=[tmp_path / "component-a.ai", tmp_path / "component-b.ai"],
        input_order_nos=["ORDER-1", "ORDER-1"],
        output_ai=tmp_path / "component.ai",
    )
    final_task = build_v2_order_column_task(
        input_ai_files=[tmp_path / "component-a.ai", tmp_path / "component-b.ai"],
        input_order_nos=["ORDER-1", "ORDER-1"],
        output_ai=tmp_path / "single-order.ai",
        label_lines=["ORDER-1", "金色"],
    )

    assert component_task["type"] == "compose_v2_order_column"
    assert "label_lines" not in component_task
    assert component_task["inputs"] == [
        {"path": str(tmp_path / "component-a.ai"), "order_no": "ORDER-1"},
        {"path": str(tmp_path / "component-b.ai"), "order_no": "ORDER-1"},
    ]
    assert final_task["label_lines"] == ["ORDER-1", "金色"]


def test_color_frame_task_preserves_public_packing_and_component_references(tmp_path):
    task = build_v2_color_frames_task(
        inputs=[{"path": str(tmp_path / "gold.ai"), "color_option": "金色", "order_nos": ["ORDER-1"]}],
        output_ai=tmp_path / "summary.ai",
        master_packing={"target_width_mm": 480},
        compatibility="Illustrator 8",
        show_color_header=True,
        show_color_frame_boundary=True,
        debug_report_path=tmp_path / "summary.debug.json",
    )

    assert task == {
        "type": "compose_color_frames",
        "output_ai": str(tmp_path / "summary.ai"),
        "master_packing": {"target_width_mm": 480},
        "compatibility": "Illustrator 8",
        "show_color_header": True,
        "show_color_frame_boundary": True,
        "inputs": [{"path": str(tmp_path / "gold.ai"), "color_option": "金色", "order_nos": ["ORDER-1"]}],
        "debug": {"report_path": str(tmp_path / "summary.debug.json")},
    }


def test_png_master_task_keeps_paging_settings_in_the_pure_payload(tmp_path):
    task = build_v2_png_master_pages_task(
        items=[{"path": str(tmp_path / "single.png"), "order_no": "ORDER-1"}],
        output_ai=tmp_path / "master.ai",
        frame_width_mm=580,
        frame_height_mm=2000,
        margin_mm=4,
        column_gap_mm=2,
        row_gap_mm=3,
        label_height_mm=4,
        label_width_mm=30,
        label_gap_mm=0.8,
        preview_background={"enabled": True},
        debug_report_path=tmp_path / "master.debug.json",
        page_count=2,
        output_policy={"outline_text": True, "pathfinder_merge": False},
    )

    assert task["type"] == "compose_png_master_pages"
    assert task["compatibility"] == "CS5"
    assert task["page_count"] == 2
    assert task["preview_background"] == {"enabled": True}
    assert task["debug"] == {"report_path": str(tmp_path / "master.debug.json")}
    assert task["output"] == {"outline_text": True, "pathfinder_merge": False}


def test_png_master_composer_outlines_final_labels_only_after_layout():
    source = Path("scripts/illustrator/compose_png_master_pages.jsx").read_text(encoding="utf-8")

    assert "function applyOutputTransforms(doc, policy)" in source
    assert source.index("drawFrame(layer, 0, pageHeight, frameWidth, pageHeight);") < source.index(
        "applyOutputTransforms(doc, task.output || {});"
    ) < source.index("saveAsAI(doc, aiFile, String(task.compatibility || \"CS5\"));")


def test_v2_output_composers_recursively_outline_and_gate_all_text_frames():
    scripts = (
        Path("scripts/illustrator/compose_v2_order_column.jsx"),
        Path("scripts/illustrator/compose_png_master_pages.jsx"),
        Path("scripts/illustrator/render_v2_template.jsx"),
        Path("scripts/illustrator/compose_color_frames.jsx"),
    )

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert "function collectTextFrames(container, result)" in source
        assert "createOutline();" in source
        assert "function assertNoTextFrames(doc, stage)" in source


def test_composition_task_builders_do_not_share_nested_input_values(tmp_path):
    color_inputs = [{"path": str(tmp_path / "gold.ai"), "order_nos": ["ORDER-1"]}]
    packing = {"target_width_mm": 480, "nested": {"gap": 2}}
    color_task = build_v2_color_frames_task(
        inputs=color_inputs,
        output_ai=tmp_path / "summary.ai",
        master_packing=packing,
    )
    png_items = [{"path": str(tmp_path / "single.png"), "metadata": {"order": "ORDER-1"}}]
    background = {"enabled": True, "cmyk": [0, 0, 0, 35]}
    png_task = build_v2_png_master_pages_task(
        items=png_items,
        output_ai=tmp_path / "master.ai",
        frame_width_mm=580,
        frame_height_mm=2000,
        margin_mm=4,
        column_gap_mm=2,
        row_gap_mm=3,
        label_height_mm=4,
        label_width_mm=30,
        label_gap_mm=0.8,
        preview_background=background,
    )

    color_inputs[0]["order_nos"].append("ORDER-2")
    packing["nested"]["gap"] = 99
    png_items[0]["metadata"]["order"] = "CHANGED"
    background["cmyk"][0] = 100
    color_task["inputs"][0]["order_nos"].append("ORDER-3")
    png_task["items"][0]["metadata"]["order"] = "TASK"

    assert color_task["inputs"][0]["order_nos"] == ["ORDER-1", "ORDER-3"]
    assert color_task["master_packing"]["nested"] == {"gap": 2}
    assert png_task["items"][0]["metadata"] == {"order": "TASK"}
    assert png_task["preview_background"] == {"enabled": True, "cmyk": [0, 0, 0, 35]}
    assert color_inputs[0]["order_nos"] == ["ORDER-1", "ORDER-2"]
    assert png_items[0]["metadata"] == {"order": "CHANGED"}
    assert background["cmyk"] == [100, 0, 0, 35]


def test_composition_wrappers_write_the_same_tasks_and_select_the_expected_scripts(tmp_path):
    bridge = FakeBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")
    order_task_file = tmp_path / "order.json"
    color_task_file = tmp_path / "color.json"
    png_task_file = tmp_path / "png.json"

    renderer.compose_order_column(
        input_ai_files=[tmp_path / "component.ai"],
        input_order_nos=["ORDER-1"],
        output_ai=tmp_path / "order.ai",
        task_file=order_task_file,
        label_lines=["ORDER-1"],
    )
    renderer.compose_color_frames(
        inputs=[{"path": str(tmp_path / "order.ai"), "color_option": "金色", "order_nos": ["ORDER-1"]}],
        output_ai=tmp_path / "color.ai",
        task_file=color_task_file,
        master_packing={"target_width_mm": 480},
        show_color_header=True,
    )
    renderer.compose_png_master_pages(
        items=[{"path": str(tmp_path / "single.png"), "order_no": "ORDER-1"}],
        output_ai=tmp_path / "master.ai",
        task_file=png_task_file,
        frame_width_mm=580,
        frame_height_mm=2000,
        margin_mm=4,
        column_gap_mm=2,
        row_gap_mm=3,
        label_height_mm=4,
        label_width_mm=30,
        label_gap_mm=0.8,
    )

    assert json.loads(order_task_file.read_text(encoding="utf-8")) == build_v2_order_column_task(
        input_ai_files=[tmp_path / "component.ai"],
        input_order_nos=["ORDER-1"],
        output_ai=tmp_path / "order.ai",
        label_lines=["ORDER-1"],
    )
    assert json.loads(color_task_file.read_text(encoding="utf-8")) == build_v2_color_frames_task(
        inputs=[{"path": str(tmp_path / "order.ai"), "color_option": "金色", "order_nos": ["ORDER-1"]}],
        output_ai=tmp_path / "color.ai",
        master_packing={"target_width_mm": 480},
        show_color_header=True,
    )
    assert json.loads(png_task_file.read_text(encoding="utf-8")) == build_v2_png_master_pages_task(
        items=[{"path": str(tmp_path / "single.png"), "order_no": "ORDER-1"}],
        output_ai=tmp_path / "master.ai",
        frame_width_mm=580,
        frame_height_mm=2000,
        margin_mm=4,
        column_gap_mm=2,
        row_gap_mm=3,
        label_height_mm=4,
        label_width_mm=30,
        label_gap_mm=0.8,
    )
    assert [call["script_path"].name for call in bridge.calls] == [
        "compose_v2_order_column.jsx",
        "compose_color_frames.jsx",
        "compose_png_master_pages.jsx",
    ]
