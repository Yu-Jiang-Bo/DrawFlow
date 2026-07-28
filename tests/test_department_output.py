from __future__ import annotations

import struct

from src.service.department_output import (
    ANNOTATION_COLOR,
    ANNOTATION_PRODUCT_NAME,
    EXPORT_UNIT_PER_GRAPHIC,
    EXPORT_UNIT_PER_ORDER,
    FILE_FORMAT_AI_CS5,
    FILE_FORMAT_AI_STANDARD,
    FILE_FORMAT_PNG_CMYK,
    build_department_deliveries,
    finalize_cmyk_png,
    is_department_d,
    resolve_department_output,
    set_png_resolution,
    translate_color_to_chinese,
)


def test_h_delivers_per_graphic_pngs_and_cropped_master_png():
    rule = resolve_department_output("H")

    assert rule.output_format == "png_cmyk"
    assert rule.export_unit == EXPORT_UNIT_PER_GRAPHIC
    assert rule.file_format == FILE_FORMAT_PNG_CMYK
    assert rule.extension == ".png"
    assert rule.fill_actual_color is True
    assert rule.apply_color_to_artwork is True
    assert rule.has_master is True
    assert rule.crop_master_height is True
    assert rule.layout["frame_width_mm"] == 580
    assert rule.layout["frame_height_mm"] == 2000
    assert rule.layout["dpi"] == 300


def test_w_only_has_two_manufacturer_exceptions():
    w196 = resolve_department_output("W", "MY-W196")
    w120 = resolve_department_output("W", "my w120")
    other = resolve_department_output("W", "OTHER-FACTORY")

    assert w196.output_format == "cs5_ai"
    assert w196.export_unit == EXPORT_UNIT_PER_ORDER
    assert w196.file_format == FILE_FORMAT_AI_CS5
    assert w196.per_order is True
    assert w196.fill_actual_color is True
    assert w196.has_master is False
    assert w120.output_format == "png_cmyk"
    assert w120.export_unit == EXPORT_UNIT_PER_GRAPHIC
    assert w120.file_format == FILE_FORMAT_PNG_CMYK
    assert w120.fill_actual_color is True
    assert w120.has_master is False
    assert other.output_format == "ai_standard"
    assert other.file_format == FILE_FORMAT_AI_STANDARD
    assert other.ai_compatibility == FILE_FORMAT_AI_STANDARD
    assert other.per_order is True


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


def test_department_deliveries_split_h_and_w120_per_graphic_but_keep_d_whole():
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
        ("png_cmyk", 1),
        ("png_cmyk", 1),
        ("ai8", 2),
        ("png_cmyk", 1),
        ("png_cmyk", 1),
        ("ai_standard", 1),
    ]
    assert [delivery.output_name for delivery in deliveries] == [
        "H-001.png",
        "H-002.png",
        "batch-D-A.ai",
        "W-001.png",
        "W-002.png",
        "batch-W-W-003.ai",
    ]


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


def test_finalize_cmyk_png_rejects_non_cmyk_policy(tmp_path):
    png = tmp_path / "output.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 10, 20, 8, 2, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )

    try:
        finalize_cmyk_png(png, dpi=300, color_mode="RGB")
    except Exception as exc:
        assert "CMYK" in str(exc)
    else:
        raise AssertionError("non-CMYK PNG policy should be rejected")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    import zlib

    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
