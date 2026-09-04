import pytest

from src.service.production_output import ProductionOutputError, validate_public_output_units
from src.service.v2_order_plan import V2OrderRenderUnit, build_v2_order_units, to_production_units
from src.service.v2_order_render_support import V2OrderRenderError


def _config(*, multi_quantity: bool = False) -> dict:
    config = {
        "field_bindings": {
            "order_no": "Order No",
            "detail_id": "Detail ID",
            "department": "Dept",
            "manufacturer": "Factory",
            "product_name": "Product",
            "color": "Font Color",
            "name": "Name",
        }
    }
    if multi_quantity:
        config["field_bindings"]["quantity"] = "Qty"
        config["multi_name_customization"] = {"enabled": True}
    return config


def _render_task() -> dict:
    return {
        "template": {"template_id": "V2ORDER001", "version": "v0007"},
        "config": {"warnings": [{"code": "layout_soft_warning", "message": "Check layout manually"}]},
        "outputs": [
            {"key": "Output_front"},
            {"key": "Output_back"},
        ],
    }


def _preflight(*, row: int = 1, order_id: str = "PF-ORDER") -> dict:
    return {
        "preflight_rows": [
            {
                "row": row,
                "order_id": order_id,
                "outputs": [
                    {"output": "Output_front", "style": "S", "design": "D1", "font": "F1"},
                    {"output": "Output_back", "style": "M", "design": "D2", "font": "F2"},
                ],
            }
        ]
    }


def _row(department: str, *, manufacturer: str = "", order_no: str = "ORD-1", detail_id: str = "LINE-1") -> dict:
    return {
        "Order No": order_no,
        "Detail ID": detail_id,
        "Dept": department,
        "Factory": manufacturer,
        "Product": "Bracelet",
        "Font Color": "Gold",
        "Name": "Alice",
    }


@pytest.mark.parametrize(
    ("department", "manufacturer", "rule_name"),
    [
        ("T", "", "T"),
        ("K", "", "K"),
        ("ZK", "", "ZK_FK"),
        ("FK", "", "ZK_FK"),
        ("PW", "", "PW_EW"),
        ("EW", "", "PW_EW"),
        ("H", "", "H"),
        ("Dept-D", "", "D_CONTAINS"),
        ("W", "MY-W196", "W_CONTAINS"),
        ("W", "MY-W120", "W_CONTAINS"),
        ("W", "OTHER-W", "W_CONTAINS"),
    ],
)
def test_v2_order_units_convert_representative_departments_to_public_units(department, manufacturer, rule_name):
    units = build_v2_order_units(_config(), _render_task(), [_row(department, manufacturer=manufacturer)], _preflight())

    production_units = validate_public_output_units(to_production_units(_config(), units))

    assert len(production_units) == 2
    assert [unit.order_no for unit in production_units] == ["ORD-1", "ORD-1"]
    assert [unit.detail_id for unit in production_units] == ["LINE-1", "LINE-1"]
    assert [unit.department for unit in production_units] == [department, department]
    assert [unit.manufacturer for unit in production_units] == [manufacturer, manufacturer]
    assert [unit.product_name for unit in production_units] == ["Bracelet", "Bracelet"]
    assert [unit.color_option for unit in production_units] == ["Gold", "Gold"]
    assert [unit.rule.name for unit in production_units] == [rule_name, rule_name]
    assert [unit.payload.output_key for unit in production_units] == ["Output_front", "Output_back"]
    assert [unit.payload.output_index for unit in production_units] == [1, 2]
    assert [unit.payload.template_version for unit in production_units] == ["v0007", "v0007"]
    assert [unit.payload.render_warnings for unit in production_units] == [
        ("Check layout manually",),
        ("Check layout manually",),
    ]


def test_v2_order_unit_identity_keeps_output_order_and_quantity_sequence_stable():
    config = _config(multi_quantity=True)
    row = {**_row("T"), "Qty": "2"}

    units = build_v2_order_units(config, _render_task(), [row], _preflight())
    production_units = to_production_units(config, units)

    assert [unit.payload.output_key for unit in production_units] == [
        "Output_front",
        "Output_back",
        "Output_front",
        "Output_back",
    ]
    assert [unit.quantity_index for unit in production_units] == [1, 1, 2, 2]
    assert [unit.identity for unit in production_units] == [
        "LINE-1|output:001|qty:001|row:001",
        "LINE-1|output:002|qty:001|row:001",
        "LINE-1|output:001|qty:002|row:001",
        "LINE-1|output:002|qty:002|row:001",
    ]


def test_v2_order_unit_metadata_can_fall_back_to_preflight_metadata():
    config = {"field_bindings": {"name": "Name"}}
    preflight = {
        "preflight_rows": [
            {
                "row": 1,
                "order_id": "PF-ORDER",
                "metadata": {
                    "detail_id": "PF-LINE",
                    "department": "K",
                    "manufacturer": "",
                    "product_name": "Pendant",
                    "color": "Black",
                },
                "outputs": [{"output": "Output_front", "font": "F1"}],
            }
        ]
    }
    render_task = {"template": {"version": "v0008"}, "outputs": [{"key": "Output_front"}]}

    production_units = validate_public_output_units(
        to_production_units(config, build_v2_order_units(config, render_task, [{"Name": "Alice"}], preflight))
    )

    assert len(production_units) == 1
    assert production_units[0].order_no == "PF-ORDER"
    assert production_units[0].detail_id == "PF-LINE"
    assert production_units[0].department == "K"
    assert production_units[0].product_name == "Pendant"
    assert production_units[0].color_option == "Black"
    assert production_units[0].payload.template_version == "v0008"


def test_v2_order_units_recognize_standard_jjmb_metadata_headers_without_bindings():
    config = {
        "field_bindings": {
            "name": "定制信息",
            "font": "字体",
            "style": "尺寸",
            "color": "字体颜色",
        }
    }
    row = {
        "内部订单号": "ORD-JJMB",
        "订单明细id": "DETAIL-JJMB",
        "生产部门": "K",
        "厂家": "",
        "产品中文名称": "吊坠",
        "字体颜色": "Gold",
        "定制信息": "Alice",
    }

    production_units = validate_public_output_units(
        to_production_units(config, build_v2_order_units(config, _render_task(), [row], _preflight()))
    )

    assert [unit.order_no for unit in production_units] == ["ORD-JJMB", "ORD-JJMB"]
    assert [unit.detail_id for unit in production_units] == ["DETAIL-JJMB", "DETAIL-JJMB"]
    assert [unit.department for unit in production_units] == ["K", "K"]
    assert [unit.product_name for unit in production_units] == ["吊坠", "吊坠"]


def test_v2_order_units_prefer_standard_jjmb_metadata_headers_when_aliases_overlap():
    config = {"field_bindings": {"name": "定制信息", "color": "字体颜色"}}
    row = {
        "内部订单号": "ORD-JJMB",
        "订单明细id": "STANDARD-DETAIL",
        "明细id": "OTHER-DETAIL",
        "生产部门": "K",
        "产品中文名称": "标准产品",
        "产品名称": "其他产品",
        "字体颜色": "Gold",
        "定制信息": "Alice",
    }

    production_units = to_production_units(
        config,
        build_v2_order_units(config, _render_task(), [row], _preflight()),
    )

    assert [unit.detail_id for unit in production_units] == ["STANDARD-DETAIL", "STANDARD-DETAIL"]
    assert [unit.product_name for unit in production_units] == ["标准产品", "标准产品"]


def test_v2_order_unit_uses_selected_custom_color_binding_for_public_metadata():
    config = {
        "field_bindings": {"front_color": "正面颜色"},
        "outputs": [
            {
                "key": "Output_main",
                "design": {"options": [{"key": "D1", "slots": [{"color_binding": "front_color"}]}]},
                "font": {"options": [{"key": "F1", "slots": [{"color_binding": "color"}]}]},
            }
        ],
    }
    unit = V2OrderRenderUnit(
        row_index=1,
        row={},
        row_preflight={},
        output_key="Output_main",
        values={
            "detail_id": "DETAIL-1",
            "department": "K",
            "product_name": "Pendant",
            "color": "Red",
            "front_color": "Gold",
        },
        selections={"Output_main": {"design": "D1", "font": "F1"}},
        order_id="ORDER-1",
        template_version="v0001",
    )

    production_unit = to_production_units(config, [unit])[0]

    assert production_unit.color_option == "Gold"


def test_v2_public_gate_rejects_missing_department_without_technical_trace():
    units = to_production_units(_config(), build_v2_order_units(_config(), _render_task(), [_row("")], _preflight()))

    with pytest.raises(ProductionOutputError) as exc_info:
        validate_public_output_units(units)

    message = str(exc_info.value)
    assert "Traceback" not in message
    assert "$." not in message
    assert ":\\" not in message


def test_v2_public_gate_rejects_missing_w_manufacturer_without_losing_w_context():
    units = to_production_units(_config(), build_v2_order_units(_config(), _render_task(), [_row("W")], _preflight()))

    with pytest.raises(ProductionOutputError) as exc_info:
        validate_public_output_units(units)

    message = str(exc_info.value)
    assert units[0].department == "W"
    assert units[0].manufacturer == ""
    assert "Traceback" not in message
    assert "$." not in message
    assert ":\\" not in message


def test_v2_production_units_reject_missing_template_version():
    render_task = _render_task()
    render_task["template"]["version"] = ""
    units = build_v2_order_units(_config(), render_task, [_row("T")], _preflight())

    with pytest.raises(V2OrderRenderError) as exc_info:
        to_production_units(_config(), units)

    assert "模板版本" in str(exc_info.value)


@pytest.mark.parametrize(
    ("field_name", "expected_message"),
    [
        ("Order No", "订单号"),
        ("Detail ID", "订单明细号"),
        ("Product", "产品名称"),
        ("Font Color", "字体颜色"),
    ],
)
def test_v2_public_gate_rejects_missing_required_metadata(field_name, expected_message):
    row = _row("T")
    row[field_name] = ""
    preflight = _preflight(order_id="" if field_name == "Order No" else "PF-ORDER")
    units = to_production_units(_config(), build_v2_order_units(_config(), _render_task(), [row], preflight))

    with pytest.raises(ProductionOutputError) as exc_info:
        validate_public_output_units(units)

    message = str(exc_info.value)
    assert expected_message in message
    assert "Traceback" not in message
    assert "$." not in message
    assert ":\\" not in message
