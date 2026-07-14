import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/illustrator/render_generic_rule_pack.jsx")


def test_generic_renderer_cycles_configured_name_colors_only():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "task.orders.length" in source
    assert "applyOptionGroups" in source
    assert "applyVariables" in source
    assert "applyAssets" in source
    assert "task.dimensions" in source
    assert "task.text_policies" in source
    assert "findPageItemsByName" in source
    assert 'String(variable.target || "") + "_ANCHOR"' in source
    assert "copyTextStyle(fontSource, frame)" in source
    assert "applyNameColorCycle(frame, variable)" in source
    assert 'String(variable.target || "") !== "Name"' in source
    assert "var rgb = hexColor(colors[partIndex % colors.length]);" in source
    assert "function hexColor(value)" in source
    assert "name_delimiter" not in source
    assert "[215, 25, 32]" not in source
    assert "applyTextEffects" not in source
    assert "TEXT_EFFECT_HANDLERS" not in source
    assert "applyTextEffectRange" not in source
    assert "applyCharacterStyles" not in source
    assert "doc-color-cmyk" in source
    assert "doc-color-rgb" in source
    assert "output.outline_text" in source
    assert "settings.rotation_deg" in source
    assert "settings.scale_percent" in source
    assert "settings.offset_x_mm" in source
    outline_body = source[source.index("if (transforms.outline_text)"):source.index("function applyOutputSettings")]
    assert "findPageItemsByName" in outline_body
    assert "outlineItems.length" in outline_body
    assert "JJMB" not in source


def test_generic_renderer_javascript_parses_in_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source = SCRIPT.read_text(encoding="utf-8").replace("#target illustrator", "", 1)

    result = subprocess.run(
        [node, "-e", "new Function(process.argv[1]);", source],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_generic_renderer_cycles_actual_name_characters_in_node_harness():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    script_path = SCRIPT.resolve()
    task = {
        "type": "generic_template_rules",
        "template_ai": "template.ai",
        "option_groups": [],
        "dimensions": {},
        "text_policies": {},
        "output": {},
        "orders": [
            {
                "selections": {},
                "variables": [
                    {
                        "target": "Name",
                        "value": "A|B|C|D",
                        "name_color_cycle": {
                            "delimiter": "|",
                            "colors": ["#FF0000", "#000000", "#0000FF"],
                        },
                    }
                ],
                "assets": [],
                "transforms": {},
                "output_ai": "output.ai",
            }
        ],
    }
    harness = f"""
const fs = require('fs');
const source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
const task = {json.dumps(task)};
const folder = {{ exists: true, parent: null, create: () => true }};
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
global.RGBColor = function() {{ this.red = 0; this.green = 0; this.blue = 0; }};
global.IllustratorSaveOptions = function() {{}};
global.Compatibility = {{ ILLUSTRATOR8: 8 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
let contents = '';
const characters = [];
const frame = {{ typename: 'TextFrame', name: 'Name', locked: false, hidden: false }};
Object.defineProperty(frame, 'contents', {{
  get: () => contents,
  set: value => {{
    contents = String(value);
    characters.length = 0;
    for (let index = 0; index < contents.length; index++) characters.push({{ characterAttributes: {{}} }});
  }}
}});
Object.defineProperty(frame, 'characters', {{ get: () => characters }});
const document = {{
  layers: [{{ pageItems: [frame] }}],
  saveAs: () => undefined,
  close: () => undefined
}};
global.app = {{ open: () => document, executeMenuCommand: () => undefined }};
new Function(source)();
const values = [0, 2, 4, 6].map(index => {{
  const color = characters[index].characterAttributes.fillColor;
  return [color.red, color.green, color.blue];
}});
const expected = [[255, 0, 0], [0, 0, 0], [0, 0, 255], [255, 0, 0]];
if (JSON.stringify(values) !== JSON.stringify(expected)) throw new Error(JSON.stringify(values));
console.log(JSON.stringify(values));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [[255, 0, 0], [0, 0, 0], [0, 0, 255], [255, 0, 0]]
