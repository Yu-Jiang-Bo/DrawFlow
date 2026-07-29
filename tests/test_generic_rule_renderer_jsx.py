import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/illustrator/render_generic_rule_pack.jsx")
GROUPED_SCRIPT = Path("scripts/illustrator/render_config_grouped_text_sheet.jsx")


def test_generic_renderer_cycles_configured_name_colors_only():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "task.orders.length" in source
    assert "applyOptionGroups" in source
    assert "applyVariables" in source
    assert "applyAssets" in source
    assert "task.dimensions" in source
    assert "task.text_policies" in source
    assert "findPageItemsByName" in source
    assert "resolveVariableTargets" in source
    assert "findFallbackNameTextFrames" in source
    assert "function createNameColumnsDocument(task, order)" in source
    assert "function drawNameColumns(doc, order, layout, fontSource, cell, dimensions)" in source
    assert "function createNameColumnsSheet(task)" in source
    assert "app.documents.add(DocumentColorSpace.RGB, pageWidth, height)" in source
    assert 'String(layout.artboard_mode || "") === "single"' in source
    assert "function planNameColumnsSingleArtboard(orders, layout, requestedColumns, cellWidth, maxArtboardSize, dimensions)" in source
    assert "function planNameColumnsMasonryUnbounded(orders, layout, columns, dimensions)" in source
    assert "function drawCardBackground(doc, left, top, width, height, color)" in source
    assert "drawCardBackground(doc, left, cardTop, width, height, cardBackground)" in source
    assert "function hasLayoutTextValue(value)" in source
    assert "var drawFooter = shouldDrawLayoutFooter(order, mode, layout);" in source
    assert "var nameBottom = cardBottom + margin + (drawFooter ? footerHeight : 0);" in source
    assert "if (drawFooter) {" in source
    assert "function addNameBlockText(doc, parts, x, y, size, lineGap, actions, legacyCycle, fontSource)" in source
    assert "function addBoxedNameSegment(doc, text, x, top, height, size, box, variable, legacyCycle, index, fontSource, member)" in source
    assert "function configuredNameSegmentBox(layout, dimensions)" in source
    assert "segment_box_target" in source
    assert "function splitBoxedNameParts(value, name)" in source
    assert "function fitTextStrict(frame, widthMm, heightMm, target)" in source
    assert "function fitTextToExactBox(frame, widthMm, heightMm, target)" in source
    assert "function resizeTextToBounds(frame, horizontalPercent, verticalPercent)" in source
    assert "function alignTextToExactBox(frame, left, top, width, height, target)" in source
    assert "fill_box_exactly === true" in source
    assert "function centerLayoutTextInBox(frame, x, top, height)" in source
    assert "function wrapGeneratedText(frame, name)" in source
    assert "holder.name = name;" in source
    assert "function createLayoutAudit(task)" in source
    assert "function recordLayoutAudit(kind, name, frame, expected)" in source
    assert "function layoutAuditIdentity(order)" in source
    assert 'row + "_copy_" + String(copy)' in source
    assert "function flushLayoutAudit()" in source
    assert "task.layout_audit_file" in source
    assert "function shouldDrawLayoutFooter(order, mode, layout)" in source
    assert "footer.optional === true" in source
    assert "var minimumNameHeight = segmentBox ? mmToPt(segmentBox.height_mm) : nameSize;" in source
    assert "var availableHeight = Math.max(minimumNameHeight, nameTop - nameBottom);" in source
    assert 'parts.join("\\r")' in source
    assert "function applyNameBlockColors(frame, parts, actions, legacyCycle)" in source
    assert "function applyNameBlockBoldness(frame, actions)" in source
    assert "function applyLineBoldness(frame, value)" in source
    assert "var lines = frame.lines;" in source
    assert "function fittedNameSize(parts, baseSize, maxWidth, minSize)" in source
    assert "function fitLayoutTextWidth(frame, maxWidth, minSize)" in source
    assert "function estimatedLayoutTextWidth(text, size)" in source
    assert "function fontStyleForSelection(source, targetDoc, cache, selected, declaredStyles)" in source
    assert "function applyLayoutTextStyle(style, target)" in source
    assert "function applyConfiguredFontStyle(config, target)" in source
    assert "function applyFontByName(target, fontName)" in source
    assert "app.textFonts.getByName" not in source
    assert "function createFontPrototype(sourceFrame, targetDoc)" in source
    assert "function removeFontPrototypes(cache)" in source
    assert "fontSource.prototype.duplicate(doc.layers[0], ElementPlacement.PLACEATEND)" in source
    assert "function colorForNamePart(actions, index, legacyCycle)" in source
    assert "task.allow_unnamed_name_fallback === true" in source
    assert 'String(variable.target || "") + "_ANCHOR"' in source
    assert "copyTextStyle(fontSource, frame)" in source
    assert "applyNameColorCycle(frame, variable)" in source
    assert "applyFontBoldness(frame, variable.font_style)" in source
    assert "function applyFontBoldness(frame, style)" in source
    assert "function applyRuleActions(frame, actions)" in source
    assert 'String(action.type || "") === "fill_color"' in source
    assert 'String(action.type || "") === "stroke_width"' in source
    assert "applyFrameBoldness(frame, action.value)" in source
    assert "function applyFrameBoldness(frame, value)" in source
    assert "Unsupported compiled rule action" in source
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
    assert 'task.output && task.output.compatibility' in source
    assert 'String(compatibility || "Illustrator 8").toLowerCase()' in source
    assert "Compatibility.ILLUSTRATOR15" in source
    assert "options.compatibility = Compatibility.ILLUSTRATOR8;" in source
    assert "options.pdfCompatible = false;" in source
    assert "options.compressed = false;" in source
    assert "options.compressed = true;" not in source
    assert "doc.pathItems.rectangle(height, 0, width, height)" not in source
    outline_body = source[source.index("if (transforms.outline_text)"):source.index("function applyOutputSettings")]
    assert "outlineAllTextFrames(doc, transforms.pathfinder_merge === true)" in outline_body
    assert "findPageItemsByName" not in outline_body
    assert "outlineItems.length" not in outline_body
    assert "function outlineAllTextFrames(doc, pathfinderMerge)" in source
    assert "function collectTextFrames(container, result)" in source
    assert "function cleanupOutline(item)" in source
    assert "pathfinder_merge: output.pathfinder_merge !== false" in source
    assert "JJMB" not in source


def assert_javascript_parses_in_node(node, source, tmp_path):
    source_file = tmp_path / "source.js"
    source_file.write_text(source, encoding="utf-8")

    return subprocess.run(
        [
            node,
            "-e",
            "const fs = require('fs'); new Function(fs.readFileSync(process.argv[1], 'utf8'));",
            str(source_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generic_renderer_javascript_parses_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source = SCRIPT.read_text(encoding="utf-8").replace("#target illustrator", "", 1)

    result = assert_javascript_parses_in_node(node, source, tmp_path)

    assert result.returncode == 0, result.stderr


def test_grouped_single_graphic_initializes_fit_stats_before_early_return():
    source = GROUPED_SCRIPT.read_text(encoding="utf-8")

    fit_stats_index = source.index("var fitStats = { count: 0, maxDeltaPt: 0, f11HeartFitCount: 0 };")
    single_graphic_index = source.index("if (layout.single_graphic_exact === true")
    record_fit_index = source.index("function recordFitDelta")

    assert fit_stats_index < single_graphic_index
    assert single_graphic_index < record_fit_index


def test_exact_box_geometry_uses_independent_scaling_and_corner_alignment():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    script_path = SCRIPT.resolve()
    harness = f"""
const fs = require('fs');
let source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
source = source.replace('var EXACT_BOX_MAX_DELTA_PT = 0.02;', '');
source = source.replace(
  '(function () {{',
  '(function () {{ var EXACT_BOX_MAX_DELTA_PT = 0.02; global.__exactBox = {{ fit: fitTextToExactBox, align: alignTextToExactBox, mmToPt: mmToPt }}; return;'
);
new Function(source)();
const frame = {{
  visibleBounds: [0, 20, 30, 0],
  resize: function(horizontalPercent, verticalPercent) {{
    const left = this.visibleBounds[0];
    const top = this.visibleBounds[1];
    const right = this.visibleBounds[2];
    const bottom = this.visibleBounds[3];
    const centerX = (left + right) / 2;
    const centerY = (top + bottom) / 2;
    const width = (right - left) * horizontalPercent / 100;
    const height = (top - bottom) * verticalPercent / 100;
    this.visibleBounds = [centerX - width / 2, centerY + height / 2, centerX + width / 2, centerY - height / 2];
  }},
  translate: function(dx, dy) {{
    this.visibleBounds = [
      this.visibleBounds[0] + dx,
      this.visibleBounds[1] + dy,
      this.visibleBounds[2] + dx,
      this.visibleBounds[3] + dy,
    ];
  }},
}};
const width = global.__exactBox.mmToPt(17);
const height = global.__exactBox.mmToPt(10);
global.__exactBox.fit(frame, 17, 10, 'Name');
global.__exactBox.align(frame, 100, 200, width, height, 'Name');
const actual = frame.visibleBounds;
for (const [value, expected] of [[actual[0], 100], [actual[1], 200], [actual[2], 100 + width], [actual[3], 200 - height]]) {{
  if (Math.abs(value - expected) > 0.02) throw new Error('exact box mismatch');
}}
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_exact_box_rendering_remains_explicitly_opt_in():
    source = SCRIPT.read_text(encoding="utf-8")
    boxed_name_body = source[source.index("function addBoxedNameSegment"):source.index("function fittedNameSize")]
    footer_body = source[source.index("if (drawFooter)"):source.index("function drawCardBackground")]

    assert "var EXACT_BOX_MAX_DELTA_PT = 0.02;" in source
    assert "frame.resize(horizontalPercent, verticalPercent" in source
    assert "if (box.fill_box_exactly === true)" in boxed_name_body
    assert "else {\n            fitTextStrict(frame" in boxed_name_body
    assert "if (footerBox.fill_box_exactly === true)" in footer_body
    assert "else {\n                    fitTextStrict(footerFrame" in footer_body


def test_single_artboard_masonry_expands_columns_to_fit_canvas():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    script_path = SCRIPT.resolve()
    harness = f"""
const fs = require('fs');
let source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
source = source.replace(
  '(function () {{',
  '(function () {{ global.__planner = planNameColumnsSingleArtboard; global.__mmToPt = mmToPt; return;'
);
new Function(source)();
const layout = {{
  margin_mm: 10,
  header_height_mm: 24,
  footer_height_mm: 12,
  card_gap_mm: 8,
  default: {{ header_fields: ['order_no'], footer_field: 'year' }},
  name: {{ delimiter: '|', font_size_pt: 72, line_gap_mm: 8 }}
}};
const orders = Array.from({{ length: 144 }}, (_, index) => ({{
  order_no: String(index + 1),
  year: '2026',
  variables: [{{ target: 'Name', value: 'A|B|C|D' }}]
}}));
const plan = global.__planner(orders, layout, 4, global.__mmToPt(100), global.__mmToPt(5750));
if (!plan) throw new Error('single artboard plan not found');
console.log(JSON.stringify({{ pages: plan.pages, columns: plan.columns, items: plan.items.length }}));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"pages": 1, "columns": 5, "items": 144}


def test_name_columns_footer_height_requires_a_nonblank_value():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    script_path = SCRIPT.resolve()
    harness = f"""
const fs = require('fs');
let source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
source = source.replace(
  '(function () {{',
  '(function () {{ global.__height = nameColumnsBlockHeight; return;'
);
new Function(source)();
const layout = {{
  margin_mm: 10,
  header_height_mm: 24,
  footer_height_mm: 12,
  default: {{ header_fields: ['order_no'], footer_field: 'year' }},
  name: {{ delimiter: '|', font_size_pt: 72, line_gap_mm: 8 }}
}};
const base = {{ order_no: 'A-1', variables: [{{ target: 'Name', value: 'A|B' }}] }};
const withYear = Object.assign({{}}, base, {{ values: {{ year: '2025' }} }});
const withoutYear = Object.assign({{}}, base, {{ values: {{ year: '   ' }} }});
console.log(JSON.stringify({{ withYear: global.__height(withYear, layout), withoutYear: global.__height(withoutYear, layout) }}));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    heights = json.loads(result.stdout)
    assert heights["withYear"] > heights["withoutYear"]


def test_grouped_renderer_applies_each_task_font_style_before_outlining():
    source = GROUPED_SCRIPT.read_text(encoding="utf-8")

    assert "var fontStyles = task.font_styles || {};" in source
    assert 'applyFontBoldness(tf, fontStyles[String(item.font_option || "")]);' in source
    assert "function applyFontBoldness(tf, style)" in source
    assert "attributes.strokeColor = attributes.fillColor" in source
    assert "attributes.strokeWeight = boldness" in source
    design_body = source[source.index("function renderDesignAssetItem"):source.index("function removeDiagnosticFrames")]
    instance_body = source[source.index("function duplicateDesignInstance"):source.index("function arrangeDesignInstances")]
    assert "applyFontBoldnessToTextFrames(copy, fontStyle);" in instance_body
    assert "var outlineText = exportConfig.outline_text !== false;" in source
    assert "if (!outlineText)" in source
    assert "if (outlineText)" in design_body
    assert design_body.index("duplicateDesignInstance") < design_body.index("outlineTextFrames(copy);")
    assert "function applyFontBoldnessToTextFrames(root, style)" in source
    assert "var showStyleBoxes = layout.show_style_boxes === true;" in source


def test_grouped_renderer_removes_diagnostic_frames_from_design_assets():
    source = GROUPED_SCRIPT.read_text(encoding="utf-8")

    instance_body = source[source.index("function duplicateDesignInstance"):source.index("function arrangeDesignInstances")]
    assert "removeDiagnosticFrames(copy);" in instance_body
    assert instance_body.index("removeDiagnosticFrames(copy);") < instance_body.index("replaceDesignTexts(copy, parts || []);")
    assert "function removeDiagnosticFrames(root)" in source
    assert "function isUnfilledStrokedRed(item)" in source
    assert "function isLargeFrame(item, rootBounds)" in source
    assert "item.filled === true" in source
    assert "item.stroked !== true" in source
    assert "Number(color.red) >= 180" in source
    assert "Number(color.magenta) >= 70" in source


def test_grouped_renderer_supports_repeated_design_instances_and_f11_f12_alignment():
    source = GROUPED_SCRIPT.read_text(encoding="utf-8")

    assert "function normalizeDesignInstances(item)" in source
    assert "var instances = item.design_instances || [];" in source
    assert "function arrangeDesignInstances(items)" in source
    assert "children.push(duplicateDesignInstance" in source
    assert "copy = layer.groupItems.add();" in source
    assert "function applyDesignTextAlignment(root, fontOption)" in source
    assert "function applyF11PrimaryHeartFit(root, fontOption)" in source
    assert "function findF11HeartMarker(root, primaryBounds)" in source
    assert "function findNamedHeartMarker(candidates)" in source
    assert "function collectFixedVisualItems(item, out)" in source
    assert "applyF11PrimaryHeartFit(copy, fontOption);" in source
    assert "primary.resize(scale * 100, scale * 100" in source
    assert "availableRight = hb[0] - gap" in source
    assert "desiredHeartLeft = pb[2] + gap" in source
    assert "heart.item.translate(desiredHeartLeft - hb[0], desiredHeartBottom - hb[3]);" in source
    assert source.index("var named = findNamedHeartMarker(candidates);") < source.index("var bestScore = -999999;")
    assert 'name.indexOf("heart") >= 0 || name.indexOf("love") >= 0' in source
    assert 'if (option !== "F11" && option !== "F12") return;' in source
    assert 'if (option === "F11")' in source
    assert "var secondaryWidth = Math.abs(sb[2] - sb[0]);" in source
    assert "var secondaryMaxRight = pb[2] + Math.max(mmToPt(5), Math.min(primaryWidth * 0.28, mmToPt(14)));" in source
    assert "var desiredSecondaryLeft = primaryCenter + Math.min(primaryWidth * 0.07, mmToPt(4));" in source
    assert "desiredSecondaryLeft = secondaryMaxRight - secondaryWidth;" in source
    assert "secondary.translate(desiredSecondaryLeft - sb[0], 0);" in source
    assert "currentGap > desiredGap" in source


def test_grouped_renderer_f11_secondary_alignment_uses_left_edge_geometry():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    script_path = GROUPED_SCRIPT.resolve()
    harness = f"""
const fs = require('fs');
let source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
source = source.replace(
  '(function () {{',
  '(function () {{ global.__align = applyDesignTextAlignment; global.__mmToPt = mmToPt; return;'
);
new Function(source)();
function frame(name, bounds) {{
  return {{
    typename: 'TextFrame',
    name,
    visibleBounds: bounds.slice(),
    translate: function(dx, dy) {{
      this.visibleBounds = [
        this.visibleBounds[0] + dx,
        this.visibleBounds[1] + dy,
        this.visibleBounds[2] + dx,
        this.visibleBounds[3] + dy,
      ];
    }},
  }};
}}
function run(secondaryBounds) {{
  const primary = frame('Text1', [0, 30, 100, 0]);
  const secondary = frame('Text2', secondaryBounds);
  global.__align({{ pageItems: [primary, secondary] }}, 'F11');
  return secondary.visibleBounds;
}}
const shortBounds = run([10, -10, 40, -30]);
const longBounds = run([10, -10, 170, -30]);
const shortLeft = 50 + Math.min(100 * 0.07, global.__mmToPt(4));
const maxRight = 100 + Math.max(global.__mmToPt(5), Math.min(100 * 0.28, global.__mmToPt(14)));
if (Math.abs(shortBounds[0] - shortLeft) > 0.02) throw new Error('short secondary should start slightly right of primary center');
if (Math.abs(longBounds[2] - maxRight) > 0.02) throw new Error('long secondary should borrow left only after hitting max right');
if (longBounds[0] >= 50) throw new Error('long secondary did not borrow left-side space');
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_grouped_renderer_javascript_parses_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source = GROUPED_SCRIPT.read_text(encoding="utf-8").replace("#target illustrator", "", 1)

    result = assert_javascript_parses_in_node(node, source, tmp_path)

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
        "allow_unnamed_name_fallback": True,
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
                        "font_style": {"boldness": 0.4},
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
const weights = [0, 2, 4, 6].map(index => characters[index].characterAttributes.strokeWeight);
if (JSON.stringify(weights) !== JSON.stringify([0.4, 0.4, 0.4, 0.4])) throw new Error(JSON.stringify(weights));
console.log(JSON.stringify(values));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [[255, 0, 0], [0, 0, 0], [0, 0, 255], [255, 0, 0]]


def test_generic_renderer_uses_blank_name_placeholder_when_target_is_unnamed():
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
        "allow_unnamed_name_fallback": True,
        "orders": [
            {
                "selections": {},
                "variables": [{"target": "Name", "field": "text", "value": "Alice"}],
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
global.RGBColor = function() {{}};
global.IllustratorSaveOptions = function() {{}};
global.Compatibility = {{ ILLUSTRATOR8: 8 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
function textFrame(contents, bounds) {{
  return {{
    typename: 'TextFrame',
    name: '',
    contents,
    visibleBounds: bounds,
    textRange: {{ characterAttributes: {{}}, paragraphAttributes: {{}} }},
    characters: []
  }};
}}
const document = {{ typename: 'Document', layers: [], saveAs: () => undefined, close: () => undefined }};
const layer = {{ typename: 'Layer', name: 'Layer 1', pageItems: [], parent: document }};
const fontGroup = {{ typename: 'GroupItem', name: 'Font', pageItems: [], parent: layer }};
const instruction = textFrame('名字说明，不应该被覆盖', [0, 100, 400, 80]);
const fontBlank = textFrame('', [0, 200, 500, 100]);
const placeholder = textFrame('', [0, 50, 200, 0]);
instruction.parent = layer;
fontBlank.parent = fontGroup;
placeholder.parent = layer;
fontGroup.pageItems = [fontBlank];
layer.pageItems = [instruction, fontGroup, placeholder];
document.layers = [layer];
global.app = {{ open: () => document, executeMenuCommand: () => undefined }};
new Function(source)();
if (placeholder.contents !== 'Alice') throw new Error('placeholder not filled: ' + placeholder.contents);
if (instruction.contents !== '名字说明，不应该被覆盖') throw new Error('instruction overwritten');
if (fontBlank.contents !== '') throw new Error('font group overwritten');
console.log(placeholder.contents);
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Alice"
