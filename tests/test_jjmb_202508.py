from src.jjmb_202508_main import (
    DEFAULT_COLOR,
    DEFAULT_DESIGN,
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
    assert items[0].production_label == "ORDER1  Gold  Meg"
    assert items[0].show_frame is False
    assert items[1].apply_color_to_artwork is True
    assert items[1].show_color_label is False
    assert items[1].color_option == DEFAULT_COLOR
    assert items[1].design_option == DEFAULT_DESIGN
    assert items[1].production_label == "ORDER2  Amy"
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
    assert items[1].production_label == "ORDER4  皮质首饰盒  Black"
    assert items[1].show_frame is False


def test_department_rules_are_loaded_from_config():
    rules = load_department_rules()
    k_rule = resolve_department_rule("K", rules)
    h_rule = resolve_department_rule("H", rules)

    assert k_rule["label_fields"] == ["order_no", "color_option", "text"]
    assert k_rule["apply_color_to_artwork"] is False
    assert h_rule["label_fields"] == ["order_no", "text"]
    assert h_rule["apply_color_to_artwork"] is True
