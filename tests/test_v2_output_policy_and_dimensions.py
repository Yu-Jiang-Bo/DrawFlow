from pathlib import Path
from dataclasses import replace

from src.renderer.v2_template_renderer import build_v2_color_frames_task, build_v2_execution_task, build_v2_order_column_task
from src.service.v2_template_contract import V2ContractError, normalize_v2_template_contract
from src.service.v2_order_task_builder import V2OrderTaskBuilderError, build_v2_order_task, create_v2_component_reuse_strategy
from src.service.department_output import resolve_department_output
from tests.test_v2_render_task import compile_task, render_config, scan_evidence
from tests.test_v2_order_task_builder import V2Payload, _production_unit


def test_compiled_and_execution_tasks_carry_template_output_policy(tmp_path):
    config = render_config()
    config["output"] = {"outline_text": False, "pathfinder_merge": True}
    compiled = compile_task(config=config, scan=scan_evidence())
    assert compiled["output"] == {"outline_text": False, "pathfinder_merge": True}
    execution = build_v2_execution_task(
        compiled,
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "out.ai",
        values={"font": "F10", "design": "03", "name": "Alice"},
        selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}},
        output_key="Output_main",
    )
    assert execution["output"] == {"outline_text": False, "pathfinder_merge": True}


def test_order_column_task_carries_target_dimensions_and_policy(tmp_path):
    task = build_v2_order_column_task(
        input_ai_files=[tmp_path / "component.ai"],
        output_ai=tmp_path / "order.ai",
        input_order_nos=["4142227962"],
        target_dimensions={"width_mm": 300, "height_mm": 70, "tolerance_mm": 0.007},
        output_policy={"outline_text": True, "pathfinder_merge": False},
    )
    assert task["inputs"][0]["target_dimensions"]["width_mm"] == 300
    assert task["output"] == {"outline_text": True, "pathfinder_merge": False}


def test_order_column_task_omits_empty_per_input_dimensions(tmp_path):
    task = build_v2_order_column_task(
        input_ai_files=[tmp_path / "unstyled.ai", tmp_path / "sized.ai", tmp_path / "incomplete.ai"],
        output_ai=tmp_path / "order.ai",
        target_dimensions_by_input=[{}, {"width_mm": 300, "height_mm": 70}, {"width_mm": 300}],
    )

    assert "target_dimensions" not in task["inputs"][0]
    assert task["inputs"][1]["target_dimensions"] == {"width_mm": 300, "height_mm": 70}
    assert task["inputs"][2]["target_dimensions"] == {"width_mm": 300}


def test_color_frames_task_omits_empty_order_dimensions_and_preserves_mixed_dimensions(tmp_path):
    task = build_v2_color_frames_task(
        inputs=[
            {"path": str(tmp_path / "unstyled.ai"), "order_dimensions": [{}]},
            {
                "path": str(tmp_path / "mixed.ai"),
                "order_dimensions": [{}, {"width_mm": 300, "height_mm": 70}],
            },
            {"path": str(tmp_path / "incomplete.ai"), "order_dimensions": [{"width_mm": 300}]},
        ],
        output_ai=tmp_path / "summary.ai",
        master_packing={"target_width_mm": 480},
    )

    assert "order_dimensions" not in task["inputs"][0]
    assert task["inputs"][1]["order_dimensions"] == [None, {"width_mm": 300, "height_mm": 70}]
    assert task["inputs"][2]["order_dimensions"] == [{"width_mm": 300}]


def test_v2_order_builder_prefers_template_policy_over_department_defaults(tmp_path):
    rule = resolve_department_output("K")
    unit = _production_unit(
        order_no="4142227962",
        detail_id="D1",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Kyra"},
            selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}},
        ),
    )
    compiled = compile_task()
    compiled["output"] = {"outline_text": False, "pathfinder_merge": False}
    task = build_v2_order_task(
        compiled,
        template_ai=tmp_path / "template.ai",
        units=(unit,),
        output_ai=tmp_path / "out.ai",
        rule=rule,
    )
    assert task["output"]["outline_text"] is False
    assert task["output"]["pathfinder_merge"] is False


def test_v2_jsx_contains_final_object_fit_and_policy_gates():
    render_source = Path("scripts/illustrator/render_v2_template.jsx").read_text(encoding="utf-8")
    order_source = Path("scripts/illustrator/compose_v2_order_column.jsx").read_text(encoding="utf-8")
    color_source = Path("scripts/illustrator/compose_color_frames.jsx").read_text(encoding="utf-8")
    assert "applyOutputTransforms(doc, execution.output || task.output || {})" in render_source
    assert "fitRenderedOutput(renderedOutputItems, finalFitAction)" in render_source
    assert "outputBoundsWithinTargetRange(fitted, targetWidth, targetHeight, dimensions)" in render_source
    assert "var fitSafety = outputFitSafetyPoints(dimensions);" in render_source
    assert "return Math.min(0.003, dimensionTolerancePoints(dimensions) / 2);" in render_source
    assert "width > targetWidth || height > targetHeight" in render_source
    assert "width < targetWidth - epsilon || height < targetHeight - epsilon" in render_source
    assert "if (!policy || policy.outline_text !== true) return;" in render_source
    assert "fitCopiedArtwork(copied, input.target_dimensions || {})" in order_source
    assert "if (!policy || policy.outline_text !== true) return;" in order_source
    assert "fitCopiedArtwork(copy, item.target_dimensions || {})" in color_source
    assert "hasDimensionFields(requestedDimensions)" in color_source
    assert "if (targetWidth <= 0 || targetHeight <= 0) return;" in color_source
    assert "outputPolicy.outline_text !== false" in color_source


def test_v2_jsx_fixed_visuals_keep_the_original_design_position_reference():
    render_source = Path("scripts/illustrator/render_v2_template.jsx").read_text(encoding="utf-8")

    assert "var fixedVisualLayoutCache = [];" in render_source
    assert "captureFixedVisualLayout(renderedItems);" in render_source
    assert render_source.index("captureFixedVisualLayout(renderedItems);") < render_source.index(
        "for (var assetIndex = 0; assetIndex < actions.length; assetIndex++)"
    )
    assert render_source.index("captureFixedVisualLayout(renderedItems);") < render_source.index(
        "for (var replaceIndex = 0; replaceIndex < actions.length; replaceIndex++)"
    )
    assert "root: root," in render_source
    assert "sourceBounds: copyBounds(unionRenderableBounds([root]))" in render_source
    assert "function unionRenderableBounds(items)" in render_source
    assert "function unionNonFixedRenderableBounds(items)" in render_source
    assert "function positionFixedVisualLayouts(layouts)" in render_source
    assert "positionFixedVisualStatesForOutput(" in render_source
    assert "unionNonFixedRenderableBounds([layout.root])" in render_source
    assert "positionFixedVisualStatesForOutput(fixedStates, sourceBounds, unionBounds(items, true));" not in render_source
    assert render_source.index("if (execution.pack_order_blocks === true)") > render_source.index(
        "if (finalFitAction) fitRenderedOutput(renderedOutputItems, finalFitAction);"
    )


def test_public_component_strategy_uses_each_unit_style_and_department_fallback(tmp_path):
    rule = replace(resolve_department_output("K"), outline_text=False, pathfinder_merge=False)
    compiled = compile_task()
    compiled["outputs"][0]["actions"].append({
        "type": "fit_output_bounds",
        "group": "style",
        "style_key": "style2",
        "dimensions": {"width_mm": 300, "height_mm": 70, "tolerance_mm": 0.007},
    })
    unit = _production_unit(
        order_no="ORDER-2",
        detail_id="D2",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Kyra"},
            selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style2"}},
        ),
    )
    strategy = create_v2_component_reuse_strategy(compiled, template_ai=tmp_path / "template.ai")
    order_task = strategy.build_order_column_task(
        input_ai_files=[tmp_path / "component.ai"],
        input_order_nos=["ORDER-2"],
        units=(unit,),
        output_ai=tmp_path / "order.ai",
        rule=rule,
        label_lines=(),
        compatibility="Illustrator 8",
    )
    color_task = strategy.build_color_frames_task(
        inputs=[{"path": str(tmp_path / "order.ai"), "order_nos": ["ORDER-2"]}],
        units=(unit,),
        output_ai=tmp_path / "color.ai",
        master_packing={"target_width_mm": 480},
        rule=rule,
        compatibility="Illustrator 8",
    )
    assert order_task["inputs"][0]["target_dimensions"]["width_mm"] == 300
    assert color_task["inputs"][0]["order_dimensions"][0]["height_mm"] == 70
    assert color_task["output"] == {"outline_text": False, "pathfinder_merge": False}


def test_color_inputs_keep_dimensions_in_unit_order_for_duplicate_order_numbers(tmp_path):
    rule = resolve_department_output("K")
    compiled = compile_task()
    unit_a = _production_unit(order_no="ORDER-X", detail_id="A", color_option="White", rule=rule, payload=V2Payload("Output_main", {"font": "F10", "design": "03", "name": "A"}, {"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}}))
    unit_b = _production_unit(order_no="ORDER-X", detail_id="B", color_option="White", rule=rule, payload=V2Payload("Output_main", {"font": "F10", "design": "03", "name": "B"}, {"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}}))
    strategy = create_v2_component_reuse_strategy(compiled, template_ai=tmp_path / "template.ai")
    task = strategy.build_color_frames_task(
        inputs=[{"path": str(tmp_path / "order.ai"), "order_nos": ["ORDER-X", "ORDER-X"]}],
        units=(unit_a, unit_b), output_ai=tmp_path / "color.ai", master_packing={"target_width_mm": 480}, rule=rule,
    )
    assert len(task["inputs"][0]["order_dimensions"]) == 2


def test_component_reuse_fills_missing_dimension_from_the_batch_target(tmp_path):
    rule = resolve_department_output("K")
    compiled = compile_task()
    sized = _production_unit(
        order_no="ORDER-SIZED",
        detail_id="SIZED",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Sized"},
            selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}},
        ),
    )
    missing = _production_unit(
        order_no="ORDER-MISSING",
        detail_id="MISSING",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "missing", "name": "Tail"},
            selections={"Output_main": {"font": "F10", "design": "DesignMissing", "style": "styleMissing"}},
        ),
    )
    strategy = create_v2_component_reuse_strategy(compiled, template_ai=tmp_path / "template.ai")

    order_task = strategy.build_order_column_task(
        input_ai_files=[tmp_path / "sized.ai", tmp_path / "tail.ai"],
        input_order_nos=["ORDER-SIZED", "ORDER-MISSING"],
        units=(sized, missing),
        output_ai=tmp_path / "order.ai",
        rule=rule,
    )
    color_task = strategy.build_color_frames_task(
        inputs=[{"path": str(tmp_path / "order.ai"), "order_nos": ["ORDER-SIZED", "ORDER-MISSING"]}],
        unit_groups=((sized, missing),),
        units=(sized, missing),
        output_ai=tmp_path / "summary.ai",
        master_packing={"target_width_mm": 480},
        rule=rule,
    )

    expected = {"width_mm": 80.0, "height_mm": 50.0, "tolerance_mm": 0.007}
    assert [item["target_dimensions"] for item in order_task["inputs"]] == [expected, expected]
    assert color_task["inputs"][0]["order_dimensions"] == [expected, expected]
    assert color_task["inputs"][0]["target_dimensions"] == expected


def test_component_reuse_rejects_missing_dimension_when_the_batch_has_multiple_sizes(tmp_path):
    rule = resolve_department_output("K")
    compiled = compile_task()
    compiled["outputs"][0]["actions"].append({
        "type": "fit_output_bounds",
        "group": "style",
        "style_key": "style2",
        "dimensions": {"width_mm": 120, "height_mm": 60, "tolerance_mm": 0.007},
    })
    units = (
        _production_unit(
            order_no="ORDER-SMALL",
            detail_id="SMALL",
            color_option="White",
            rule=rule,
            payload=V2Payload(
                output_key="Output_main",
                values={"font": "F10", "design": "03", "name": "Small"},
                selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}},
            ),
        ),
        _production_unit(
            order_no="ORDER-LARGE",
            detail_id="LARGE",
            color_option="White",
            rule=rule,
            payload=V2Payload(
                output_key="Output_main",
                values={"font": "F10", "design": "03", "name": "Large"},
                selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style2"}},
            ),
        ),
        _production_unit(
            order_no="ORDER-MISSING",
            detail_id="MISSING",
            color_option="White",
            rule=rule,
            payload=V2Payload(
                output_key="Output_main",
                values={"font": "F10", "design": "missing", "name": "Tail"},
                selections={"Output_main": {"font": "F10", "design": "DesignMissing", "style": "styleMissing"}},
            ),
        ),
    )
    strategy = create_v2_component_reuse_strategy(compiled, template_ai=tmp_path / "template.ai")

    with __import__("pytest").raises(V2OrderTaskBuilderError) as exc_info:
        strategy.build_order_column_task(
            input_ai_files=[tmp_path / "small.ai", tmp_path / "large.ai", tmp_path / "tail.ai"],
            input_order_nos=[unit.order_no for unit in units],
            units=units,
            output_ai=tmp_path / "order.ai",
            rule=rule,
        )

    assert exc_info.value.code == "v2_order_task_dimensions_ambiguous"


def test_component_reuse_uses_selected_design_dimensions_when_template_has_no_style_dimensions(tmp_path):
    rule = resolve_department_output("K")
    unit = _production_unit(
        order_no="ORDER-NO-SIZE",
        detail_id="NO-SIZE",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Kyra"},
            selections={"Output_main": {"font": "F10", "design": "Design03", "style": "style1"}},
        ),
    )
    config = render_config()
    config["outputs"][0]["style"]["options"][0].pop("dimensions")
    strategy = create_v2_component_reuse_strategy(compile_task(config=config), template_ai=tmp_path / "template.ai")
    order_task = strategy.build_order_column_task(
        input_ai_files=[tmp_path / "component.ai"],
        input_order_nos=["ORDER-NO-SIZE"],
        units=(unit,),
        output_ai=tmp_path / "order.ai",
        rule=rule,
    )
    color_task = strategy.build_color_frames_task(
        inputs=[{"path": str(tmp_path / "order.ai"), "order_nos": ["ORDER-NO-SIZE"]}],
        units=(unit,),
        output_ai=tmp_path / "summary.ai",
        master_packing={"target_width_mm": 480},
        rule=rule,
    )

    expected = {"width_mm": 80.0, "height_mm": 50.0, "tolerance_mm": 0.007}
    assert order_task["inputs"][0]["target_dimensions"] == expected
    assert color_task["inputs"][0]["order_dimensions"] == [expected]


def test_component_reuse_uses_selected_design_dimensions_without_styles(tmp_path):
    rule = resolve_department_output("K")
    unit = _production_unit(
        order_no="ORDER-DESIGN-SIZE",
        detail_id="DESIGN-SIZE",
        color_option="White",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Kyra"},
            selections={"Output_main": {"font": "F10", "design": "Design03"}},
        ),
    )
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    scan["outputs"][0]["styles"] = []
    scan["outputs"][0]["designs"][0]["dimensions"] = {"width_mm": 155.035, "height_mm": 56.652}
    strategy = create_v2_component_reuse_strategy(compile_task(config=config, scan=scan), template_ai=tmp_path / "template.ai")

    task = strategy.build_order_column_task(
        input_ai_files=[tmp_path / "component.ai"],
        input_order_nos=["ORDER-DESIGN-SIZE"],
        units=(unit,),
        output_ai=tmp_path / "order.ai",
        rule=rule,
    )

    assert task["inputs"][0]["target_dimensions"] == {"width_mm": 155.035, "height_mm": 56.652, "tolerance_mm": 0.007}


def test_output_policy_rejects_non_boolean_values():
    config = render_config()
    config["output"] = {"outline_text": "false"}
    with __import__("pytest").raises(V2ContractError):
        normalize_v2_template_contract(config)
