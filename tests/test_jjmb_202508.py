import json
from pathlib import Path
import shutil
import subprocess

from src.jjmb_202508_main import (
    DEFAULT_COLOR,
    DEFAULT_DESIGN,
    build_task,
    group_items,
    load_department_rules,
    normalize_color,
    normalize_design,
    parse_items,
    resolve_department_rule,
)


def test_normalize_color_defaults_and_aliases():
    assert normalize_color("") == DEFAULT_COLOR
    assert normalize_color("gold") == "Gold"
    assert normalize_color("White font") == "White"
    assert normalize_color("second one is Madison with Gold") == "Gold"
    assert normalize_color("Rose Gold") == "Rose Gold"


def test_normalize_design_defaults_and_case():
    assert normalize_design("") == DEFAULT_DESIGN
    assert normalize_design("design 2") == "Design2"
    assert normalize_design("Design 3") == "Design3"


def test_parse_items_applies_department_color_rule():
    rows = [
        {
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "生产部门": "K",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "产品",
            "字体": "F7",
            "定制信息": "Meg",
            "字体颜色": "Gold",
            "设计": "Design 3",
        },
        {
            "内部订单号": "ORDER2",
            "订单明细id": "2",
            "生产部门": "H",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "产品",
            "字体": "F1",
            "定制信息": "Amy",
            "字体颜色": "",
            "设计": "",
        },
    ]

    items = parse_items(rows)

    assert len(items) == 2
    assert items[0].apply_color_to_artwork is False
    assert items[0].show_color_label is True
    assert items[0].color_option == "Gold"
    assert items[0].design_option == "Design3"
    assert items[0].production_label == "ORDER1  金色"
    assert items[0].production_label_lines == ["ORDER1", "金色"]
    assert items[0].show_frame is False
    assert items[1].apply_color_to_artwork is True
    assert items[1].show_color_label is False
    assert items[1].color_option == DEFAULT_COLOR
    assert items[1].design_option == DEFAULT_DESIGN
    assert items[1].production_label == "ORDER2"
    assert items[1].production_label_lines == ["ORDER2"]
    assert items[1].show_frame is False


def test_parse_items_sets_department_labels_and_frames():
    rows = [
        {
            "内部订单号": "ORDER3",
            "订单明细id": "3",
            "生产部门": "D",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "皮质首饰盒",
            "字体": "F2",
            "定制信息": "Beth",
            "字体颜色": "Silver",
            "设计": "Design1",
        },
        {
            "内部订单号": "ORDER4",
            "订单明细id": "4",
            "生产部门": "PW",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "皮质首饰盒",
            "字体": "F3",
            "定制信息": "Cora",
            "字体颜色": "Black",
            "设计": "Design3",
        },
    ]

    items = parse_items(rows)

    assert items[0].production_label == "ORDER3  皮质首饰盒"
    assert items[0].show_frame is True
    assert items[1].production_label == "ORDER4  皮质首饰盒"
    assert items[1].show_frame is False


def test_parse_items_uses_the_requested_template_id():
    rows = [
        {
            "内部订单号": "ORDER5",
            "订单明细id": "5",
            "生产部门": "K",
            "模板": "JJMB202510241154389614",
            "产品中文名称": "树脂挂件",
            "字体": "F2",
            "定制信息": "Alice|Bob",
            "字体颜色": "Gold",
            "设计": "Design 1",
        }
    ]

    assert parse_items(rows) == []
    items = parse_items(rows, template_id="JJMB202510241154389614")

    assert [item.text for item in items] == ["Alice", "Bob"]
    preserved = parse_items(
        rows,
        template_id="JJMB202510241154389614",
        preserve_personalization=True,
    )
    assert [item.text for item in preserved] == ["Alice|Bob"]


def test_parse_items_splits_comma_separated_202508_name_lists():
    rows = [
        {
            "内部订单号": "ORDER-COMMAS",
            "订单明细id": "10",
            "生产部门": "K",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "产品",
            "字体": "F2",
            "定制信息": "Alice,Beth，Cora",
            "字体颜色": "Gold",
            "设计": "Design 1",
        }
    ]

    items = parse_items(rows)
    preserved = parse_items(rows, preserve_personalization=True)

    assert [item.text for item in items] == ["Alice", "Beth", "Cora"]
    assert [item.quantity_index for item in items] == [1, 2, 3]
    assert [item.text for item in preserved] == ["Alice", "Beth", "Cora"]


def test_parse_items_preserves_pipe_segments_but_splits_comma_name_lists():
    rows = [
        {
            "\u5185\u90e8\u8ba2\u5355\u53f7": "ORDER-SEGMENTS",
            "\u8ba2\u5355\u660e\u7ec6id": "11",
            "\u751f\u4ea7\u90e8\u95e8": "K",
            "\u6a21\u677f": "JJMB202508261001394920",
            "\u4ea7\u54c1\u4e2d\u6587\u540d\u79f0": "\u4ea7\u54c1",
            "\u5b57\u4f53": "F2",
            "\u5b9a\u5236\u4fe1\u606f": "Alice|Beth,Cora|Dana",
            "\u5b57\u4f53\u989c\u8272": "Gold",
            "\u8bbe\u8ba1": "Design 1",
        }
    ]

    items = parse_items(rows, preserve_personalization=True)

    assert [item.text for item in items] == ["Alice|Beth", "Cora|Dana"]


def test_build_task_keeps_actions_for_each_202508_text_item(tmp_path):
    rows = [
        {
            "内部订单号": "ORDER6",
            "订单明细id": "6",
            "生产部门": "K",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "皮质首饰盒",
            "字体": "F2",
            "定制信息": "Alice|Bob",
            "字体颜色": "Gold",
            "设计": "Design 1",
        }
    ]
    groups = group_items(parse_items(rows))
    actions = [[[{"type": "fill_color", "selector": {"type": "segments", "delimiter": "|"}, "values": ["#FF0000", "#FFFFFF"]}]]]

    task = build_task(
        tmp_path / "template.config.json",
        tmp_path / "out.ai",
        groups,
        columns=1,
        show_style_boxes=False,
        text_actions=actions,
    )

    assert task["groups"][0]["items"][0]["text_actions"] == actions[0][0]


def test_build_task_creates_exact_color_frames_with_actions(tmp_path):
    rows = [
        {
            "内部订单号": "ORDER8",
            "订单明细id": "8",
            "生产部门": "T",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "产品",
            "字体": "F2",
            "定制信息": "Alice",
            "字体颜色": "Gold",
            "设计": "Design1",
        },
        {
            "内部订单号": "ORDER9",
            "订单明细id": "9",
            "生产部门": "T",
            "模板": "JJMB202508261001394920",
            "产品中文名称": "产品",
            "字体": "F2",
            "定制信息": "Beth",
            "字体颜色": "Silver",
            "设计": "Design1",
        },
    ]
    groups = group_items(parse_items(rows))
    actions = [
        [[{"type": "fill_color", "values": ["#FF0000"]}]],
        [[{"type": "fill_color", "values": ["#FFFFFF"]}]],
    ]
    by_color = {
        "Gold": [groups[0]],
        "Silver": [groups[1]],
    }

    task = build_task(
        tmp_path / "template.config.json",
        tmp_path / "out.ai",
        groups,
        columns=1,
        show_style_boxes=False,
        text_actions=actions,
        fixed_canvas_mm={"width_mm": 580, "height_mm": 2000},
        master_packing={"target_width_mm": 580, "item_gap_mm": 2},
        color_frames=[
            {"color_option": color, "groups": frame_groups}
            for color, frame_groups in by_color.items()
        ],
    )

    assert [frame["color_option"] for frame in task["color_frames"]] == ["Gold", "Silver"]
    assert task["color_frames"][0]["groups"][0]["items"][0]["text_actions"] == actions[0][0]
    assert task["output"]["fixed_canvas_mm"] == {"width_mm": 580, "height_mm": 2000}
    assert task["layout"]["pack_order_blocks"] is True
    assert task["layout"]["master_packing"] == {"target_width_mm": 580, "item_gap_mm": 2}


def test_202508_renderer_accepts_compiled_fill_color_actions():
    source = Path("scripts/illustrator/render_202508_grouped.jsx").read_text(encoding="utf-8")

    assert "item.text_actions || []" in source
    assert "applyTextActions(tf, actions || []);" in source
    assert "function applyFillColorAction(tf, action)" in source
    assert "values[partIndex % values.length]" in source
    assert "function applyBoldnessToAttributes(attributes, boldness)" in source
    assert "var showBoxes = layout.show_style_boxes === true;" in source
    assert "var drawFrame = !compactOutput && showBoxes;" in source
    compose_source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")
    assert "task.type !== \"compose_color_frames\"" in compose_source
    assert "COLOR_FRAME_" in compose_source
    assert "boundary.stroked = colorFrameBoundary;" in compose_source
    assert "boundary.strokeColor = redColor();" in compose_source
    assert "COLOR_FRAME_OUTPUT" in compose_source
    assert "function packAdaptiveGrid(" in compose_source
    assert "function packColorFrameBlocks(" in compose_source
    assert "function placeOrderIntoColumns(" in compose_source
    assert "function findBestColumnWindow(" in compose_source
    assert "label_scope: \"order_segment\"" in compose_source
    assert "function collectOrderBlocks(source)" in compose_source
    assert "item.show_frame === true" not in source
    assert "var outlineText = outputConfig.outline_text !== false;" in source
    assert "if (!outlineText)" in source
    assert "var pathfinderMerge = outputConfig.pathfinder_merge !== false;" in source
    assert "if (outlineText)" in source
    assert "outlineAllTextFrames(doc, pathfinderMerge);" in source
    assert "function collectTextFrames(container, result)" in source
    assert "function groupNewLayerItems(layer, previousItems, name)" in source
    assert "var packOrderBlocks = layout.pack_order_blocks === true;" in source
    assert "var forceSubitemOrderLabels = packOrderBlocks" in source
    assert "ORDER_PACK_ITEM_" in source
    assert "outlineTextFrames(compactLabelFrames, pathfinderMerge);" in source
    assert "function outlineTextFrames(frames, shouldCleanup)" in source

    node = shutil.which("node")
    if not node:
        return
    result = subprocess.run(
        [
            node,
            "-e",
            "const fs=require('fs');new Function(fs.readFileSync(process.argv[1],'utf8').replace(/^#target.*\\r?\\n/,''));",
            str(Path("scripts/illustrator/render_202508_grouped.jsx").resolve()),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_202508_renderer_cycles_segment_colors_and_matches_each_stroke_color():
    node = shutil.which("node")
    if not node:
        return
    script_path = Path("scripts/illustrator/render_202508_grouped.jsx").resolve()
    task = {
        "type": "jjmb_202508_grouped",
        "template_config": "config.json",
        "output_ai": "out.ai",
        "groups": [
            {
                "order_no": "ORDER7",
                "items": [
                    {
                        "text": "A|B|C|D",
                        "font_option": "F2",
                        "color_option": "Black",
                        "design_option": "Design1",
                        "show_color_label": False,
                        "show_frame": False,
                        "production_label": "ORDER7",
                        "production_label_lines": ["ORDER7"],
                        "text_actions": [
                            {
                                "type": "fill_color",
                                "strategy": "cycle",
                                "values": ["#FF0000", "#FFFFFF"],
                                "selector": {"type": "segments", "delimiter": "|"},
                            }
                        ],
                    }
                ],
            }
        ],
        "font_styles": {"F2": {"boldness": 0.4}},
        "layout": {"columns": 1, "show_style_boxes": False},
        "fit": {"min_font_size_pt": 4, "max_font_size_pt": 48},
        "output": {"color_mode": "RGB", "pathfinder_merge": False},
        "debug": {"report_path": "debug.json"},
    }
    config = {
        "font_options": {"F2": {"font_size_pt": 12, "tracking": 0}},
        "design_options": {
            "Design1": {
                "product_bounds_pt": [0, 100, 100, 0],
                "anchor_bounds_pt": [0, 100, 100, 0],
                "rotation_deg": 0,
            }
        },
        "color_options": {"Black": {"rgb": [0, 0, 0]}},
        "defaults": {"design_option": "Design1"},
    }
    harness = f"""
const fs = require('fs');
const source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
const task = {json.dumps(task)};
const config = {json.dumps(config)};
const frames = [];
const folder = {{ exists: true, parent: null, create: () => true }};
function json(value) {{ return JSON.stringify(value); }}
global.$ = {{ getenv: () => 'task.json' }};
global.File = function(path) {{
  return {{
    fsName: path,
    exists: path === 'task.json' || path === 'config.json',
    parent: folder,
    open: () => true,
    read: () => path === 'task.json' ? json(task) : json(config),
    write: () => undefined,
    close: () => undefined,
    remove: () => undefined
  }};
}};
global.RGBColor = function() {{ this.red = 0; this.green = 0; this.blue = 0; }};
global.IllustratorSaveOptions = function() {{}};
global.Compatibility = {{ ILLUSTRATOR8: 8 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
global.DocumentColorSpace = {{ RGB: 'RGB', CMYK: 'CMYK' }};
global.UserInteractionLevel = {{ DONTDISPLAYALERTS: 0 }};
function makeFrame() {{
  let contents = '';
  const frame = {{
    textRange: {{ characterAttributes: {{ size: 12 }}, paragraphAttributes: {{}} }},
    visibleBounds: [0, 10, 20, 0],
    characters: [],
    translate: () => undefined,
    createOutline: () => ({{ geometricBounds: [0, 10, 20, 0], resize: () => undefined, translate: () => undefined, rotate: () => undefined }})
  }};
  Object.defineProperty(frame, 'contents', {{
    get: () => contents,
    set: value => {{
      contents = String(value);
      frame.characters = Array.from(contents, () => ({{ characterAttributes: {{}} }}));
    }}
  }});
  frames.push(frame);
  return frame;
}}
const layer = {{
  textFrames: {{ add: () => makeFrame() }},
  pathItems: {{ rectangle: () => ({{ filled: false, stroked: false }}) }}
}};
const doc = {{ layers: [layer], saveAs: () => undefined, close: () => undefined }};
global.app = {{ documents: {{ add: () => doc }}, textFonts: [], redraw: () => undefined, executeMenuCommand: () => undefined }};
new Function(source)();
const frame = frames.find(item => item.contents === 'A|B|C|D');
if (!frame) throw new Error('personalized frame missing');
const letters = [0, 2, 4, 6].map(index => {{
  const attributes = frame.characters[index].characterAttributes;
  const color = attributes.fillColor;
  const stroke = attributes.strokeColor;
  return [[color.red, color.green, color.blue], [stroke.red, stroke.green, stroke.blue], attributes.strokeWeight];
}});
const expected = [
  [[255, 0, 0], [255, 0, 0], 0.4],
  [[255, 255, 255], [255, 255, 255], 0.4],
  [[255, 0, 0], [255, 0, 0], 0.4],
  [[255, 255, 255], [255, 255, 255], 0.4]
];
if (JSON.stringify(letters) !== JSON.stringify(expected)) throw new Error(JSON.stringify(letters));
if (frame.characters[1].characterAttributes.fillColor !== undefined) throw new Error('delimiter was recolored');
console.log(JSON.stringify(letters));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_department_rules_are_loaded_from_config():
    rules = load_department_rules()
    k_rule = resolve_department_rule("K", rules)
    h_rule = resolve_department_rule("H", rules)
    shop_rules = rules["shop_rules"]

    assert k_rule["label_fields"] == ["order_no", "color_option"]
    assert k_rule["label_lines"] == [["order_no"], ["color_option"]]
    assert k_rule["annotation_type"] == "COLOR"
    assert k_rule["apply_color_to_artwork"] is False
    assert h_rule["label_fields"] == ["order_no"]
    assert h_rule["apply_color_to_artwork"] is True
    assert "实际效果图" in shop_rules["interpretation"]
    assert "执行最终部门排版和成品格式" in shop_rules["current_render_policy"]
    assert shop_rules["global_requirements"]["must_pathfinder_merge"] is True
    assert shop_rules["global_requirements"]["default_output_color_mode"] == "CMYK"
    assert shop_rules["global_requirements"]["allowed_output_color_modes"] == ["CMYK", "RGB"]
    assert shop_rules["global_requirements"]["size_frame_text_path_overlap"] is True
    assert "去重很重要" in shop_rules["global_requirements"]["outline_dedupe_note"]
    k_output = next(rule for rule in shop_rules["department_output_requirements"] if rule["name"] == "K")
    h_output = next(rule for rule in shop_rules["department_output_requirements"] if rule["name"] == "H")
    pw_output = next(rule for rule in shop_rules["department_output_requirements"] if rule["name"] == "PW_EW")
    d_output = next(rule for rule in shop_rules["department_output_requirements"] if rule["name"] == "D_CONTAINS")
    assert k_output["layout"]["frame_width_mm"] == 480
    assert k_output["single_order_ai"] is True
    assert k_output["annotation_type"] == "COLOR"
    assert h_output["exportUnit"] == "PER_GRAPHIC"
    assert h_output["fileFormat"] == "PNG_CMYK"
    assert h_output["fillActualColor"] is True
    assert h_output["cropMasterHeight"] is True
    assert pw_output["annotation_type"] == "PRODUCT_NAME"
    assert pw_output["single_order_ai"] is True
    assert pw_output["hasMaster"] is True
    assert d_output["annotation_type"] == "PRODUCT_NAME"
    assert d_output["single_order_ai"] is True
    assert d_output["hasMaster"] is False
    assert k_output["artwork_content"] == "订单号 + 字体颜色 + 效果图"
