import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/illustrator/render_v2_template.jsx")


def run_node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    return subprocess.run([node, "-e", script], capture_output=True, text=True, check=False)


def jsx_source_expression():
    return f"fs.readFileSync({json.dumps(str(SCRIPT.resolve()))}, 'utf8').replace(/^#target.*\\r?\\n/, '')"


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
    assert "function saveAsAI8" in source
    assert "findPageItemsByName" not in source
    assert "app.doScript" not in source
    assert "eval(" not in source
    assert "JJMB" not in source


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


def node_mock_harness(task, assertions):
    return f"""
const fs = require('fs');
const source = {jsx_source_expression()};
const task = {json.dumps(task)};
const folder = {{ exists: true, parent: null, create: () => true }};
let savedAs = '';
global.$ = {{ getenv: () => 'task.json' }};
global.File = function(path) {{
  return {{
    fsName: path,
    exists: path === 'task.json',
    parent: folder,
    open: () => true,
    read: () => JSON.stringify(task),
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
function item(typename, name, contents, children, styleToken) {{
  const node = {{
    typename,
    name,
    contents: contents || '',
    styleToken: styleToken || '',
    pageItems: children || [],
    duplicate: function(targetLayer) {{
      const copy = clone(this);
      attach(targetLayer, copy);
      return copy;
    }},
    remove: function() {{
      if (!this.parent || !this.parent.pageItems) return;
      const index = this.parent.pageItems.indexOf(this);
      if (index >= 0) this.parent.pageItems.splice(index, 1);
    }}
  }};
  for (const childNode of node.pageItems) childNode.parent = node;
  return node;
}}
function clone(node) {{
  return item(node.typename, node.name, node.contents, node.pageItems.map(clone), node.styleToken);
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
  item('PathItem', '', '', [])
]);
const design03 = item('GroupItem', 'Design03', '', [
  item('TextFrame', 'slot_name', 'Design sample', [], 'Design-style'),
  item('TextFrame', 'tail_name_1', 'Tail 1', [], 'Tail-style'),
  item('TextFrame', 'tail_name_2', 'Tail 2', [], 'Tail-style'),
  item('TextFrame', 'slot_year', '2026', [], 'Year-style'),
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
