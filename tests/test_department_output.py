from __future__ import annotations

import struct

from src.service.department_output import (
    ANNOTATION_COLOR,
    ANNOTATION_PRODUCT_NAME,
    build_department_deliveries,
    is_department_d,
    resolve_department_output,
    set_png_resolution,
    translate_color_to_chinese,
)


def test_h_only_delivers_one_fixed_master_png():
    rule = resolve_department_output("H")

    assert rule.output_format == "png_master"
    assert rule.extension == ".png"
    assert rule.layout["frame_width_mm"] == 580
    assert rule.layout["frame_height_mm"] == 2000
    assert rule.layout["dpi"] == 300


def test_w_only_has_two_manufacturer_exceptions():
    assert resolve_department_output("W", "MY-W196").output_format == "cs5_ai"
    assert resolve_department_output("W", "my w120").output_format == "png_per_item"
    assert resolve_department_output("W", "OTHER-FACTORY").output_format == "ai8"


def test_department_config_exposes_single_order_and_master_rules():
    t_rule = resolve_department_output("T")
    k_rule = resolve_department_output("K")
    zk_rule = resolve_department_output("ZK")
    pw_rule = resolve_department_output("PW")
    d_rule = resolve_department_output("Dept_D")

    assert t_rule.single_order_ai is True
    assert t_rule.annotation_type == ANNOTATION_COLOR
    assert t_rule.has_master is True
    assert t_rule.master_group_by_color is True
    assert t_rule.master_frame_width_mm == 580
    assert k_rule.master_frame_width_mm == 480
    assert zk_rule.master_frame_width_mm == 450
    assert pw_rule.single_order_ai is True
    assert pw_rule.annotation_type == ANNOTATION_PRODUCT_NAME
    assert pw_rule.has_master is True
    assert pw_rule.master_group_by_color is False
    assert d_rule.single_order_ai is True
    assert d_rule.annotation_type == ANNOTATION_PRODUCT_NAME
    assert d_rule.has_master is False


def test_department_d_matching_and_color_translation_are_standard():
    assert is_department_d("Dept_D") is True
    assert is_department_d("D_Group") is True
    assert is_department_d("d-line") is True
    assert is_department_d("ZK") is False
    assert translate_color_to_chinese("Red") == "红色"
    assert translate_color_to_chinese("Black") == "黑色"
    assert translate_color_to_chinese("Rose Gold") == "玫瑰金"
    assert translate_color_to_chinese("红色") == "红色"


def test_department_deliveries_keep_d_whole_and_w120_per_order_but_h_whole():
    deliveries = build_department_deliveries(
        [
            {"生产部门": "H", "内部订单号": "H-001"},
            {"生产部门": "H", "内部订单号": "H-002"},
            {"生产部门": "D-A", "内部订单号": "D-001"},
            {"生产部门": "D-A", "内部订单号": "D-002"},
            {"生产部门": "W", "厂家": "MY-W120", "内部订单号": "W-001"},
            {"生产部门": "W", "厂家": "MY-W120", "内部订单号": "W-002"},
            {"生产部门": "W", "厂家": "Factory-A", "内部订单号": "W-003"},
        ],
        base_name="batch",
    )

    assert [(delivery.rule.output_format, len(delivery.rows)) for delivery in deliveries] == [
        ("png_master", 2),
        ("ai8", 2),
        ("png_per_item", 1),
        ("png_per_item", 1),
        ("ai8", 1),
    ]
    assert deliveries[0].output_name == "batch-H-580x2000mm.png"
    assert deliveries[1].output_name == "batch-D-A.ai"
    assert deliveries[2].output_name == "batch-W-W-001.png"
    assert deliveries[3].output_name == "batch-W-W-002.png"


def test_set_png_resolution_writes_standard_phys_metadata(tmp_path):
    png = tmp_path / "output.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 10, 20, 8, 2, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )

    set_png_resolution(png, 300)

    data = png.read_bytes()
    phys_offset = data.index(b"pHYs")
    x_pixels_per_meter, y_pixels_per_meter, unit = struct.unpack(">IIB", data[phys_offset + 4 : phys_offset + 13])
    assert (x_pixels_per_meter, y_pixels_per_meter, unit) == (11811, 11811, 1)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    import zlib

    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
