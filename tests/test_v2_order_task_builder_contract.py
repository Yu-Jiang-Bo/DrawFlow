from types import SimpleNamespace

import pytest

from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputUnit
from src.service.v2_order_task_builder import V2OrderTaskBuilderError, build_v2_order_task
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA


def test_multiple_units_are_rejected_before_the_first_unit_can_be_rendered(tmp_path, monkeypatch):
    rule = resolve_department_output("K")
    calls = []

    def fake_build_execution_task(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"pure": True}

    monkeypatch.setattr("src.service.v2_order_task_builder.build_v2_execution_task", fake_build_execution_task)

    with pytest.raises(V2OrderTaskBuilderError) as exc_info:
        build_v2_order_task(
            _compiled_task(),
            template_ai=tmp_path / "template.ai",
            units=(_unit(rule, "D3", "Cara"), _unit(rule, "D4", "Dana")),
            output_ai=tmp_path / "ORDER-3.ai",
            rule=rule,
            fixed_canvas=None,
            progress={},
        )

    message = str(exc_info.value)
    assert exc_info.value.code == "v2_order_task_units_multiple"
    assert calls == []
    assert "暂不能直接处理" in message
    assert all(token not in message for token in ("JSON", "JSX", "C:\\", "Traceback", "COM", "HRESULT"))


def _unit(rule, detail_id: str, name: str) -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no="ORDER-3",
        detail_id=detail_id,
        department=rule.department or "K",
        manufacturer=rule.manufacturer,
        product_name="Product",
        color_option="Gold",
        payload=SimpleNamespace(
            output_key="Output_main",
            values={"name": name},
            selections={"Output_main": {"font": "F10", "design": "Design03"}},
        ),
        rule=rule,
    )


def _compiled_task() -> dict:
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "a" * 64,
        "option_mappings": [],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "copy_option_group",
                        "group": "font",
                        "option_key": "F10",
                        "object_path": "Template/Output_main/Font/F10",
                    },
                    {
                        "type": "copy_option_group",
                        "group": "design",
                        "option_key": "Design03",
                        "object_path": "Template/Output_main/Design/Design03",
                    },
                ],
            }
        ],
    }
