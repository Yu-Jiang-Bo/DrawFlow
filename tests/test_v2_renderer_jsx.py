import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/illustrator/render_v2_template.jsx")
TAIL_INCLUDE = Path("scripts/illustrator/v2_tail_text.jsxinc")
TAIL_PUA_BASE = 0xF000


def run_node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    return subprocess.run([node, "-e", script], capture_output=True, text=True, check=False)


def jsx_source_expression():
    return (
        f"fs.readFileSync({json.dumps(str(SCRIPT.resolve()))}, 'utf8')"
        ".replace(/^#target.*\\r?\\n/, '')"
        f".replace(/^#include\\s+\"v2_tail_text\\.jsxinc\"\\s*\\r?\\n/m, fs.readFileSync({json.dumps(str(TAIL_INCLUDE.resolve()))}, 'utf8') + '\\n')"
    )


def test_v2_renderer_jsx_parses_in_node():
    harness = f"""
const fs = require('fs');
const source = {jsx_source_expression()};
new Function(source);
"""

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_static_contract_uses_paths_and_safe_actions():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "function findPageItemByPath" in source
    assert "function findPageItemByRelativePath" in source
    assert "function copyOptionGroup" in source
    assert "function replaceSlotText" in source
    assert "function splitPipeValue" in source
    assert "function removePageItem" in source
    assert '#include "v2_tail_text.jsxinc"' in source
    assert TAIL_INCLUDE.exists()
    assert "function saveAsAI8" in source
    assert "findPageItemsByName" not in source
    assert "app.doScript" not in source
    assert "eval(" not in source
    assert "JJMB" not in source
    assert "tailTextForSample" not in source
    include = TAIL_INCLUDE.read_text(encoding="utf-8")
    assert "var V2TailText" in include
    assert "function tailGlyphForSpec" in include
    assert "String.fromCharCode" in include


def test_v2_renderer_jsx_runs_without_native_json_parser():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "layout_warning_file": "warnings.json",
        "values": {},
        "selections": {},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [],
        },
    }
    harness = node_mock_harness(task, """
if (savedAs !== 'out.ai') throw new Error('output was not saved');
if (writtenFiles['warnings.json'] !== '{"warnings":[]}') throw new Error('warnings were not written without JSON');
""", disable_native_json=True)

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_binds_asset_library_from_source_field_initial():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"initial": "Tom"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "bind_asset_library",
                            "group": "design",
                            "option_key": "Design03",
                            "asset_key": "initial_top",
                            "slot_key": "slot_initial",
                            "slot_path": "Template/Output_main/Design/Design03/slot_initial",
                            "object_path": "Template/Output_main/Design/Design03/Assets/initial_top",
                            "source_field": "initial",
                            "supported_values": ["A", "T"],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const design = outputLayer.pageItems[0];
const names = design.pageItems.map(item => item.name);
if (!names.includes('T')) throw new Error('initial asset T was not inserted: ' + names.join(','));
if (names.includes('slot_initial')) throw new Error('placeholder slot was not removed');
if (names.includes('Assets')) throw new Error('asset library was not cleaned up');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_copies_selected_groups_and_preserves_pipe_in_direct_text():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"font": "F10", "design": "03", "name": "Alice", "multi": "Amy|Beth|Cara"},
        "selections": {"Output_main": {"font": "F10", "design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
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
                            "object_path": "Template/Output_main/Font/F10/slot_name",
                            "source_field": "name",
                            "required": True,
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "multi",
                            "required": True,
                            "tail_paths": [
                                "Template/Output_main/Design/Design03/tail_name_1",
                                "Template/Output_main/Design/Design03/tail_name_2",
                            ],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const fontCopy = outputLayer.pageItems.find(item => item.name === 'F10');
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!fontCopy) throw new Error('F10 was not copied');
if (outputLayer.pageItems.find(item => item.name === 'F1')) throw new Error('unselected F1 was copied');
if (!designCopy) throw new Error('Design03 was not copied');
const fontSlot = child(fontCopy, 'slot_name');
const fixed = fontCopy.pageItems.find(item => item.typename === 'PathItem' && item.name === '');
if (!fixed) throw new Error('unnamed fixed object was not preserved');
if (fontSlot.contents !== 'Alice') throw new Error('font slot not replaced: ' + fontSlot.contents);
if (fontSlot.styleToken !== 'F10-style') throw new Error('font style was not preserved');
if (child(designCopy, 'slot_name').contents !== 'Amy|Beth|Cara') throw new Error('direct text was split: ' + child(designCopy, 'slot_name').contents);
if (designCopy.pageItems.find(item => item.name === 'tail_name_1')) throw new Error('direct text populated a split-only tail');
if (designCopy.pageItems.find(item => item.name === 'tail_name_2')) throw new Error('direct text populated a split-only tail');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["savedAs"] == "out.ai"


def test_v2_renderer_copies_selected_f1_and_replaces_its_slot():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"font": "F1", "name": "Frank"},
        "selections": {"Output_main": {"font": "F1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F10",
                            "object_path": "Template/Output_main/Font/F10",
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const f1Copy = outputLayer.pageItems.find(item => item.name === 'F1');
if (!f1Copy) throw new Error('F1 was not copied');
if (outputLayer.pageItems.find(item => item.name === 'F10')) throw new Error('unselected F10 was copied');
const slot = child(f1Copy, 'slot_name');
if (slot.contents !== 'Frank') throw new Error('F1 slot not replaced: ' + slot.contents);
if (slot.styleToken !== 'F1-style') throw new Error('F1 style was not preserved');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_replaces_pure_design_direct_text_slot():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "year": "2027"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_year",
                            "source_field": "year",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!designCopy) throw new Error('Design03 was not copied');
const slot = child(designCopy, 'slot_year');
if (slot.contents !== '2027') throw new Error('design slot not replaced: ' + slot.contents);
if (slot.styleToken !== 'Year-style') throw new Error('design slot style was not preserved');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_replaces_split_by_pipe_slots_by_source_part_index():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": " Jay | | Tom "},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "source_part_index": 0,
                            "required": True,
                            "preset": "split_by_pipe",
                            "tail_paths": [],
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03/slot_year",
                            "source_field": "name",
                            "source_part_index": 1,
                            "required": True,
                            "preset": "split_by_pipe",
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!designCopy) throw new Error('Design03 was not copied');
if (child(designCopy, 'slot_name').contents !== 'Jay') throw new Error('first split slot mismatch: ' + child(designCopy, 'slot_name').contents);
if (child(designCopy, 'slot_year').contents !== 'Tom') throw new Error('second split slot mismatch: ' + child(designCopy, 'slot_year').contents);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_filters_one_output_and_exports_visible_bounds_preview():
    actions = [
        {
            "type": "copy_option_group",
            "group": "design",
            "option_key": "Design03",
            "object_path": "Template/Output_main/Design/Design03",
        }
    ]
    side_b_actions = json.loads(json.dumps(actions))
    side_b_actions[0]["object_path"] = "Template/Output_SideB/Design/Design03"
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "output_key": "Output_SideB",
        "preview_png": "preview.png",
        "values": {},
        "selections": {
            "Output_main": {"design": "Design03"},
            "Output_SideB": {"design": "Design03"},
        },
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {"key": "Output_main", "actions": actions},
                {"key": "Output_SideB", "actions": side_b_actions},
            ],
        },
    }
    harness = node_mock_harness(task, """
if (outputLayer.pageItems.length !== 1) throw new Error('preview rendered more than one output');
if (exportedAs !== 'preview.png') throw new Error('preview PNG was not exported');
if (!exportOptions || exportOptions.artBoardClipping !== true || exportOptions.transparency !== true) throw new Error('preview PNG options mismatch');
const visible = outputLayer.pageItems[0].visibleBounds;
const artboard = outputDoc.artboards[0].artboardRect;
const expectedArtboard = [visible[0] - 12, visible[1] + 12, visible[2] + 12, visible[3] - 12];
if (JSON.stringify(artboard) !== JSON.stringify(expectedArtboard)) throw new Error('preview artboard does not include safe visible-bounds margin');
if (JSON.stringify(savedArtboard) !== JSON.stringify(visible)) throw new Error('formal AI saved preview margin into its artboard');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["exportedAs"] == "preview.png"
    assert payload["copied"] == ["Design03"]


def test_v2_renderer_without_preview_filter_keeps_all_outputs_and_skips_png():
    actions = [
        {
            "type": "copy_option_group",
            "group": "design",
            "option_key": "Design03",
            "object_path": "Template/Output_main/Design/Design03",
        }
    ]
    side_b_actions = json.loads(json.dumps(actions))
    side_b_actions[0]["object_path"] = "Template/Output_SideB/Design/Design03"
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {},
        "selections": {
            "Output_main": {"design": "Design03"},
            "Output_SideB": {"design": "Design03"},
        },
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {"key": "Output_main", "actions": actions},
                {"key": "Output_SideB", "actions": side_b_actions},
            ],
        },
    }
    harness = node_mock_harness(task, """
if (outputLayer.pageItems.length !== 2) throw new Error('formal render did not keep all outputs');
if (exportedAs) throw new Error('formal render exported an internal preview PNG');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["savedAs"] == "out.ai"
    assert payload["exportedAs"] == ""
    assert payload["copied"] == ["Design03", "Design03"]


def test_v2_renderer_combines_design_slot_with_selected_font_style_source():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "font": "F10", "name": "Carla"},
        "selections": {"Output_main": {"design": "Design03", "font": "F10"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F10",
                            "object_path": "Template/Output_main/Font/F10",
                            "source_only": True,
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                            "style_source": {
                                "group": "font",
                                "slot_key": "slot_name",
                                "paths_by_option": {"F10": "Template/Output_main/Font/F10/slot_name"},
                            },
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!designCopy) throw new Error('Design03 was not copied');
if (outputLayer.pageItems.find(item => item.name === 'F10')) throw new Error('source-only F10 copy was not removed');
const slot = child(designCopy, 'slot_name');
if (slot.contents !== 'Carla') throw new Error('combo slot not replaced: ' + slot.contents);
if (slot.styleToken !== 'F10-style') throw new Error('combo slot did not inherit F10 style: ' + slot.styleToken);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_keeps_tail_glyphs_from_selected_font_style_source():
    tail_base = 0xE054
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "mock_font_tail": True,
        "mock_pua_tail_base": tail_base,
        "values": {"design": "03", "font": "F3", "name": "Carla"},
        "selections": {"Output_main": {"design": "Design03", "font": "F3"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F3",
                            "object_path": "Template/Output_main/Font/F10",
                            "source_only": True,
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "preset": "direct_text",
                            "tail_paths": [],
                            "tails": [],
                            "style_source": {
                                "group": "font",
                                "slot_key": "slot_name",
                                "paths_by_option": {"F3": "Template/Output_main/Font/F10/slot_name"},
                                "tails_by_option": {
                                    "F3": [
                                        {
                                            "key": "tail_name_last_m",
                                            "position": "last",
                                            "sample": "m",
                                                "glyph_mode": "pua_contiguous",
                                                "pua_base": tail_base,
                                            "path": "Template/Output_main/Font/F10/tail_name_last_m",
                                        }
                                    ]
                                },
                            },
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!designCopy) throw new Error('Design03 was not copied');
if (outputLayer.pageItems.find(item => item.name === 'F10')) throw new Error('source-only tail font copy was not removed');
const slot = child(designCopy, 'slot_name');
if (slot.contents !== 'Carl' + String.fromCharCode({tail_base})) throw new Error('font tail glyph was not carried to design: ' + slot.contents);
if (slot.styleToken !== 'F10-style') throw new Error('tail font style was not inherited: ' + slot.styleToken);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_removes_optional_blank_slot_inside_copied_group():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "year": ""},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_year",
                            "source_field": "year",
                            "required": False,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (!designCopy) throw new Error('Design03 was not copied');
if (designCopy.pageItems.find(item => item.name === 'slot_year')) throw new Error('optional blank slot was not removed');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_fits_short_and_long_text_inside_local_slot_bounds():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Alexandria-Catherine-Very-Long-Name"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
const height = slot.visibleBounds[1] - slot.visibleBounds[3];
if (width > 100.01) throw new Error('long text escaped local slot width: ' + width);
if (height > 30.01) throw new Error('long text escaped local slot height: ' + height);
if (slot.resizeCalls < 1) throw new Error('long text was not shrunk');
const centerX = (slot.visibleBounds[0] + slot.visibleBounds[2]) / 2;
const centerY = (slot.visibleBounds[1] + slot.visibleBounds[3]) / 2;
if (Math.abs(centerX - 50) > 0.1 || Math.abs(centerY - 15) > 0.1) throw new Error('text not centered in slot');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_short_text_fills_slot_bounds_and_centers():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Amy"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
if (slot.resizeCalls < 1) throw new Error('short text should resize to fill slot bounds');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
const height = slot.visibleBounds[1] - slot.visibleBounds[3];
if (Math.abs(width - 100) > 0.1 || Math.abs(height - 30) > 0.1) throw new Error('short text did not fill slot bounds: ' + width + 'x' + height);
const centerX = (slot.visibleBounds[0] + slot.visibleBounds[2]) / 2;
const centerY = (slot.visibleBounds[1] + slot.visibleBounds[3]) / 2;
if (Math.abs(centerX - 50) > 0.1 || Math.abs(centerY - 15) > 0.1) throw new Error('short text not centered');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_normal_text_fills_slot_bounds():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Normal"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
if (slot.resizeCalls < 1) throw new Error('normal text should resize to fill slot bounds');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
const height = slot.visibleBounds[1] - slot.visibleBounds[3];
if (Math.abs(width - 100) > 0.1 || Math.abs(height - 30) > 0.1) throw new Error('normal text did not fill slot bounds: ' + width + 'x' + height);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_uses_anchor_bounds_without_moving_fixed_art():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Anchored-Long-Name"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "anchor_path": "Template/Output_main/Design/Design03/anchor_name",
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const fixed = child(designCopy, 'fixed_heart');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
const height = slot.visibleBounds[1] - slot.visibleBounds[3];
if (width > 60.01) throw new Error('anchored text escaped anchor width: ' + width);
if (height > 20.01) throw new Error('anchored text escaped anchor height: ' + height);
const centerX = (slot.visibleBounds[0] + slot.visibleBounds[2]) / 2;
const centerY = (slot.visibleBounds[1] + slot.visibleBounds[3]) / 2;
if (Math.abs(centerX - 230) > 0.1 || Math.abs(centerY - 110) > 0.1) throw new Error('text not centered in anchor');
if (fixed.translateCalls !== 0 || fixed.resizeCalls !== 0) throw new Error('fixed art moved or resized');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_extreme_text_keeps_shrinking_without_touching_fixed_art():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "layout_warning_file": "warnings.json",
        "values": {"design": "03", "name": "X" * 160},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const fixed = child(designCopy, 'fixed_heart');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
if (width > 100.01) throw new Error('extreme text escaped slot width: ' + width);
if (slot.resizeCalls < 1) throw new Error('extreme text was not shrunk');
if (fixed.translateCalls !== 0 || fixed.resizeCalls !== 0) throw new Error('fixed art moved or resized for extreme text');
const warning = JSON.parse(writtenFiles['warnings.json']);
if (!warning.warnings || warning.warnings[0].code !== 'text_fit_extreme') throw new Error('extreme text warning missing');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_ignores_sub_tolerance_text_fit_rounding_warning():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "layout_warning_file": "warnings.json",
        "values": {"design": "03", "name": "ModeratelyLong"},
        "selections": {"Output_main": {"design": "Design03"}},
        "visible_bounds_padding_after_resize": {"slot_name": 0.004},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
if (width <= 100 || width >= 100.02) throw new Error('test did not create sub-tolerance rounding: ' + width);
const warning = JSON.parse(writtenFiles['warnings.json']);
if (warning.warnings.length) throw new Error('sub-tolerance text fit warning should be ignored');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_group_slot_fits_text_without_moving_slot_decoration():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "group_name": "Grouped-Slot-Long-Name"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_group",
                            "source_field": "group_name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slotGroup = child(designCopy, 'slot_group');
const text = child(slotGroup, 'slot_group_text');
const deco = child(slotGroup, 'slot_group_decoration');
if (text.resizeCalls < 1) throw new Error('group slot text was not fitted');
if (deco.translateCalls !== 0 || deco.resizeCalls !== 0) throw new Error('slot decoration moved or resized');
if (!slotGroup.pageItems.includes(deco)) throw new Error('slot decoration was removed');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_preserves_short_group_slot_text_with_keep_ratio_marker():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "group_name": "A"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_ratio_group",
                            "source_field": "group_name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slotGroup = child(designCopy, 'slot_ratio_group');
const text = child(slotGroup, 'slot_ratio_text');
const deco = child(slotGroup, 'keep_ratio_heart');
const marker = slotGroup.pageItems.find(item => item.name === 'keep_ratio');
const bounds = text.visibleBounds;
const width = bounds[2] - bounds[0];
const height = bounds[1] - bounds[3];
if (text.resizeCalls !== 0) throw new Error('decorated short slot text should keep template scale');
if (deco.translateCalls !== 0 || deco.resizeCalls !== 0) throw new Error('slot decoration moved or resized');
if (marker) throw new Error('pure keep_ratio marker should be removed from output');
if (width > 150.01 || height > 40.01) throw new Error('decorated text escaped group slot bounds: ' + width + 'x' + height);
const centerX = (bounds[0] + bounds[2]) / 2;
const centerY = (bounds[1] + bounds[3]) / 2;
if (Math.abs(centerX - 75) > 0.1 || Math.abs(centerY - 20) > 0.1) throw new Error('expanded text not centered in slot');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_preserves_path_text_geometry_while_fitting_content():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"font": "F10", "title": "Alexandria Catherine"},
        "selections": {"Output_main": {"font": "F10"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
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
                            "slot_key": "slot_title",
                            "object_path": "Template/Output_main/Font/F10/slot_title",
                            "source_field": "title",
                            "required": True,
                            "preset": "path_text",
                            "text_kind": "path_text",
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const fontCopy = outputLayer.pageItems.find(item => item.name === 'F10');
const slotTitle = child(fontCopy, 'slot_title');
if (slotTitle.contents !== 'Alexandria Catherine') throw new Error('path text was not replaced');
if (slotTitle.kind !== 'PATHTEXT') throw new Error('path text kind changed');
if (slotTitle.pathToken !== 'arc-main') throw new Error('path geometry token changed');
if (slotTitle.resizeCalls !== 0) throw new Error('path text object was resized');
if (slotTitle.translateCalls !== 0) throw new Error('path text object was translated');
if (slotTitle.textSize >= 18) throw new Error('path text size was not reduced');
const width = slotTitle.visibleBounds[2] - slotTitle.visibleBounds[0];
if (width > 100) throw new Error('path text exceeded original path bounds: ' + width);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def tail_text_task(tails, value="Alice Smith"):
    return {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": value},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "preset": "tail_text",
                            "tail_paths": [tail["path"] for tail in tails],
                            "tails": tails,
                        },
                    ],
                }
            ],
        },
    }


@pytest.mark.parametrize(
    ("tails", "expected_slot", "expected_first", "expected_last", "assert_tail_presence"),
    [
        (
            [
                {
                    "key": "tail_name_first_a",
                    "position": "first",
                    "sample": "a",
                    "pua_base": TAIL_PUA_BASE,
                    "path": "Template/Output_main/Design/Design03/tail_name_first_a",
                }
            ],
            "lice Smith",
            chr(TAIL_PUA_BASE),
            None,
            """
const firstTail = designCopy.pageItems.find(item => item.name === 'tail_name_first_a');
if (!firstTail || firstTail.contents !== expectedFirst) throw new Error('first tail mismatch');
""",
        ),
        (
            [
                {
                    "key": "tail_name_last_a",
                    "position": "last",
                    "sample": "a",
                    "pua_base": TAIL_PUA_BASE,
                    "path": "Template/Output_main/Design/Design03/tail_name_last_a",
                }
            ],
            "Alice Smit",
            None,
            chr(TAIL_PUA_BASE + 7),
            """
const lastTail = designCopy.pageItems.find(item => item.name === 'tail_name_last_a');
if (!lastTail || lastTail.contents !== expectedLast) throw new Error('last tail mismatch');
""",
        ),
        (
            [
                {
                    "key": "tail_name_first_a",
                    "position": "first",
                    "sample": "a",
                    "pua_base": TAIL_PUA_BASE,
                    "path": "Template/Output_main/Design/Design03/tail_name_first_a",
                },
                {
                    "key": "tail_name_last_a",
                    "position": "last",
                    "sample": "a",
                    "pua_base": TAIL_PUA_BASE,
                    "path": "Template/Output_main/Design/Design03/tail_name_last_a",
                },
            ],
            "lice Smit",
            chr(TAIL_PUA_BASE),
            chr(TAIL_PUA_BASE + 7),
            """
const firstTail = designCopy.pageItems.find(item => item.name === 'tail_name_first_a');
const lastTail = designCopy.pageItems.find(item => item.name === 'tail_name_last_a');
if (!firstTail || firstTail.contents !== expectedFirst) throw new Error('first tail mismatch');
if (!lastTail || lastTail.contents !== expectedLast) throw new Error('last tail mismatch');
""",
        ),
    ],
)
def test_v2_renderer_applies_tail_text_to_whole_content_endpoints(tails, expected_slot, expected_first, expected_last, assert_tail_presence):
    harness = node_mock_harness(tail_text_task(tails), f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (child(designCopy, 'slot_name').contents !== {json.dumps(expected_slot)}) throw new Error('tail main text mismatch: ' + child(designCopy, 'slot_name').contents);
const expectedFirst = {json.dumps(expected_first)};
const expectedLast = {json.dumps(expected_last)};
{assert_tail_presence}
if (child(designCopy, 'slot_name').contents.indexOf('S') < 0) throw new Error('middle word was incorrectly treated as endpoint');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("fit_mode", ["fill_width", "fill_height"])
def test_v2_renderer_tail_text_preserves_composition_before_single_axis_fit(fit_mode):
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "pua_base": TAIL_PUA_BASE,
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        }
    ]
    task = tail_text_task(tails, value="Alice Smith")
    action = task["render_task"]["outputs"][0]["actions"][1]
    action["preserve_composition"] = True
    action["fit_mode"] = fit_mode
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
if (slot.resizeCalls !== 0) throw new Error('preserved tail text should not stretch short main text');
if (width >= 99.9) throw new Error('preserved tail text unexpectedly filled full slot width: ' + width);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_rejects_unverified_direct_text_tail_samples():
    tails = [
        {
            "key": "tail_name_first_m",
            "position": "first",
            "sample": "m",
            "glyph_mode": "plain_text",
            "path": "Template/Output_main/Design/Design03/tail_name_first_m",
        },
        {
            "key": "tail_name_last_a",
            "position": "last",
            "sample": "a",
            "glyph_mode": "plain_text",
            "path": "Template/Output_main/Design/Design03/tail_name_last_a",
        }
    ]
    task = tail_text_task(tails, value="Custom")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    task["mock_first_tail_sample"] = "__m"
    task["mock_last_tail_sample"] = "a__"
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "tail glyph coverage is missing" in result.stderr


def test_v2_renderer_fills_only_requested_axis_and_centers_slot_content():
    task = tail_text_task([], value="Custom")
    action = task["render_task"]["outputs"][0]["actions"][1]
    action["preset"] = "direct_text"
    action["anchor_path"] = "Template/Output_main/Design/Design03/anchor_name"
    action["fit_mode"] = "fill_width"
    task["mock_anchor_name_bounds"] = [200, 140, 260, 100]
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const bounds = slot.visibleBounds;
const width = bounds[2] - bounds[0];
const height = bounds[1] - bounds[3];
if (Math.abs(width - 60) > 0.01 || Math.abs(height - 30) > 0.01) {
  throw new Error('width-only fit did not preserve the non-overflowing height: ' + JSON.stringify(bounds));
}
if (Math.abs((bounds[0] + bounds[2]) / 2 - 230) > 0.01 || Math.abs((bounds[1] + bounds[3]) / 2 - 120) > 0.01) {
  throw new Error('width-only fit did not center content: ' + JSON.stringify(bounds));
}
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("fit_mode", "value", "anchor_bounds", "expected_width", "expected_height", "expected_center"),
    [
        ("fill_width", "Custom", [200, 150, 400, 100], 100, 50, (300, 125)),
        # The long value is deliberately wider than the 50pt slot. Height
        # fill first reaches 200pt, then cross-axis overflow scales both axes
        # down together rather than distorting the requested fit.
        ("fill_height", "CustomCustomCustomCustom", [200, 300, 250, 100], 50, 52.0833, (225, 200)),
    ],
)
def test_v2_renderer_single_axis_fit_shrinks_proportionally_on_cross_axis_overflow(
    fit_mode, value, anchor_bounds, expected_width, expected_height, expected_center
):
    task = tail_text_task([], value=value)
    action = task["render_task"]["outputs"][0]["actions"][1]
    action["preset"] = "direct_text"
    action["anchor_path"] = "Template/Output_main/Design/Design03/anchor_name"
    action["fit_mode"] = fit_mode
    task["mock_anchor_name_bounds"] = anchor_bounds
    task["mock_design_slot_bounds"] = [0, 100, 100, 0]
    harness = node_mock_harness(task, f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const slot = child(designCopy, 'slot_name');
const bounds = slot.visibleBounds;
const width = bounds[2] - bounds[0];
const height = bounds[1] - bounds[3];
if (Math.abs(width - {expected_width}) > 0.01 || Math.abs(height - {expected_height}) > 0.01) {{
  throw new Error('single-axis overflow was not proportionally reduced: ' + JSON.stringify(bounds));
}}
if (Math.abs((bounds[0] + bounds[2]) / 2 - {expected_center[0]}) > 0.01 || Math.abs((bounds[1] + bounds[3]) / 2 - {expected_center[1]}) > 0.01) {{
  throw new Error('single-axis overflow result was not centered: ' + JSON.stringify(bounds));
}}
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_rejects_unverified_plain_tail_even_when_a_probe_candidate_exists():
    tails = [
        {
            "key": "tail_name_last_m",
            "position": "last",
            "sample": "m",
            "glyph_mode": "plain_text",
            "path": "Template/Output_main/Design/Design03/tail_name_last_m",
        }
    ]
    task = tail_text_task(tails, value="Mastka")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    task["mock_pua_tail_base"] = 0xE054
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "tail glyph coverage is missing" in result.stderr


def test_v2_renderer_bounds_plain_tail_pua_probe_candidates():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "knownTailPuaBases" in source
    assert "for (var candidate = 0xE000; candidate <= 0xF8FF - 25; candidate++)" not in source
    assert "puaTailGlyph" in source
    assert "missingCount === 0" in source


def test_v2_renderer_rejects_plain_tail_pua_when_alphabet_is_incomplete():
    tails = [
        {
            "key": "tail_name_last_m",
            "position": "last",
            "sample": "m",
            "glyph_mode": "plain_text",
            "path": "Template/Output_main/Design/Design03/tail_name_last_m",
        }
    ]
    task = tail_text_task(tails, value="Mastka")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    task["mock_pua_tail_base"] = 0xE054
    task["mock_pua_incomplete_base"] = 0xE054
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "tail glyph coverage is missing" in result.stderr


def test_v2_renderer_blocks_when_the_requested_plain_tail_pua_is_missing():
    tails = [
        {
            "key": "tail_name_last_m",
            "position": "last",
            "sample": "m",
            "glyph_mode": "plain_text",
            "path": "Template/Output_main/Design/Design03/tail_name_last_m",
        }
    ]
    task = tail_text_task(tails, value="Mastkf")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    task["mock_pua_tail_base"] = 0xE054
    task["mock_pua_missing_base"] = 0xE054
    task["mock_pua_missing_index"] = 5
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "tail glyph coverage is missing" in result.stderr


def test_v2_renderer_applies_verified_pua_tail_to_split_part_only():
    tails = [
        {
            "key": "tail_year_tail_last_a",
            "position": "last",
            "sample": "a",
            "glyph_mode": "pua_contiguous",
            "pua_base": TAIL_PUA_BASE,
            "path": "Template/Output_main/Design/Design03/tail_year_tail_last_a",
        }
    ]
    task = tail_text_task(tails)
    task["values"] = {"design": "03", "year": "Left|Omega"}
    action = task["render_task"]["outputs"][0]["actions"][1]
    action.update(
        {
            "slot_key": "slot_year_tail",
            "object_path": "Template/Output_main/Design/Design03/slot_year_tail",
            "source_field": "year",
            "source_part_index": 1,
            "preset": "split_by_pipe",
            "tail_paths": [tail["path"] for tail in tails],
            "tails": tails,
        }
    )
    harness = node_mock_harness(task, f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (child(designCopy, 'slot_year_tail').contents !== 'Omeg') throw new Error('plain split main mismatch: ' + child(designCopy, 'slot_year_tail').contents);
if (child(designCopy, 'tail_year_tail_last_a').contents !== String.fromCharCode({TAIL_PUA_BASE})) throw new Error('PUA split tail mismatch: ' + child(designCopy, 'tail_year_tail_last_a').contents);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_rejects_tail_text_without_latin_endpoint():
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "pua_base": TAIL_PUA_BASE,
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        }
    ]
    harness = node_mock_harness(tail_text_task(tails, value="12345"), "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "V2 tail text requires latin endpoints" in result.stderr


def test_v2_renderer_rejects_tail_text_without_glyph_coverage():
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        }
    ]
    harness = node_mock_harness(tail_text_task(tails, value="Alice"), "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "V2 tail glyph coverage is missing" in result.stderr


def test_v2_renderer_uses_tail_glyph_map_when_provided():
    glyph_map = {chr(ord("a") + index): 0xE200 + index for index in range(26)}
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "glyph_map": glyph_map,
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        }
    ]
    harness = node_mock_harness(tail_text_task(tails, value="Zelda"), f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const firstTail = designCopy.pageItems.find(item => item.name === 'tail_name_first_a');
if (!firstTail || firstTail.contents !== {json.dumps(chr(0xE219))}) throw new Error('glyph map tail mismatch');
if (child(designCopy, 'slot_name').contents !== 'elda') throw new Error('main tail removal mismatch');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_embeds_materialized_opentype_tail_glyphs_for_direct_text():
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "glyph_mode": "opentype_alternate",
            "opentype_glyph_asset": {"path": "first-a.svg"},
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        },
        {
            "key": "tail_name_last_a",
            "position": "last",
            "sample": "a",
            "glyph_mode": "opentype_alternate",
            "opentype_glyph_asset": {"path": "last-a.svg"},
            "path": "Template/Output_main/Design/Design03/tail_name_last_a",
        },
    ]
    task = tail_text_task(tails, value="Alice")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    harness = node_mock_harness(task, f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (designCopy.pageItems.find(item => item.name === 'slot_name')) throw new Error('OpenType composition retained editable normal endpoint text');
if (designCopy.pageItems.find(item => item.name === 'tail_name_first_a' || item.name === 'tail_name_last_a')) throw new Error('OpenType helper sample remained in output');
if (!designCopy.pageItems.find(item => item.name === 'TAIL_VECTOR_tail_name_first_a' && item.typename === 'PathItem')) throw new Error('OpenType first glyph was not inserted');
if (!designCopy.pageItems.find(item => item.name === 'TAIL_VECTOR_tail_name_last_a' && item.typename === 'PathItem')) throw new Error('OpenType last glyph was not inserted');
const embedded = designCopy.pageItems.filter(item => item.typename === 'PathItem' && /^TAIL_VECTOR_/.test(item.name));
if (embedded.length !== 2) throw new Error('OpenType glyph SVGs were not embedded');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_composes_mixed_opentype_and_pua_tail_vectors_for_one_slot():
    tails = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "glyph_mode": "opentype_alternate",
            "tail_vector_asset": {"path": "first-a.svg"},
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        },
        {
            "key": "tail_name_last_a",
            "position": "last",
            "sample": "a",
            "glyph_mode": "pua_contiguous",
            "pua_base": TAIL_PUA_BASE,
            "tail_vector_asset": {"path": "last-e.svg"},
            "path": "Template/Output_main/Design/Design03/tail_name_last_a",
        },
    ]
    task = tail_text_task(tails, value="Alice")
    task["render_task"]["outputs"][0]["actions"][1]["preset"] = "direct_text"
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (designCopy.pageItems.find(item => item.name === 'slot_name')) throw new Error('mixed composition retained editable endpoint text');
for (const key of ['tail_name_first_a', 'tail_name_last_a']) {
  if (!designCopy.pageItems.find(item => item.name === 'TAIL_VECTOR_' + key && item.typename === 'PathItem')) {
    throw new Error('mixed vector tail was not inserted: ' + key);
  }
}
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_tail_text_slots_do_not_delete_other_slot_tail_samples():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Alice", "year": "YearZ"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "preset": "tail_text",
                            "tail_paths": ["Template/Output_main/Design/Design03/tail_name_first_a"],
                            "tails": [
                                {
                                    "key": "tail_name_first_a",
                                    "position": "first",
                                    "sample": "a",
                                    "pua_base": TAIL_PUA_BASE,
                                    "path": "Template/Output_main/Design/Design03/tail_name_first_a",
                                }
                            ],
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "design",
                            "option_key": "Design03",
                            "slot_key": "slot_year_tail",
                            "object_path": "Template/Output_main/Design/Design03/slot_year_tail",
                            "source_field": "year",
                            "required": True,
                            "preset": "tail_text",
                            "tail_paths": ["Template/Output_main/Design/Design03/tail_year_tail_last_a"],
                            "tails": [
                                {
                                    "key": "tail_year_tail_last_a",
                                    "position": "last",
                                    "sample": "a",
                                    "pua_base": TAIL_PUA_BASE,
                                    "path": "Template/Output_main/Design/Design03/tail_year_tail_last_a",
                                }
                            ],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, f"""
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const nameTail = designCopy.pageItems.find(item => item.name === 'tail_name_first_a');
const yearTail = designCopy.pageItems.find(item => item.name === 'tail_year_tail_last_a');
if (!nameTail || nameTail.contents !== {json.dumps(chr(TAIL_PUA_BASE))}) throw new Error('name first tail missing');
if (!yearTail || yearTail.contents !== {json.dumps(chr(TAIL_PUA_BASE + 25))}) throw new Error('year last tail was removed by another slot');
if (child(designCopy, 'slot_name').contents !== 'lice') throw new Error('name main mismatch');
if (child(designCopy, 'slot_year_tail').contents !== 'Year') throw new Error('year main mismatch');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_fits_final_output_bounds_and_removes_auxiliary_items():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "style": "small", "name": "Amy"},
        "selections": {"Output_main": {"design": "Design03", "style": "style1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
if (designCopy.pageItems.find(item => item.name === 'anchor_name')) throw new Error('anchor auxiliary was not removed');
const width = designCopy.visibleBounds[2] - designCopy.visibleBounds[0];
const height = designCopy.visibleBounds[1] - designCopy.visibleBounds[3];
if (Math.abs(width - 100) > 0.04) throw new Error('final width mismatch: ' + width);
if (Math.abs(height - 30) > 0.04) throw new Error('final height mismatch: ' + height);
if (width > 100 || height > 30) throw new Error('final output exceeded target');
if (designCopy.resizeCalls < 1) throw new Error('final output was not resized');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_fits_final_output_bounds_from_selected_design_without_style():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "name": "Amy"},
        "selections": {"Output_main": {"design": "Design03"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
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
                            "object_path": "Template/Output_main/Design/Design03/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "design",
                            "option_key": "Design03",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const designCopy = outputLayer.pageItems.find(item => item.name === 'Design03');
const width = designCopy.visibleBounds[2] - designCopy.visibleBounds[0];
const height = designCopy.visibleBounds[1] - designCopy.visibleBounds[3];
if (Math.abs(width - 100) > 0.04) throw new Error('design final width mismatch: ' + width);
if (Math.abs(height - 30) > 0.04) throw new Error('design final height mismatch: ' + height);
if (designCopy.resizeCalls < 1) throw new Error('design final output was not resized');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_copies_selected_style_option():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"style": "small"},
        "selections": {"Output_main": {"style": "style1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                        },
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style2",
                            "object_path": "Template/Output_main/Style/style2",
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const copiedNames = outputLayer.pageItems.map(item => item.name);
if (!copiedNames.includes('style1')) throw new Error('selected style was not copied');
if (copiedNames.includes('style2')) throw new Error('unselected style was copied');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_uses_source_only_style_as_bounds_without_outputting_frame():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"style": "small", "font": "F1", "name": "Amy"},
        "selections": {"Output_main": {"style": "style1", "font": "F1"}},
        "mock_style1_bounds": [200, 100, 300, 0],
        "mock_f1_slot_bounds": [0, 30, 30, 0],
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                            "source_only": True,
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const copiedNames = outputLayer.pageItems.map(item => item.name);
if (copiedNames.includes('style1')) throw new Error('source-only style frame remained in output');
const fontCopy = outputLayer.pageItems.find(item => item.name === 'F1');
if (!fontCopy) throw new Error('font output was not copied');
const slot = child(fontCopy, 'slot_name');
const textBounds = slot.visibleBounds;
if (textBounds[0] < 200 - 0.05 || textBounds[2] > 300 + 0.05) throw new Error('font text escaped source-only style width');
if (textBounds[1] > 100 + 0.05 || textBounds[3] < 0 - 0.05) throw new Error('font text escaped source-only style height');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_scales_style_and_font_as_one_final_output():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"style": "small", "font": "F1", "name": "Amy"},
        "selections": {"Output_main": {"style": "style1", "font": "F1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const bounds = union(outputLayer.pageItems.map(item => item.visibleBounds));
const width = bounds[2] - bounds[0];
const height = bounds[1] - bounds[3];
if (width > 100 || height > 30) throw new Error('final output exceeded target: ' + width + 'x' + height);
if (height < 29.96) throw new Error('font and style were not scaled as one output: ' + height);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_pack_order_blocks_groups_rendered_items_without_menu_command():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "pack_order_blocks": True,
        "values": {"style": "small", "font": "F1", "name": "Amy"},
        "selections": {"Output_main": {"style": "style1", "font": "F1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
if (outputLayer.pageItems.length !== 1) throw new Error('rendered items were not grouped');
const block = outputLayer.pageItems[0];
if (block.name !== 'ORDER_PACK_BLOCK_0') throw new Error('order block was not named');
const childNames = block.pageItems.map(item => item.name);
if (!childNames.includes('style1')) throw new Error('style was not moved into order block');
if (!childNames.includes('F1')) throw new Error('font was not moved into order block');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["copied"] == ["ORDER_PACK_BLOCK_0"]


def test_v2_renderer_pack_order_blocks_cleans_partial_dom_group_before_fallback():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "pack_order_blocks": True,
        "fail_dom_move_once": ["F1"],
        "values": {"style": "small", "font": "F1", "name": "Amy"},
        "selections": {"Output_main": {"style": "style1", "font": "F1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
if (outputLayer.pageItems.length !== 1) throw new Error('partial group was not cleaned');
const block = outputLayer.pageItems[0];
if (block.name !== 'ORDER_PACK_BLOCK_0') throw new Error('fallback order block was not named');
const childNames = block.pageItems.map(item => item.name);
if (!childNames.includes('style1')) throw new Error('style was lost during fallback');
if (!childNames.includes('F1')) throw new Error('font was lost during fallback');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["copied"] == ["ORDER_PACK_BLOCK_0"]


def test_v2_renderer_places_standalone_font_text_inside_selected_style_bounds():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"style": "small", "font": "F1", "name": "Amy"},
        "selections": {"Output_main": {"style": "style1", "font": "F1"}},
        "mock_style1_bounds": [200, 100, 300, 0],
        "mock_f1_slot_bounds": [0, 30, 30, 0],
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "select_style",
                            "group": "style",
                            "option_key": "style1",
                            "object_path": "Template/Output_main/Style/style1",
                        },
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "replace_slot_text",
                            "group": "font",
                            "option_key": "F1",
                            "slot_key": "slot_name",
                            "object_path": "Template/Output_main/Font/F1/slot_name",
                            "source_field": "name",
                            "required": True,
                            "tail_paths": [],
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, """
const styleCopy = outputLayer.pageItems.find(item => item.name === 'style1');
const fontCopy = outputLayer.pageItems.find(item => item.name === 'F1');
const slot = child(fontCopy, 'slot_name');
const styleBounds = styleCopy.visibleBounds;
const textBounds = slot.visibleBounds;
const styleWidth = styleBounds[2] - styleBounds[0];
const styleHeight = styleBounds[1] - styleBounds[3];
const textWidth = textBounds[2] - textBounds[0];
const textHeight = textBounds[1] - textBounds[3];
if (textBounds[0] < styleBounds[0] - 0.05 || textBounds[2] > styleBounds[2] + 0.05) throw new Error('font text escaped selected style width');
if (textBounds[1] > styleBounds[1] + 0.05 || textBounds[3] < styleBounds[3] - 0.05) throw new Error('font text escaped selected style height');
if (textWidth < styleWidth - 0.08) throw new Error('font text did not fill selected style width: ' + textWidth + ' vs ' + styleWidth);
if (textHeight < styleHeight - 0.08) throw new Error('font text did not fill selected style height: ' + textHeight + ' vs ' + styleHeight);
if (slot.contents !== 'Amy') throw new Error('font slot not replaced: ' + slot.contents);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_blocks_unmeasurable_final_output():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"style": "small"},
        "selections": {"Output_main": {"style": "style1"}},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        }
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "V2 output has no rendered items" in result.stderr


def test_v2_renderer_rejects_final_output_when_visible_bounds_fail():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "style": "small"},
        "selections": {"Output_main": {"design": "Design03", "style": "style1"}},
        "visible_bounds_failures": ["Design03"],
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "Cannot measure V2 output visible bounds" in result.stderr


def test_v2_renderer_rejects_final_output_that_exceeds_target():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "style": "small"},
        "selections": {"Output_main": {"design": "Design03", "style": "style1"}},
        "visible_bounds_padding_after_resize": {"Design03": 60},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {"width_mm": 35.2777777778, "height_mm": 10.5833333333},
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode != 0
    assert "V2 output exceeds target bounds" in result.stderr


def test_v2_renderer_allows_sub_tolerance_final_output_rounding():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"design": "03", "style": "small"},
        "selections": {"Output_main": {"design": "Design03", "style": "style1"}},
        # -0.01pt is an inner rounding delta within the contractual 0.007mm
        # (about 0.0198pt), but exceeds the former 0.0005mm threshold.
        "visible_bounds_padding_after_resize": {"Design03": -0.01},
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "design",
                            "option_key": "Design03",
                            "object_path": "Template/Output_main/Design/Design03",
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {
                                "width_mm": 35.2777777778,
                                "height_mm": 10.5833333333,
                                "tolerance_mm": 0.007,
                            },
                        },
                    ],
                }
            ],
        },
    }
    harness = node_mock_harness(task, "")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_rejects_sub_tolerance_final_output_overflow():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"font": "F1", "style": "small"},
        "selections": {"Output_main": {"font": "F1", "style": "style1"}},
        # 0.01pt is about 0.0035mm: within the tolerance magnitude but outside
        # the target frame, so it must never be accepted as a final result.
        "mock_f1_slot_bounds": [0, 30, 100.01, 0],
        "mock_no_resize_names": ["F1"],
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {
                                "width_mm": 35.2777777778,
                                "height_mm": 10.5833333333,
                                "tolerance_mm": 0.007,
                            },
                        },
                    ],
                }
            ],
        },
    }

    result = run_node(node_mock_harness(task, ""))

    assert result.returncode != 0
    assert "V2 output exceeds target bounds" in result.stderr


def test_v2_renderer_fits_sub_threshold_visible_bounds_overflow_inside_target():
    task = {
        "$schema": "custom-renderer/v2-render-execution",
        "template_ai": "template.ai",
        "output_ai": "out.ai",
        "values": {"font": "F1", "style": "small"},
        "selections": {"Output_main": {"font": "F1", "style": "style1"}},
        # A 0.0006pt output overflow is smaller than the old 0.001% convergence
        # threshold. The final fit must still run and leave the result inside the
        # requested frame, rather than rejecting an Illustrator grid-rounding step.
        "mock_f1_slot_bounds": [0, 30.0006, 100.0006, 0],
        "render_task": {
            "$schema": "custom-renderer/v2-render-task",
            "outputs": [
                {
                    "key": "Output_main",
                    "actions": [
                        {
                            "type": "copy_option_group",
                            "group": "font",
                            "option_key": "F1",
                            "object_path": "Template/Output_main/Font/F1",
                        },
                        {
                            "type": "fit_output_bounds",
                            "group": "style",
                            "style_key": "style1",
                            "dimensions": {
                                "width_mm": 35.2777777778,
                                "height_mm": 10.5833333333,
                                "tolerance_mm": 0.007,
                            },
                        },
                    ],
                }
            ],
        },
    }

    result = run_node(node_mock_harness(task, ""))

    assert result.returncode == 0, result.stderr


def node_mock_harness(task, assertions, disable_native_json=False):
    return f"""
const fs = require('fs');
const source = {jsx_source_expression()};
const NativeJSON = JSON;
const task = {json.dumps(task)};
const taskText = NativeJSON.stringify(task);
const visibleBoundsFailures = new Set(task.visible_bounds_failures || []);
const visibleBoundsPaddingAfterResize = task.visible_bounds_padding_after_resize || {{}};
const noResizeNames = new Set(task.mock_no_resize_names || []);
let domMoveFailures = new Set(task.fail_dom_move_once || []);
const folder = {{ exists: true, parent: null, create: () => true }};
let savedAs = '';
let savedArtboard = null;
let exportedAs = '';
let exportOptions = null;
const writtenFiles = {{}};
global.$ = {{ getenv: () => 'task.json' }};
global.File = function(path) {{
  return {{
    fsName: path,
    exists: path === 'task.json' || /\.svg$/i.test(path),
    parent: folder,
    open: () => true,
    read: () => taskText,
    write: text => {{ writtenFiles[path] = (writtenFiles[path] || '') + String(text); }},
    close: () => undefined,
    remove: () => undefined
  }};
}};
global.UserInteractionLevel = {{ DONTDISPLAYALERTS: 0 }};
global.DocumentColorSpace = {{ RGB: 1 }};
global.ElementPlacement = {{ PLACEATEND: 1, PLACEBEFORE: 2 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
global.Compatibility = {{ ILLUSTRATOR8: 8 }};
global.IllustratorSaveOptions = function() {{}};
global.ExportOptionsPNG24 = function() {{}};
global.ExportType = {{ PNG24: 24 }};
global.Transformation = {{ CENTER: 0 }};
global.RGBColor = function() {{ this.red = 0; this.green = 0; this.blue = 0; }};
function item(typename, name, contents, children, styleToken, bounds, options) {{
  let text = contents || '';
  const characterColors = {{}};
  const opts = options || {{}};
  let textSize = Number(opts.textSize || 18);
  let box = (bounds || defaultBounds(typename, name, text)).slice();
  const baseBox = box.slice();
  const node = {{
    typename,
    name,
    kind: opts.kind || '',
    pathToken: opts.pathToken || '',
    puaTailBase: opts.puaTailBase || 0,
    outlineToken: opts.outlineToken || '',
    styleToken: styleToken || '',
    pageItems: children || [],
    translateCalls: 0,
    resizeCalls: 0,
    duplicate: function(targetLayer) {{
      const copy = clone(this);
      attach(targetLayer || this.parent, copy);
      return copy;
    }},
    createOutline: function() {{
      if (typename === 'TextFrame' && Object.keys(characterColors).length) {{
        const glyphs = text.split('').map((character, index) => {{
          const width = Math.max(1, (box[2] - box[0]) / Math.max(text.length, 1));
          const glyph = item('PathItem', '', '', [], '', [box[0] + width * index, box[1], box[0] + width * (index + 1), box[3]]);
          glyph.fillColor = characterColors[index] || {{ red: 0, green: 0, blue: 0 }};
          return glyph;
        }});
        const outlined = item('GroupItem', '', '', glyphs, '', this.visibleBounds);
        const parent = this.parent;
        this.remove();
        if (parent) attach(parent, outlined);
        return outlined;
      }}
      const code = text.length === 1 ? text.charCodeAt(0) : 0;
      const matchesTailSample = opts.puaTailBase && (text === 'm' || code === Number(opts.puaTailBase) + 12);
      const token = matchesTailSample ? 'tail-sample-m' : ('glyph-' + code);
      let points;
      if (token === 'tail-sample-m') {{
        points = [[0, 0], [1, 0], [1, 1], [0, 1]];
      }} else {{
        const puaIndex = opts.puaTailBase ? code - Number(opts.puaTailBase) : -1;
        const geometryCode = task.mock_pua_missing_base === Number(opts.puaTailBase)
            && puaIndex === Number(task.mock_pua_missing_index)
          ? 0xF8FF
          : (task.mock_pua_incomplete_base === Number(opts.puaTailBase) && puaIndex === 1
            ? code - 1
            : code);
        points = [];
        for (let pointIndex = 0; pointIndex < 4 + (geometryCode % 26); pointIndex++) {{
          points.push([pointIndex / (3 + (geometryCode % 26)), pointIndex % 2]);
        }}
      }}
      const path = item('PathItem', '', '', [], '', this.visibleBounds, {{ pathPoints: points, closed: true }});
      const outlined = item('GroupItem', '', '', [path], '', this.visibleBounds);
      const parent = this.parent;
      this.remove();
      if (parent) attach(parent, outlined);
      return outlined;
    }},
    remove: function() {{
      if (!this.parent || !this.parent.pageItems) return;
      const index = this.parent.pageItems.indexOf(this);
      if (index >= 0) this.parent.pageItems.splice(index, 1);
    }},
    move: function(target, placement) {{
      const targetName = String(target && target.name || '');
      if (targetName.indexOf('ORDER_PACK_BLOCK_') === 0 && domMoveFailures.has(this.name)) {{
        domMoveFailures.delete(this.name);
        throw new Error('dom move failed: ' + this.name);
      }}
      this.remove();
      attach(placement === ElementPlacement.PLACEBEFORE && target && target.parent ? target.parent : target, this);
    }},
    translate: function(dx, dy) {{
      this.translateCalls++;
      if (this.pageItems.length) {{
        for (const childNode of this.pageItems) childNode.translate(dx, dy);
        return;
      }}
      box = [box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy];
    }},
    resize: function(horizontalPercent, verticalPercent) {{
      this.resizeCalls++;
      if (noResizeNames.has(this.name)) return;
      if (this.pageItems.length) {{
        const bounds = this.visibleBounds;
        const cx = (bounds[0] + bounds[2]) / 2;
        const cy = (bounds[1] + bounds[3]) / 2;
        for (const childNode of this.pageItems) scaleNode(childNode, cx, cy, horizontalPercent / 100, verticalPercent / 100);
        return;
      }}
      const cx = (box[0] + box[2]) / 2;
      const cy = (box[1] + box[3]) / 2;
      const width = (box[2] - box[0]) * horizontalPercent / 100;
      const height = (box[1] - box[3]) * verticalPercent / 100;
      box = [cx - width / 2, cy + height / 2, cx + width / 2, cy - height / 2];
    }}
  }};
  Object.defineProperty(node, 'contents', {{
    get: () => text,
    set: value => {{
      text = String(value || '');
      if (typename === 'TextFrame') {{
        const left = box[0];
        const top = box[1];
        const height = Math.max(8, box[1] - box[3]);
        const width = opts.kind === 'PATHTEXT' ? Math.max(10, text.length * textSize * 0.45) : Math.max(10, text.length * 8);
        box = [left, top, left + width, top - height];
      }}
    }}
  }});
  Object.defineProperty(node, 'textSize', {{ get: () => textSize }});
  node.textRange = {{
    characterAttributes: {{}}
  }};
  node.textRange.characterAttributes.fillColor = {{ red: 0, green: 0, blue: 0 }};
  node.textRange.characterAttributes.strokeColor = {{ red: 0, green: 0, blue: 0 }};
  node.textRange.characterAttributes.strokeWeight = 0;
  Object.defineProperty(node.textRange, 'characters', {{
    get: () => text.split('').map((character, index) => {{
      const attributes = {{}};
      Object.defineProperty(attributes, 'fillColor', {{
        get: () => characterColors[index] || node.textRange.characterAttributes.fillColor,
        set: value => {{ characterColors[index] = value; }}
      }});
      return {{ characterAttributes: attributes }};
    }})
  }});
  Object.defineProperty(node.textRange.characterAttributes, 'size', {{
    get: () => textSize,
    set: value => {{
      const next = Number(value);
      if (!Number.isFinite(next) || next <= 0) return;
      const ratio = next / textSize;
      textSize = next;
      if (typename === 'TextFrame') {{
        if (opts.kind === 'PATHTEXT') {{
          const left = box[0];
          const top = box[1];
          const width = Math.max(10, text.length * textSize * 0.45);
          box = [left, top, left + width, baseBox[3]];
        }} else {{
          const cx = (box[0] + box[2]) / 2;
          const cy = (box[1] + box[3]) / 2;
          const width = (box[2] - box[0]) * ratio;
          const height = (box[1] - box[3]) * ratio;
          box = [cx - width / 2, cy + height / 2, cx + width / 2, cy - height / 2];
        }}
      }}
    }}
  }});
  Object.defineProperty(node, 'visibleBounds', {{
    get: () => {{
      if (node.fromCopy && visibleBoundsFailures.has(node.name)) throw new Error('visible bounds unavailable: ' + node.name);
      const code = text.length === 1 ? text.charCodeAt(0) : 0;
      if (opts.puaTailBase) {{
        if (text === 'm' || code === Number(opts.puaTailBase) + 12) return [box[0], box[1], box[0] + 40, box[3]];
        if (code >= 0xE000 && code <= 0xF8FF) return [box[0], box[1], box[0] + 10, box[3]];
      }}
      const bounds = node.pageItems.length ? union(node.pageItems.map(item => item.visibleBounds)) : box.slice();
      const resizePadding = node.fromCopy && node.resizeCalls > 0 ? Number(visibleBoundsPaddingAfterResize[node.name] || 0) : 0;
      const padding = resizePadding;
      return padding ? [bounds[0] - padding, bounds[1] + padding, bounds[2] + padding, bounds[3] - padding] : bounds;
    }},
    set: value => {{ box = value.slice(); }}
  }});
  Object.defineProperty(node, 'geometricBounds', {{ get: () => box.slice() }});
  node.closed = opts.closed === true;
  node.pathPoints = (opts.pathPoints || []).map(point => {{
    const anchor = [box[0] + Number(point[0]) * (box[2] - box[0]), box[3] + Number(point[1]) * (box[1] - box[3])];
    return {{ anchor, leftDirection: anchor.slice(), rightDirection: anchor.slice() }};
  }});
  for (const childNode of node.pageItems) childNode.parent = node;
  return node;
}}
function defaultBounds(typename, name, contents) {{
  if (name === 'anchor_name') return task.mock_anchor_name_bounds || [200, 120, 260, 100];
  if (typename === 'TextFrame' && name === 'slot_name') return task.mock_design_slot_bounds || [0, 30, 100, 0];
  if (typename === 'TextFrame') return [0, 20, Math.max(10, String(contents || '').length * 8), 0];
  if (typename === 'PathItem') return [130, 40, 150, 20];
  return [0, 100, 100, 0];
}}
function union(boundsList) {{
  return boundsList.reduce((result, bounds) => [
    Math.min(result[0], bounds[0]),
    Math.max(result[1], bounds[1]),
    Math.max(result[2], bounds[2]),
    Math.min(result[3], bounds[3])
  ]);
}}
function scaleNode(node, cx, cy, sx, sy) {{
  const bounds = node.visibleBounds;
  const childCx = (bounds[0] + bounds[2]) / 2;
  const childCy = (bounds[1] + bounds[3]) / 2;
  const targetCx = cx + (childCx - cx) * sx;
  const targetCy = cy + (childCy - cy) * sy;
  node.resize(sx * 100, sy * 100);
  const resized = node.visibleBounds;
  const resizedCx = (resized[0] + resized[2]) / 2;
  const resizedCy = (resized[1] + resized[3]) / 2;
  node.translate(targetCx - resizedCx, targetCy - resizedCy);
}}
function clone(node) {{
  const copy = item(node.typename, node.name, node.contents, node.pageItems.map(clone), node.styleToken, node.visibleBounds, {{
    kind: node.kind,
    pathToken: node.pathToken,
    textSize: node.textSize,
    puaTailBase: node.puaTailBase
  }});
  copy.fromCopy = true;
  return copy;
}}
function attach(parent, childNode) {{
  childNode.parent = parent;
  parent.pageItems.push(childNode);
}}
function child(parent, name) {{
  const found = parent.pageItems.find(item => item.name === name);
  if (!found) throw new Error('missing child: ' + name);
  return found;
}}
const f1SlotBounds = task.mock_f1_slot_bounds || undefined;
const style1Bounds = task.mock_style1_bounds || [0, 100, 100, 0];
const f1 = item('GroupItem', 'F1', '', [item('TextFrame', 'slot_name', 'F1 sample', [], 'F1-style', f1SlotBounds)]);
const f10 = item('GroupItem', 'F10', '', [
  item('TextFrame', 'slot_name', 'F10 sample', [], 'F10-style'),
  item('TextFrame', 'slot_title', 'Arc sample', [], 'Arc-style', [0, 40, 100, 20], {{ kind: 'PATHTEXT', pathToken: 'arc-main', textSize: 18 }}),
  ...(task.mock_font_tail ? [item('TextFrame', 'tail_name_last_m', 'm', [], 'F10-style', undefined, {{ puaTailBase: task.mock_pua_tail_base || 0 }})] : []),
  item('PathItem', '', '', [])
]);
const design03 = item('GroupItem', 'Design03', '', [
  item('GroupItem', 'slot_initial', '', [item('PathItem', 'placeholder_initial', '', [])]),
  item('TextFrame', 'slot_name', 'Design sample', [], 'Design-style'),
  item('TextFrame', 'slot_year_tail', 'Year sample', [], 'Year-style'),
  item('PathItem', 'anchor_name', '', []),
  item('GroupItem', 'slot_group', '', [
    item('TextFrame', 'slot_group_text', 'Group sample', [], 'Group-style'),
    item('PathItem', 'slot_group_decoration', '', [])
  ]),
  item('GroupItem', 'slot_ratio_group', '', [
    item('TextFrame', 'slot_ratio_text', 'Ratio sample', [], 'Ratio-style'),
    item('PathItem', 'keep_ratio', '', []),
    item('PathItem', 'keep_ratio_heart', '', [])
  ]),
  item('TextFrame', 'tail_name_first_a', task.mock_first_tail_sample || 'a', [], 'First-tail-style'),
  item('TextFrame', 'tail_name_first_m', task.mock_first_tail_sample || 'm', [], 'First-tail-style'),
  item('TextFrame', 'tail_name_last_a', task.mock_last_tail_sample || 'a', [], 'Last-tail-style'),
  item('TextFrame', 'tail_name_last_m', 'm', [], 'Last-tail-style', undefined, {{ puaTailBase: task.mock_pua_tail_base || 0 }}),
  item('TextFrame', 'tail_year_tail_last_a', 'a', [], 'Year-last-tail-style'),
  item('TextFrame', 'tail_name_1', 'Tail 1', [], 'Tail-style'),
  item('TextFrame', 'tail_name_2', 'Tail 2', [], 'Tail-style'),
  item('TextFrame', 'slot_year', '2026', [], 'Year-style'),
  item('PathItem', 'fixed_heart', '', []),
  item('GroupItem', 'Assets', '', [
    item('GroupItem', 'initial_top', '', [
      item('PathItem', 'A', '', []),
      item('PathItem', 'T', '', [])
    ])
  ]),
  item('PathItem', '', '', [])
]);
const style1 = item('GroupItem', 'style1', '', [item('PathItem', 'style1_shape', '', [], '', style1Bounds)]);
const style2 = item('GroupItem', 'style2', '', [item('PathItem', 'style2_shape', '', [], '', [0, 200, 200, 0])]);
const styleGroup = item('GroupItem', 'Style', '', [style1, style2]);
const fontGroup = item('GroupItem', 'Font', '', [f1, f10]);
const designGroup = item('GroupItem', 'Design', '', [design03]);
const outputMain = item('GroupItem', 'Output_main', '', [styleGroup, fontGroup, designGroup]);
const outputSideB = item('GroupItem', 'Output_SideB', '', [clone(fontGroup), clone(designGroup)]);
const templateLayer = {{ typename: 'Layer', name: 'Template', pageItems: [outputMain, outputSideB] }};
outputMain.parent = templateLayer;
outputSideB.parent = templateLayer;
const templateDoc = {{ layers: [templateLayer], close: () => undefined }};
const outputLayer = {{ typename: 'Layer', name: 'Layer 1', pageItems: [] }};
outputLayer.groupItems = {{
  add: () => {{
    const group = item('GroupItem', '', '', []);
    attach(outputLayer, group);
    return group;
  }}
}};
const outputDoc = {{
  layers: [outputLayer],
  artboards: [{{ artboardRect: [0, 1000, 1000, 0] }}],
  selection: [],
  saveAs: file => {{ savedAs = file.fsName; savedArtboard = outputDoc.artboards[0].artboardRect.slice(); }},
  // Illustrator appends the PNG24 extension automatically.
  exportFile: (file, type, options) => {{ exportedAs = file.fsName + '.png'; exportOptions = options; }},
  close: () => undefined
}};
function glyphDocument() {{
  const glyph = item('PathItem', '', '', [], '', [0, 20, 10, 0]);
  glyph.openTypeTail = true;
  const glyphLayer = {{ typename: 'Layer', name: 'SVG', pageItems: [glyph] }};
  glyph.parent = glyphLayer;
  return {{ layers: [glyphLayer], close: () => undefined }};
}}
function groupSelectedOutputItems() {{
  const selected = outputLayer.pageItems.filter(item => item.selected);
  const group = item('GroupItem', '', '', []);
  attach(outputLayer, group);
  for (const childNode of selected.slice()) {{
    childNode.selected = false;
    childNode.move(group, ElementPlacement.PLACEATEND);
  }}
  outputDoc.selection = [group];
}}
global.app = {{
  userInteractionLevel: 0,
  open: file => /\.svg$/i.test(String(file && file.fsName || '')) ? glyphDocument() : templateDoc,
  activeDocument: outputDoc,
  documents: {{ add: () => {{
    global.app.activeDocument = outputDoc;
    return outputDoc;
  }} }},
  executeMenuCommand: command => {{
    if (command === 'group') groupSelectedOutputItems();
  }}
}};
if ({str(disable_native_json).lower()}) global.JSON = undefined;
new Function(source)();
global.JSON = NativeJSON;
{assertions}
console.log(JSON.stringify({{ savedAs, exportedAs, copied: outputLayer.pageItems.map(item => item.name) }}));
"""
