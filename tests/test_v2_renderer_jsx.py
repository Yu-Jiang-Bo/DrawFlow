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


def test_v2_renderer_copies_selected_groups_and_replaces_single_and_multi_slots():
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
if (child(designCopy, 'slot_name').contents !== 'Amy') throw new Error('primary multi slot mismatch');
if (child(designCopy, 'tail_name_1').contents !== 'Beth') throw new Error('first tail mismatch');
if (child(designCopy, 'tail_name_2').contents !== 'Cara') throw new Error('second tail mismatch');
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
        "values": {"design": "03", "name": "Alice|Beth"},
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
if (child(designCopy, 'slot_name').contents !== 'Alice') throw new Error('first split slot mismatch: ' + child(designCopy, 'slot_name').contents);
if (child(designCopy, 'slot_year').contents !== 'Beth') throw new Error('second split slot mismatch: ' + child(designCopy, 'slot_year').contents);
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


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


def test_v2_renderer_short_text_centers_without_resizing():
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
if (slot.resizeCalls !== 0) throw new Error('short text should not resize');
const centerX = (slot.visibleBounds[0] + slot.visibleBounds[2]) / 2;
const centerY = (slot.visibleBounds[1] + slot.visibleBounds[3]) / 2;
if (Math.abs(centerX - 50) > 0.1 || Math.abs(centerY - 15) > 0.1) throw new Error('short text not centered');
""")

    result = run_node(harness)

    assert result.returncode == 0, result.stderr


def test_v2_renderer_normal_text_stays_proportional_without_resizing():
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
if (slot.resizeCalls !== 0) throw new Error('normal text should keep template scale');
const width = slot.visibleBounds[2] - slot.visibleBounds[0];
if (width > 100.01) throw new Error('normal text escaped slot width');
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
        "visible_bounds_padding_after_resize": {"Design03": 0.01},
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


def node_mock_harness(task, assertions):
    return f"""
const fs = require('fs');
const source = {jsx_source_expression()};
const task = {json.dumps(task)};
const visibleBoundsFailures = new Set(task.visible_bounds_failures || []);
const visibleBoundsPaddingAfterResize = task.visible_bounds_padding_after_resize || {{}};
const folder = {{ exists: true, parent: null, create: () => true }};
let savedAs = '';
const writtenFiles = {{}};
global.$ = {{ getenv: () => 'task.json' }};
global.File = function(path) {{
  return {{
    fsName: path,
    exists: path === 'task.json',
    parent: folder,
    open: () => true,
    read: () => JSON.stringify(task),
    write: text => {{ writtenFiles[path] = (writtenFiles[path] || '') + String(text); }},
    close: () => undefined,
    remove: () => undefined
  }};
}};
global.UserInteractionLevel = {{ DONTDISPLAYALERTS: 0 }};
global.DocumentColorSpace = {{ RGB: 1 }};
global.ElementPlacement = {{ PLACEATEND: 1 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
global.Compatibility = {{ ILLUSTRATOR8: 8 }};
global.IllustratorSaveOptions = function() {{}};
global.Transformation = {{ CENTER: 0 }};
function item(typename, name, contents, children, styleToken, bounds, options) {{
  let text = contents || '';
  const opts = options || {{}};
  let textSize = Number(opts.textSize || 18);
  let box = (bounds || defaultBounds(typename, name, text)).slice();
  const baseBox = box.slice();
  const node = {{
    typename,
    name,
    kind: opts.kind || '',
    pathToken: opts.pathToken || '',
    styleToken: styleToken || '',
    pageItems: children || [],
    translateCalls: 0,
    resizeCalls: 0,
    duplicate: function(targetLayer) {{
      const copy = clone(this);
      attach(targetLayer, copy);
      return copy;
    }},
    remove: function() {{
      if (!this.parent || !this.parent.pageItems) return;
      const index = this.parent.pageItems.indexOf(this);
      if (index >= 0) this.parent.pageItems.splice(index, 1);
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
      const bounds = node.pageItems.length ? union(node.pageItems.map(item => item.visibleBounds)) : box.slice();
      const padding = node.fromCopy && node.resizeCalls > 0 ? Number(visibleBoundsPaddingAfterResize[node.name] || 0) : 0;
      return padding > 0 ? [bounds[0] - padding, bounds[1] + padding, bounds[2] + padding, bounds[3] - padding] : bounds;
    }},
    set: value => {{ box = value.slice(); }}
  }});
  Object.defineProperty(node, 'geometricBounds', {{ get: () => box.slice() }});
  for (const childNode of node.pageItems) childNode.parent = node;
  return node;
}}
function defaultBounds(typename, name, contents) {{
  if (name === 'anchor_name') return [200, 120, 260, 100];
  if (typename === 'TextFrame' && name === 'slot_name') return [0, 30, 100, 0];
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
    textSize: node.textSize
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
const f1 = item('GroupItem', 'F1', '', [item('TextFrame', 'slot_name', 'F1 sample', [], 'F1-style')]);
const f10 = item('GroupItem', 'F10', '', [
  item('TextFrame', 'slot_name', 'F10 sample', [], 'F10-style'),
  item('TextFrame', 'slot_title', 'Arc sample', [], 'Arc-style', [0, 40, 100, 20], {{ kind: 'PATHTEXT', pathToken: 'arc-main', textSize: 18 }}),
  item('PathItem', '', '', [])
]);
const design03 = item('GroupItem', 'Design03', '', [
  item('TextFrame', 'slot_name', 'Design sample', [], 'Design-style'),
  item('TextFrame', 'slot_year_tail', 'Year sample', [], 'Year-style'),
  item('PathItem', 'anchor_name', '', []),
  item('GroupItem', 'slot_group', '', [
    item('TextFrame', 'slot_group_text', 'Group sample', [], 'Group-style'),
    item('PathItem', 'slot_group_decoration', '', [])
  ]),
  item('TextFrame', 'tail_name_first_a', 'a', [], 'First-tail-style'),
  item('TextFrame', 'tail_name_last_a', 'a', [], 'Last-tail-style'),
  item('TextFrame', 'tail_year_tail_last_a', 'a', [], 'Year-last-tail-style'),
  item('TextFrame', 'tail_name_1', 'Tail 1', [], 'Tail-style'),
  item('TextFrame', 'tail_name_2', 'Tail 2', [], 'Tail-style'),
  item('TextFrame', 'slot_year', '2026', [], 'Year-style'),
  item('PathItem', 'fixed_heart', '', []),
  item('PathItem', '', '', [])
]);
const fontGroup = item('GroupItem', 'Font', '', [f1, f10]);
const designGroup = item('GroupItem', 'Design', '', [design03]);
const outputMain = item('GroupItem', 'Output_main', '', [fontGroup, designGroup]);
const templateLayer = {{ typename: 'Layer', name: 'Template', pageItems: [outputMain] }};
outputMain.parent = templateLayer;
const templateDoc = {{ layers: [templateLayer], close: () => undefined }};
const outputLayer = {{ typename: 'Layer', name: 'Layer 1', pageItems: [] }};
const outputDoc = {{
  layers: [outputLayer],
  saveAs: file => {{ savedAs = file.fsName; }},
  close: () => undefined
}};
global.app = {{
  userInteractionLevel: 0,
  open: () => templateDoc,
  documents: {{ add: () => outputDoc }}
}};
new Function(source)();
{assertions}
console.log(JSON.stringify({{ savedAs, copied: outputLayer.pageItems.map(item => item.name) }}));
"""
