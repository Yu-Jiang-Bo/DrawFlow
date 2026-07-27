import json
from pathlib import Path

import pytest

from src.service.production_output import (
    ProductionOutputError,
    ProductionOutputUnit,
    color_frames,
    partition_output_units,
    single_order_outputs,
    write_batch_task_files,
)


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


def test_shared_planner_uses_parenthesized_names_for_duplicate_order_artwork(tmp_path):
    outputs = single_order_outputs(
        [
            make_unit(order_no="ORD-1", department="T", detail_id="1"),
            make_unit(order_no="ORD-1", department="T", detail_id="2"),
            make_unit(order_no="ORD-2", department="T", detail_id="3"),
        ],
        Path(tmp_path) / "single-orders",
    )

    assert [output.output_path.name for output in outputs] == ["ORD-1(1).ai", "ORD-1(2).ai", "ORD-2.ai"]
    assert [output.arcname for output in outputs] == [
        "single-orders/ORD-1(1).ai",
        "single-orders/ORD-1(2).ai",
        "single-orders/ORD-2.ai",
    ]


def test_generic_batch_jsx_executes_child_tasks_by_script_path():
    source = Path("scripts/illustrator/render_batch.jsx").read_text(encoding="utf-8")

    assert 'task.type !== "render_batch"' in source
    assert 'var scriptPath = String(entry.script || "");' in source
    assert 'var childTaskPath = String(entry.task_file || entry.task_path || "");' in source
    assert "$.evalFile(File(scriptPath))" in source


def test_color_frame_composer_copies_only_top_level_source_items():
    source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")

    assert "source.pageItems.length" not in source
    assert "var sourceLayer = source.layers[sourceLayerIndex];" in source
    assert "if (sourceItem.parent !== sourceLayer) continue;" in source
    assert "copy.translate(frameLeft - sourceArtboard[0], height - sourceArtboard[1]);" in source


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
