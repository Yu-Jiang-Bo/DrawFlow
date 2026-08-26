from __future__ import annotations

import pytest

from src.service.multi_template_canary import CanaryRepresentative, CanarySelectionError, RepresentativeOrderSelector
from src.service.multi_template_order import MultiTemplateOrderBatch, MultiTemplateOrderRow, TemplateOrderGroup
from src.service.multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult


def _group(template_id="TEMPLATE-A"):
    rows = (
        MultiTemplateOrderRow("订单", 2, "A-1", template_id, {"定制信息": "Short", "数量": 1}),
        MultiTemplateOrderRow("订单", 3, "A-2", template_id, {"定制信息": "A much longer name", "数量": 1}),
        MultiTemplateOrderRow("订单", 4, "A-3", template_id, {"定制信息": "Longest", "数量": 1}),
    )
    return TemplateOrderGroup(template_id, rows)


def test_selector_uses_planned_units_then_text_length_then_excel_row_without_io():
    group = _group()
    selected = RepresentativeOrderSelector().select(
        group,
        {"row_metrics": {
            "2": {"planned_output_units": 2, "variable_text_length": 50},
            "3": {"planned_output_units": 3, "variable_text_length": 10},
            "4": {"planned_output_units": 3, "variable_text_length": 40},
        }},
        group_workbook_sha256="a" * 64,
    )

    assert (selected.template_id, selected.excel_row, selected.order_no) == ("TEMPLATE-A", 4, "A-3")
    assert (selected.planned_output_units, selected.variable_text_length) == (3, 40)
    assert selected.group_workbook_sha256 == "a" * 64
    assert CanaryRepresentative.from_dict(selected.to_dict()) == selected


def test_selector_rejects_a_plan_without_real_row_metrics():
    group = TemplateOrderGroup("TEMPLATE-A", (
        MultiTemplateOrderRow("订单", 2, "A-1", "TEMPLATE-A", {"定制信息": "Longer", "购买数量": 1}),
        MultiTemplateOrderRow("订单", 3, "A-2", "TEMPLATE-A", {"定制信息": "A", "购买数量": 3}),
    ))

    with pytest.raises(CanarySelectionError, match="缺少"):
        RepresentativeOrderSelector().select(group, {"stats": {"outputs": 2}}, group_workbook_sha256="")


def test_selector_rejects_fractional_plan_metrics_instead_of_truncating_them():
    with pytest.raises(CanarySelectionError, match="无效"):
        RepresentativeOrderSelector().select(
            _group(),
            {"row_metrics": {
                "2": {"planned_output_units": 1.5, "variable_text_length": 1},
                "3": {"planned_output_units": 1, "variable_text_length": 1},
                "4": {"planned_output_units": 1, "variable_text_length": 1},
            }},
            group_workbook_sha256="",
        )

def test_selector_uses_the_earliest_excel_row_for_a_complete_risk_tie():
    group = _group()

    selected = RepresentativeOrderSelector().select(
        group,
        {"row_metrics": {
            "2": {"planned_output_units": 3, "variable_text_length": 20},
            "3": {"planned_output_units": 3, "variable_text_length": 20},
            "4": {"planned_output_units": 2, "variable_text_length": 100},
        }},
        group_workbook_sha256="",
    )

    assert selected.excel_row == 2


def test_selector_does_not_select_any_canary_when_parent_preflight_failed():
    group_a = _group("TEMPLATE-A")
    group_b = TemplateOrderGroup("TEMPLATE-B", (MultiTemplateOrderRow("订单", 5, "B-1", "TEMPLATE-B", {"Name": "Bob"}),))
    batch = MultiTemplateOrderBatch("订单", ("订单号", "模板"), (*group_a.rows, *group_b.rows), (group_a, group_b), ())
    result = MultiTemplatePreflightResult(
        "preflight_failed",
        "source-sha",
        "订单",
        batch,
        (),
        (
            MultiTemplateGroupPreflight("TEMPLATE-A", 3, (2, 3, 4), ("A-1", "A-2", "A-3"), "missing.xlsx", "sha-a", True, {}, {"row_metrics": {"2": {"planned_output_units": 4, "variable_text_length": 1}, "3": {"planned_output_units": 4, "variable_text_length": 1}, "4": {"planned_output_units": 4, "variable_text_length": 1}}}),
            MultiTemplateGroupPreflight("TEMPLATE-B", 1, (5,), ("B-1",), "missing.xlsx", "sha-b", False, {}, {}),
        ),
        (),
    )

    selected = RepresentativeOrderSelector().select_ready(result)

    assert selected == ()


def test_selector_reads_ready_group_plans_in_preflight_order():
    group_a = _group("TEMPLATE-A")
    group_b = TemplateOrderGroup("TEMPLATE-B", (MultiTemplateOrderRow("订单", 5, "B-1", "TEMPLATE-B", {"Name": "Bob"}),))
    batch = MultiTemplateOrderBatch("订单", ("订单号", "模板"), (*group_a.rows, *group_b.rows), (group_a, group_b), ())
    result = MultiTemplatePreflightResult(
        "ready",
        "source-sha",
        "订单",
        batch,
        (),
        (
            MultiTemplateGroupPreflight("TEMPLATE-A", 3, (2, 3, 4), ("A-1", "A-2", "A-3"), "missing.xlsx", "sha-a", True, {}, {"row_metrics": {"2": {"planned_output_units": 1, "variable_text_length": 1}, "3": {"planned_output_units": 4, "variable_text_length": 1}, "4": {"planned_output_units": 2, "variable_text_length": 1}}}),
            MultiTemplateGroupPreflight("TEMPLATE-B", 1, (5,), ("B-1",), "missing.xlsx", "sha-b", True, {}, {"row_metrics": {"5": {"planned_output_units": 2, "variable_text_length": 3}}}),
        ),
        (),
    )

    selected = RepresentativeOrderSelector().select_ready(result)

    assert [(item.template_id, item.excel_row, item.group_workbook_sha256) for item in selected] == [("TEMPLATE-A", 3, "sha-a"), ("TEMPLATE-B", 5, "sha-b")]
