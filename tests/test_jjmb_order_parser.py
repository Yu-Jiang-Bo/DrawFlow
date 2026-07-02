from src.jjmb_order_parser import (
    parse_custom_info,
    parse_order_items,
    split_personalization,
)
from src.jjmb_template_main import expand_values
from src.jjmb_combined_main import combined_personalization_text


def test_parse_custom_info_with_multiline_personalization():
    parsed = parse_custom_info(
        "Style Option:Style 2\n"
        "Font Option:F3\n"
        "Personalization:Mr Clarke\n"
        "Mrs Clarke"
    )

    assert parsed["style_option"] == "Style 2"
    assert parsed["font_option"] == "F3"
    assert parsed["personalization"] == "Mr Clarke\nMrs Clarke"


def test_split_personalization_by_lines_and_pipe():
    assert split_personalization("A\nB\nC") == ["A", "B", "C"]
    assert split_personalization("A|B|C") == ["A", "B", "C"]


def test_parse_order_items_normalizes_options():
    rows = [
        {
            "内部订单号": "4013367078",
            "订单明细id": "2313435",
            "购买数量": "2",
            "模板": "JJMB202603281027102517",
            "定制信息": "Style Option:Style 2\nFont Option:F3\nPersonalization:Mr Clarke\nMrs Clarke",
        }
    ]

    items = parse_order_items(rows, template_id="JJMB202603281027102517")

    assert len(items) == 1
    assert items[0].order_no == "4013367078"
    assert items[0].detail_id == "2313435"
    assert items[0].quantity == 2
    assert items[0].style_option == "Style2"
    assert items[0].font_option == "F3"
    assert items[0].personalization_values == ["Mr Clarke", "Mrs Clarke"]


def test_expand_values_does_not_duplicate_by_quantity():
    item = parse_order_items(
        [
            {
                "内部订单号": "401",
                "订单明细id": "1",
                "购买数量": "5",
                "模板": "JJMB202603281027102517",
                "定制信息": "Style Option:Style 1\nFont Option:F1\nPersonalization:Only One",
            }
        ],
        template_id="JJMB202603281027102517",
    )[0]

    assert expand_values(item) == ["Only One"]


def test_combined_sheet_keeps_multiline_personalization_together():
    assert combined_personalization_text(["A", "B", "C"]) == "A\nB\nC"
