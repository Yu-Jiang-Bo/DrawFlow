import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.service.production_output import (
    ProductionOutputError,
    ProductionOutputUnit,
    color_frames,
    graphic_outputs,
    master_packing_config,
    partition_output_units,
    requires_graphic_outputs,
    single_order_outputs,
    write_batch_task_files,
)
from src.service.department_output import resolve_department_output


def make_unit(*, order_no: str, department: str, color: str = "Gold", detail_id: str = "1") -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no=order_no,
        detail_id=detail_id,
        department=department,
        manufacturer="",
        product_name="测试产品",
        color_option=color,
        payload={"order_no": order_no},
        quantity_index=1,
        identity=detail_id,
    )


def test_batch_task_json_is_ascii_escaped_for_illustrator(tmp_path):
    paths = write_batch_task_files(
        tmp_path,
        [{"script": str(tmp_path / "渲染.jsx"), "task_file": str(tmp_path / "任务.json")}],
        chunk_size=1,
    )

    text = paths[0].read_text(encoding="utf-8")
    assert "渲染" not in text
    assert "任务" not in text
    assert json.loads(text)["tasks"][0]["script"].endswith("渲染.jsx")


def test_shared_planner_partitions_by_department_rule_and_color():
    batches = partition_output_units(
        [
            make_unit(order_no="T-1", department="T", color="Red"),
            make_unit(order_no="T-2", department="T", color="Black", detail_id="2"),
            make_unit(order_no="D-1", department="Dept_D"),
        ]
    )

    assert [batch.rule.name for batch in batches] == ["T", "D_CONTAINS"]
    assert [frame.color_option for frame in color_frames(batches[0].units)] == ["红色", "黑色"]
    assert batches[1].rule.has_master is False


def test_shared_planner_groups_equivalent_color_aliases_under_one_chinese_header():
    frames = color_frames(
        [
            make_unit(order_no="GOLD-EN", department="K", color="Gold"),
            make_unit(order_no="GOLD-ZH", department="K", color="金色", detail_id="2"),
        ]
    )

    assert len(frames) == 1
    assert frames[0].color_option == "金色"
    assert [unit.order_no for unit in frames[0].units] == ["GOLD-EN", "GOLD-ZH"]


def test_shared_planner_groups_duplicate_order_artwork_into_one_ai(tmp_path):
    outputs = single_order_outputs(
        [
            make_unit(order_no="ORD-1", department="T", detail_id="1"),
            make_unit(order_no="ORD-1", department="T", detail_id="2"),
            make_unit(order_no="ORD-2", department="T", detail_id="3"),
        ],
        Path(tmp_path) / "single-orders",
    )

    assert [output.output_path.name for output in outputs] == ["ORD-1.ai", "ORD-2.ai"]
    assert [output.arcname for output in outputs] == [
        "single-orders/ORD-1.ai",
        "single-orders/ORD-2.ai",
    ]
    assert [[unit.detail_id for unit in output.units] for output in outputs] == [["1", "2"], ["3"]]


def test_per_graphic_png_outputs_use_hyphen_numbering_for_duplicate_order_artwork(tmp_path):
    outputs = graphic_outputs(
        [
            make_unit(order_no="ORD-1", department="H", detail_id="1"),
            make_unit(order_no="ORD-1", department="H", detail_id="2"),
            make_unit(order_no="ORD-2", department="H", detail_id="3"),
        ],
        Path(tmp_path) / "single-graphics",
    )

    assert [output.output_path.name for output in outputs] == ["ORD-1-1.png", "ORD-1-2.png", "ORD-2.png"]
    assert [output.arcname for output in outputs] == [
        "single-graphics/ORD-1-1.png",
        "single-graphics/ORD-1-2.png",
        "single-graphics/ORD-2.png",
    ]
    assert requires_graphic_outputs(resolve_department_output("H")) is True
    assert requires_graphic_outputs(resolve_department_output("W", "MY-W120")) is True
    assert requires_graphic_outputs(resolve_department_output("W", "MY-W196")) is False


def test_generic_batch_jsx_executes_child_tasks_by_script_path():
    source = Path("scripts/illustrator/render_batch.jsx").read_text(encoding="utf-8")

    assert 'task.type !== "render_batch"' in source
    assert 'var scriptPath = String(entry.script || "");' in source
    assert 'var childTaskPath = String(entry.task_file || entry.task_path || "");' in source
    assert "$.evalFile(File(scriptPath))" in source


def test_h_png_master_composer_embeds_placed_pngs():
    source = Path("scripts/illustrator/compose_png_master_pages.jsx").read_text(encoding="utf-8")
    compose_body = source[source.index("function composePage"):source.index("function drawLabel")]

    assert "var previewBackground = task.preview_background || {};" in source
    assert "PREVIEW_BACKGROUND_NON_PRINTING" in source
    assert "previewLayer.printable = previewBackground.non_printing !== true;" in source
    assert "drawPreviewBackground(previewLayer, imageLeft, imageTop, placement.imageWidth, placement.imageHeight);" in compose_body
    assert compose_body.index("drawPreviewBackground(previewLayer") < compose_body.index("var placed = layer.placedItems.add();")
    assert "var placed = layer.placedItems.add();" in source
    assert "placed.file = File(String(item.png_path));" in source
    assert "placed.embed();" in source
    assert "Failed to embed PNG in H master AI" in source
    assert 'String(task.compatibility || "CS5")' in source
    assert "Compatibility.ILLUSTRATOR15" in source
    assert "function drawPreviewBackground" in source
    assert "function previewBackgroundColor" in source
    assert "function clampPercent" in source
    assert "drawWhiteBackground(" not in compose_body


def test_h_png_master_composer_javascript_parses_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source_file = tmp_path / "compose.js"
    source_file.write_text(
        Path("scripts/illustrator/compose_png_master_pages.jsx").read_text(encoding="utf-8").replace("#target illustrator", "", 1),
        encoding="utf-8",
    )

    result = subprocess.run(
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

    assert result.returncode == 0, result.stderr


def test_color_frame_composer_packs_order_segments_by_adaptive_grid():
    source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")

    assert "source.pageItems.length" not in source
    assert "adaptive_column_grid" in source
    assert "function collectOrderBlocks(source)" in source
    assert 'task.compatibility || "Illustrator 8"' in source
    assert "Compatibility.ILLUSTRATOR15" in source
    assert 'item.typename !== "GroupItem"' in source
    assert "if (sourceItem.parent !== sourceLayer) continue;" in source
    assert "collectNamedPackItemsByOrder(sourceItem, byIndex)" in source
    assert "function collectNamedPackItemsByOrder(item, byIndex)" in source
    assert "parseOrderBlockIndex(item.name)" in source
    assert "ensureOrderEntry(byIndex, blockIndex).block = item;" in source
    assert "parseOrderItemName(item.name)" in source
    assert "ensureOrderEntry(byIndex, itemIndex.orderIndex).subItems.push" in source
    assert "function parseOrderBlockIndex(name)" in source
    assert "ORDER_PACK_BLOCK_(\\d+)" in source
    assert "function pageItemBounds(item)" in source
    assert "item.visibleBounds" in source
    assert "item.geometricBounds" in source
    assert "function collectOrderSubItems(orderItem)" in source
    assert "parseOrderItemIndex(item.name)" in source
    assert "function parseOrderItemIndex(name)" in source
    assert "function parseOrderItemName(name)" in source
    assert "ORDER_PACK_ITEM_(\\d+)_(\\d+)" in source
    assert "var namedItems = namedPackItems(result);" in source
    assert "parseOrderBlockIndex(orderItem.name) >= 0" in source
    assert "if (result.length > 1) return sortByStablePackIndex(result);" in source
    assert "function namedPackItems(items)" in source
    assert "function sortByStablePackIndex(items)" in source
    assert "function packAdaptiveGrid(" in source
    assert "var keepOrderItemsTogether = packing.keep_order_items_together === true;" in source
    assert "function placeWholeOrderIntoColumn(" in source
    assert "if (keepOrderItemsTogether === true)" in source
    assert "function packColorFrameBlocks(plans, width, gap)" in source
    assert "targetHeight = Math.max(targetHeight, plans[planIndex].frameHeight);" in source
    assert "function findBestColorFrameColumn(columns, frameHeight, targetHeight, gap)" in source
    assert "current = findBestColorFrameColumn(columns, plan.frameHeight, targetHeight, gap);" in source
    assert "if (nextHeight > targetHeight + 0.01) continue;" in source
    assert "remaining < bestRemaining - 0.01" in source
    assert "plan.frameY = current.height + needsGap;" in source
    assert "plan.frameLeft = current.index * (width + gap);" in source
    assert "function placeOrderIntoColumns(" in source
    assert "function findBestColumnWindow(" in source
    assert "var idealRows = Math.max(1, Math.ceil(subItemCount / maxColumns));" in source
    assert "boundary.stroked = colorFrameBoundary;" in source
    assert "boundary.strokeColor = redColor();" in source
    assert "function redColor()" in source
    assert "function updateFragmentMetadata(placements)" in source
    assert "placement.fragmentCount = total;" in source
    assert "placement.split = total > 1;" in source
    assert "label_scope: \"order_segment\"" in source
    assert "copy.translate(destinationLeft - copiedBounds[0], destinationTop - copiedBounds[1]);" in source
    assert "coordinate_unit: \"mm\"" in source
    assert "function auditColumns(columns)" in source
    assert "function auditFragments(placements)" in source
    assert "function auditColorFrameLayout(frameLayout)" in source
    assert "algorithm: \"best_fit_color_frame_columns\"" in source
    assert "frame_y_mm: roundMm(plan.frameY)" in source
    assert "frame_column: plan.frameColumn" in source
    assert "frame_boundary_stroked: colorFrameBoundary" in source
    assert "color_frame_layout: auditColorFrameLayout(frameLayout)" in source
    assert "split: placement.split === true" in source
    assert "label_required: true" in source


def test_color_frame_composer_best_fit_backfills_existing_frame_columns(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is required to execute the Illustrator packing helper")

    source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")
    source = "\n".join(
        line
        for index, line in enumerate(source.splitlines())
        if not (index == 0 and line.startswith("#target"))
    )
    script = f"""
const vm = require('vm');
const context = {{
  __COLOR_FRAME_PACK_TEST__: {{
    width: 480,
    gap: 4,
    plans: [
      {{ colorOption: 'A', frameHeight: 100 }},
      {{ colorOption: 'B', frameHeight: 30 }},
      {{ colorOption: 'C', frameHeight: 70 }},
      {{ colorOption: 'D', frameHeight: 20 }},
      {{ colorOption: 'E', frameHeight: 40 }}
    ]
  }}
}};
vm.runInNewContext({json.dumps(source)}, context);
console.log(JSON.stringify(context.__COLOR_FRAME_PACK_TEST__.result));
"""
    script_path = tmp_path / "run-compose-color-frame-pack-test.js"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script_path)],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    assert result["width"] == 1448
    assert result["height"] == 100
    assert [[plan["colorOption"] for plan in column["plans"]] for column in result["columns"]] == [
        ["A"],
        ["B", "E"],
        ["C", "D"],
    ]
    assert [plan["frameColumn"] for plan in result["columns"][1]["plans"]] == [1, 1]
    assert [plan["frameY"] for plan in result["columns"][1]["plans"]] == [0, 34]


def test_color_frame_adaptive_grid_can_keep_order_items_in_one_column(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is required to execute the Illustrator packing helper")

    source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")
    source = "\n".join(
        line
        for index, line in enumerate(source.splitlines())
        if not (index == 0 and line.startswith("#target"))
    )
    script = f"""
const vm = require('vm');
const context = {{
  __COLOR_FRAME_PACK_TEST__: {{
    mode: 'adaptive_grid',
    width: 240,
    verticalGap: 6,
    columnGap: 4,
    labelHeight: 10,
    labelGap: 2,
    cellPadding: 0,
    slackRows: 0,
    colorOption: 'W196',
    keepOrderItemsTogether: true,
    orders: [
      {{
        sourceIndex: 0,
        orderNo: 'ORDER1',
        items: [
          {{ sourceChildIndex: 0, width: 40, height: 20 }},
          {{ sourceChildIndex: 1, width: 40, height: 20 }}
        ]
      }},
      {{
        sourceIndex: 1,
        orderNo: 'ORDER2',
        items: [
          {{ sourceChildIndex: 0, width: 40, height: 20 }}
        ]
      }}
    ]
  }}
}};
vm.runInNewContext({json.dumps(source)}, context);
console.log(JSON.stringify(context.__COLOR_FRAME_PACK_TEST__.result));
"""
    script_path = tmp_path / "run-compose-adaptive-grid-pack-test.js"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        ["node", str(script_path)],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    order1_fragments = [
        placement for placement in result["placements"] if placement["orderNo"] == "ORDER1"
    ]

    assert len(order1_fragments) == 1
    assert order1_fragments[0]["itemCount"] == 2
    assert order1_fragments[0]["split"] is False
    assert [item["sourceChildIndex"] for item in order1_fragments[0]["items"]] == [0, 1]


def test_master_packing_config_uses_department_width_and_configured_spacing():
    packing = master_packing_config(resolve_department_output("K"))

    assert packing == {
        "algorithm": "adaptive_column_grid",
        "target_width_mm": 480.0,
        "item_gap_mm": 2.0,
        "column_gap_mm": 2.0,
        "outer_margin_mm": 2.0,
        "header_height_mm": 7.0,
        "color_gap_mm": 4.0,
        "label_height_mm": 4.0,
        "label_gap_mm": 0.8,
        "row_slack": 1,
        "cell_width_padding_mm": 0.8,
        "component_suppress_labels": True,
        "force_subitem_order_labels": False,
        "keep_order_items_together": False,
        "allow_rotation": False,
    }


def test_batch_tasks_use_absolute_paths_for_illustrator_child_evaluation(tmp_path):
    batch = write_batch_task_files(
        tmp_path / "jobs",
        [{"script": "scripts/illustrator/render_202508_grouped.jsx", "task_file": str(tmp_path / "child.json")}],
        chunk_size=20,
    )[0]

    entry = json.loads(batch.read_text(encoding="utf-8"))["tasks"][0]
    assert Path(entry["script"]).is_absolute()
    assert Path(entry["task_file"]).is_absolute()


def test_batch_tasks_reject_an_incomplete_child_entry(tmp_path):
    with pytest.raises(ProductionOutputError, match="script and task_file"):
        write_batch_task_files(tmp_path / "jobs", [{"script": "render.jsx"}], chunk_size=20)
