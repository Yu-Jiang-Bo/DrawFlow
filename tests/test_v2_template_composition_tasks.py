import json
from pathlib import Path
import shutil
import subprocess

import pytest

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
        {
            "path": str(tmp_path / "component-a.ai"),
            "component_contract_file": str(tmp_path / "component-a.warnings.json"),
            "order_no": "ORDER-1",
        },
        {
            "path": str(tmp_path / "component-b.ai"),
            "component_contract_file": str(tmp_path / "component-b.warnings.json"),
            "order_no": "ORDER-1",
        },
    ]
    assert component_task["component_contract_file"] == str(tmp_path / "component.warnings.json")
    assert final_task["label_lines"] == ["ORDER-1", "金色"]


def test_order_column_task_carries_per_product_annotation_groups(tmp_path):
    task = build_v2_order_column_task(
        input_ai_files=[tmp_path / "component-a.ai", tmp_path / "component-b.ai", tmp_path / "component-c.ai"],
        input_order_nos=["ORDER-1", "ORDER-1", "ORDER-1"],
        output_ai=tmp_path / "single-order.ai",
        input_annotation_groups=[
            {"group_key": "product-1", "label_lines": ["ORDER-1", "礼盒"]},
            {"group_key": "product-1", "label_lines": ["ORDER-1", "礼盒"]},
            {"group_key": "product-2", "label_lines": ["收纳盒"]},
        ],
    )

    assert "label_lines" not in task
    assert task["inputs"] == [
        {
            "path": str(tmp_path / "component-a.ai"),
            "component_contract_file": str(tmp_path / "component-a.warnings.json"),
            "order_no": "ORDER-1",
            "annotation_group": "product-1",
            "label_lines": ["ORDER-1", "礼盒"],
        },
        {
            "path": str(tmp_path / "component-b.ai"),
            "component_contract_file": str(tmp_path / "component-b.warnings.json"),
            "order_no": "ORDER-1",
            "annotation_group": "product-1",
            "label_lines": ["ORDER-1", "礼盒"],
        },
        {
            "path": str(tmp_path / "component-c.ai"),
            "component_contract_file": str(tmp_path / "component-c.warnings.json"),
            "order_no": "ORDER-1",
            "annotation_group": "product-2",
            "label_lines": ["收纳盒"],
        },
    ]


def test_order_column_composer_supports_per_product_annotation_blocks():
    source = Path("scripts/illustrator/compose_v2_order_column.jsx").read_text(encoding="utf-8")

    assert "input.annotation_group" in source
    assert "input.label_lines" in source
    assert "bucket.labelLines" in source
    assert "layoutOrderBlocks(layer, orderBuckets, gap, labelHeight, labelGap, labelFontSize)" in source
    assert "function addProductionLabelsAboveBlock" in source
    assert "artworkTop = currentTop - labelSpace" in source
    assert "addProductionLabelsAboveBlock(" in source


def test_order_column_composer_round_trips_multi_frame_aggregate_contract():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")

    source = Path("scripts/illustrator/compose_v2_order_column.jsx").read_text(encoding="utf-8")
    functions = (
        "writeComponentContract",
        "readComponentFrame",
        "readSingleComponentFrame",
        "readAggregateComponentFrame",
        "translateTrackedSlots",
        "translateBounds",
        "copyBounds",
        "validBounds",
        "stringifyJson",
    )
    executable = "\n".join(_extract_js_function(source, name) for name in functions)
    harness = f"""
let written = "";
function File(path) {{
  return {{
    fsName: path,
    parent: {{}},
    open: () => true,
    write: value => {{ written = value; }},
    close: () => true
  }};
}}
function ensureFolder() {{}}
let parsedContract = null;
function readJSON() {{ return parsedContract; }}
{executable}

const entries = [
  {{
    key: "component-a",
    final_frame_bounds: [0, 100, 80, 50],
    translation: {{x: 0, y: 0}},
    frame: {{frame_bounds: [0, 50, 80, 0], artwork_bounds_after: [2, 48, 78, 2], tracked_slots: []}},
    actual_artwork_bounds: [2, 98, 78, 52]
  }},
  {{
    key: "component-b",
    final_frame_bounds: [0, 42, 120, -18],
    translation: {{x: 0, y: -58}},
    frame: {{frame_bounds: [0, 60, 120, 0], artwork_bounds_after: [1, 59, 119, 1], tracked_slots: []}},
    actual_artwork_bounds: [1, 41, 119, -17]
  }}
];
writeComponentContract(
  {{component_contract_file: "order.warnings.json"}},
  entries,
  [-10, 112, 120, -18],
  [-8, 110, 119, -17]
);
parsedContract = JSON.parse(written);
if (parsedContract.component_frames.length !== 2) throw new Error("first-level frames were lost");
const frame = readComponentFrame({{
  component_contract_file: "order.warnings.json",
  component_frame_mode: "aggregate"
}});
if (JSON.stringify(frame.frame_bounds) !== JSON.stringify([-10, 112, 120, -18])) throw new Error("aggregate frame mismatch");
if (JSON.stringify(frame.artwork_bounds_after) !== JSON.stringify([-8, 110, 119, -17])) throw new Error("aggregate artwork mismatch");
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert ".resize(" not in source
    assert "readComponentFrame(input)" in source
    assert "unionBounds(layer.pageItems)" in source


def _extract_js_function(source, name):
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed JavaScript function: {name}")


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
        "component_contract_version": 1,
        "inputs": [{
            "path": str(tmp_path / "gold.ai"),
            "component_contract_file": str(tmp_path / "gold.warnings.json"),
            "color_option": "金色",
            "order_nos": ["ORDER-1"],
        }],
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


def test_v2_output_transforms_keep_pre_defer_execution_without_weakening_terminal_outputs():
    order_source = Path("scripts/illustrator/compose_v2_order_column.jsx").read_text(encoding="utf-8")
    render_source = Path("scripts/illustrator/render_v2_template.jsx").read_text(encoding="utf-8")
    png_master_source = Path("scripts/illustrator/compose_png_master_pages.jsx").read_text(encoding="utf-8")
    renderer_source = Path("src/renderer/v2_template_renderer.py").read_text(encoding="utf-8")
    task_builder_source = Path("src/service/v2_order_task_builder.py").read_text(encoding="utf-8")
    pipeline_source = Path("src/service/production_pipeline.py").read_text(encoding="utf-8")

    assert "function applyOutputTransforms(doc, policy)" in order_source
    assert render_source.index("applyOutputTransforms(doc, execution.output || task.output || {});") < render_source.index(
        "var finalFitAction = selectedFitAction"
    )
    assert "defer_output_transforms" not in renderer_source
    assert "defer_output_transforms" not in task_builder_source
    assert 'task["output"] = {"outline_text": False, "pathfinder_merge": False}' not in pipeline_source
    assert png_master_source.index("drawFrame(layer, 0, pageHeight, frameWidth, pageHeight);") < png_master_source.index(
        "applyOutputTransforms(doc, task.output || {});"
    ) < png_master_source.index("saveAsAI(doc, aiFile, String(task.compatibility || \"CS5\"));")


def test_v2_terminal_output_composers_reacquire_and_gate_all_text_frames():
    scripts = (
        Path("scripts/illustrator/compose_v2_order_column.jsx"),
        Path("scripts/illustrator/compose_color_frames.jsx"),
        Path("scripts/illustrator/compose_png_master_pages.jsx"),
    )

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert "doc.textFrames.length" in source
        assert "while (doc.textFrames.length > 0)" in source
        assert "var frame = doc.textFrames[beforeCount - 1];" in source
        assert "function collectTextFrames(container, result)" in source
        assert "createOutline();" in source
        assert "function assertNoTextFrames(doc, stage)" in source
        assert "frames[index].createOutline();" not in source


def test_v2_template_renderer_recursively_outlines_and_gates_all_text_frames():
    source = Path("scripts/illustrator/render_v2_template.jsx").read_text(encoding="utf-8")

    assert "function collectTextFrames(container, result)" in source
    assert "createOutline();" in source
    assert "function assertNoTextFrames(doc, stage)" in source


def test_v2_terminal_output_composers_only_merge_overlapping_compatible_text_outlines():
    scripts = (
        Path("scripts/illustrator/compose_v2_order_column.jsx"),
        Path("scripts/illustrator/compose_color_frames.jsx"),
        Path("scripts/illustrator/compose_png_master_pages.jsx"),
    )

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert "function mergeOverlappingTextOutlines(outlines, context)" in source
        assert "if (consumed[candidate] || !sameMergeStyle(current, outlines[candidate])) continue;" in source
        assert "if (!boundsOverlap(current.bounds, outlines[candidate].bounds)) continue;" in source
        assert "return left.styleKey !== null && right.styleKey !== null && left.styleKey === right.styleKey;" in source
        assert "app.executeMenuCommand(\"Live Pathfinder Add\");" in source
        assert "app.executeMenuCommand(\"expandStyle\");" in source
        assert "if (items.length < 2) return;" in source
        assert "outline.selected = true;" not in source


def test_v2_terminal_output_composers_skip_ineligible_pathfinder_clusters():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")

    scripts = (
        Path("scripts/illustrator/compose_v2_order_column.jsx"),
        Path("scripts/illustrator/compose_color_frames.jsx"),
        Path("scripts/illustrator/compose_png_master_pages.jsx"),
    )
    functions = (
        "mergeOverlappingTextOutlines",
        "sameMergeStyle",
        "boundsOverlap",
        "mergeOutlineItems",
    )
    cases = (
        ([{"bounds": [0, 10, 10, 0], "styleKey": "A"}], []),
        (
            [
                {"bounds": [0, 10, 10, 0], "styleKey": "A"},
                {"bounds": [20, 10, 30, 0], "styleKey": "A"},
            ],
            [],
        ),
        (
            [
                {"bounds": [0, 10, 10, 0], "styleKey": None},
                {"bounds": [5, 10, 15, 0], "styleKey": None},
            ],
            [],
        ),
        (
            [
                {"bounds": [0, 10, 10, 0], "styleKey": "A"},
                {"bounds": [5, 10, 15, 0], "styleKey": "A"},
            ],
            ["Live Pathfinder Add", "expandStyle"],
        ),
    )

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        executable = "\n".join(_extract_js_function(source, name) for name in functions)
        for outlines, expected in cases:
            payload = [dict(outline, item={"selected": False}) for outline in outlines]
            harness = f"""
const calls = [];
global.app = {{ executeMenuCommand: command => calls.push(command) }};
{executable}
mergeOverlappingTextOutlines({json.dumps(payload)}, "test");
const pathfinderCalls = calls.filter(command => command !== "deselectall");
const expected = {json.dumps(expected)};
if (JSON.stringify(pathfinderCalls) !== JSON.stringify(expected)) {{
  throw new Error(JSON.stringify(pathfinderCalls));
}}
"""
            result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)
            assert result.returncode == 0, f"{script}: {result.stderr}"


def _extract_js_function(source, name):
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed JavaScript function: {name}")


def test_v2_terminal_cross_frame_dedupe_refuses_unverifiable_or_visually_different_styles():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")

    scripts = (
        Path("scripts/illustrator/compose_v2_order_column.jsx"),
        Path("scripts/illustrator/compose_color_frames.jsx"),
        Path("scripts/illustrator/compose_png_master_pages.jsx"),
    )
    functions = (
        "uniformTextStyleKey",
        "characterStyleKey",
        "stylePropertyValues",
        "colorStyleKey",
        "mergeOverlappingTextOutlines",
        "sameMergeStyle",
        "boundsOverlap",
        "mergeOutlineItems",
    )

    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert "if (font === null || fill === null || stroke === null) return null;" in source
        assert "if (type[0] === \"NoColor\") return \"NoColor\";" in source
        assert "if (typeof value === \"undefined\") return null;" in source
        assert "Gradient and pattern transforms are object-level state." in source
        executable = "\n".join(_extract_js_function(source, name) for name in functions)
        harness = f"""
const calls = [];
global.app = {{ executeMenuCommand: command => calls.push(command) }};
{executable}

function attributes(fontName, red) {{
  return {{
    textFont: {{ name: fontName }},
    fillColor: {{ typename: "RGBColor", red: red, green: 20, blue: 30 }},
    strokeColor: {{ typename: "NoColor" }},
    strokeWeight: 0,
    size: 10,
    horizontalScale: 100,
    verticalScale: 100,
    baselineShift: 0,
    tracking: 0,
    overprintFill: false,
    overprintStroke: false
  }};
}}

function frame(fontName, red, opacity) {{
  return {{
    textRange: {{ characters: [{{ characterAttributes: attributes(fontName, red) }}] }},
    opacity: opacity,
    blendingMode: "NORMAL"
  }};
}}

const base = uniformTextStyleKey(frame("FontA", 10, 100));
const differentColor = uniformTextStyleKey(frame("FontA", 11, 100));
const differentFont = uniformTextStyleKey(frame("FontB", 10, 100));
const differentOpacity = uniformTextStyleKey(frame("FontA", 10, 90));
const cmykFrame = frame("FontA", 10, 100);
cmykFrame.textRange.characters[0].characterAttributes.fillColor = {{
  typename: "CMYKColor", cyan: 0, magenta: 10, yellow: 20, black: 30
}};
const cmyk = uniformTextStyleKey(cmykFrame);
const unreadableOpacity = frame("FontA", 10, 100);
Object.defineProperty(unreadableOpacity, "opacity", {{ get: () => {{ throw new Error("blocked"); }} }});
const unreadableFill = frame("FontA", 10, 100);
Object.defineProperty(unreadableFill.textRange.characters[0].characterAttributes, "fillColor", {{ get: () => {{ throw new Error("blocked"); }} }});

if (base === null || cmyk === null || base === differentColor || base === differentFont || base === differentOpacity) {{
  throw new Error("distinct readable styles produced the same key");
}}
if (uniformTextStyleKey(unreadableOpacity) !== null || uniformTextStyleKey(unreadableFill) !== null) {{
  throw new Error("unreadable style property produced a mergeable key");
}}

for (const candidate of [differentColor, differentFont, differentOpacity, null]) {{
  calls.length = 0;
  mergeOverlappingTextOutlines([
    {{ item: {{ selected: false }}, bounds: [0, 10, 10, 0], styleKey: base }},
    {{ item: {{ selected: false }}, bounds: [5, 10, 15, 0], styleKey: candidate }}
  ], "test");
  if (calls.some(command => command !== "deselectall")) throw new Error("different or unreadable styles merged");
}}

calls.length = 0;
mergeOverlappingTextOutlines([
  {{ item: {{ selected: false }}, bounds: [0, 10, 10, 0], styleKey: base }},
  {{ item: {{ selected: false }}, bounds: [5, 10, 15, 0], styleKey: base }}
], "test");
const computedStyleCalls = calls.filter(command => command !== "deselectall");
if (JSON.stringify(computedStyleCalls) !== JSON.stringify(["Live Pathfinder Add", "expandStyle"])) {{
  throw new Error("matching readable styles did not merge");
}}
"""
        result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{script}: {result.stderr}"


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
