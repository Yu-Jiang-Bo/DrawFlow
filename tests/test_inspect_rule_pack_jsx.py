import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_jsx_isolates_an_unsupported_object_and_continues_scan():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the JSX behavior harness")
    script_path = Path("scripts/illustrator/inspect_rule_pack.jsx").resolve()
    harness = f"""
const fs = require('fs');
const source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
const writes = {{}};
global.$ = {{ getenv: () => 'task.json' }};
global.File = function(path) {{
  return {{
    fsName: path,
    exists: true,
    open: () => true,
    read: () => JSON.stringify({{ input_ai: 'input.ai', output_json: 'out.json' }}),
    write: text => {{ writes[path] = text; }},
    close: () => undefined
  }};
}};
const broken = {{ typename: 'GroupItem', name: 'BROKEN' }};
Object.defineProperty(broken, 'pageItems', {{ get: () => {{ throw new Error('unsupported children'); }} }});
const good = {{
  typename: 'TextFrame', name: 'Name1', contents: 'Sample', kind: 'TextType.AREATEXT',
  visibleBounds: [0, 10, 20, 0], opacity: 100, hidden: false, locked: false,
  textRange: {{ characterAttributes: {{
    textFont: {{ name: 'DemoFont', family: 'Demo', style: 'Regular' }},
    size: 12, fillColor: {{ typename: 'RGBColor', red: 0, green: 0, blue: 0 }}
  }} }}
}};
const layer = {{ name: 'Layer', visible: true, locked: false, pageItems: [broken, good] }};
global.app = {{ open: () => ({{
  name: 'demo.ai', documentColorSpace: 'RGB', width: 100, height: 100,
  layers: [layer], close: () => undefined
}}) }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
new Function(source)();
const scan = JSON.parse(writes['out.json']);
if (scan.items.length !== 2) throw new Error('scan did not continue');
if (scan.items[1].name !== 'Name1') throw new Error('good object missing');
if (scan.scan_errors.length !== 1) throw new Error('isolated error missing');
console.log(JSON.stringify({{ items: scan.items.length, errors: scan.scan_errors.length }}));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"items": 2, "errors": 1}


def test_jsx_uses_strict_json_parsing_without_eval():
    script = Path("scripts/illustrator/inspect_rule_pack.jsx").read_text(encoding="utf-8")

    assert "JSON.parse unavailable" in script
    assert "eval(" not in script
