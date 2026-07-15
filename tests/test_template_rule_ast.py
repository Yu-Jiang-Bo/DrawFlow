import pytest

from src.service.llm_rule_parser import LlmRuleParser
from src.service.template_rule_ast import (
    RULE_AST_SCHEMA,
    font_styles_from_ast,
    migrate_legacy_rule_ast,
    rule_source_hash,
    runtime_actions,
    validate_rule_ast,
)
from src.service.template_rule_compiler import compile_local_rule_ast, compile_rule_ast


def test_compiles_name_odd_even_colors_into_safe_cycle_ast():
    text = "Name列的数据，按照顺序，奇数位的渲染为红色，偶数位的渲染为白色，字体保持默认"

    ast = compile_local_rule_ast(text)

    assert ast["$schema"] == RULE_AST_SCHEMA
    assert ast["source_hash"] == rule_source_hash(text)
    assert ast["unresolved"] == []
    assert ast["rules"] == [
        {
            "id": "rule-1",
            "target": {"type": "text", "name": "Name"},
            "conditions": [],
            "selector": {"type": "segments", "delimiter": "|"},
            "operations": [
                {"type": "fill_color", "strategy": "cycle", "values": ["#FF0000", "#FFFFFF"]}
            ],
        }
    ]
    assert validate_rule_ast(ast, natural_text=text) == []


def test_compiles_multiple_font_boldness_clauses_without_a_row_limit():
    text = "F2/F3/F10/F11/F12 需要加粗 0.4；F5/F6/F7/F8/F9 需要加粗 0.5"

    ast = compile_local_rule_ast(text)

    assert ast["unresolved"] == []
    assert font_styles_from_ast(ast) == {
        "F2": {"boldness": 0.4},
        "F3": {"boldness": 0.4},
        "F10": {"boldness": 0.4},
        "F11": {"boldness": 0.4},
        "F12": {"boldness": 0.4},
        "F5": {"boldness": 0.5},
        "F6": {"boldness": 0.5},
        "F7": {"boldness": 0.5},
        "F8": {"boldness": 0.5},
        "F9": {"boldness": 0.5},
    }


def test_unknown_or_extra_actions_are_rejected_before_confirmation():
    text = "Name 加弧度"
    ast = compile_local_rule_ast(text)
    assert any("未识别" in message for message in validate_rule_ast(ast, natural_text=text))

    ast["rules"] = [
        {
            "id": "rule-1",
            "target": {"type": "text", "name": "Name"},
            "conditions": [],
            "selector": {"type": "whole"},
            "operations": [{"type": "run_script", "script": "alert(1)"}],
        }
    ]
    ast["unresolved"] = []
    errors = validate_rule_ast(ast, natural_text=text)
    assert any("不支持的动作" in message for message in errors)
    with pytest.raises(ValueError, match="无效的模板特殊规则"):
        runtime_actions(ast, target="Name", selections={})


def test_rejects_malformed_ast_field_types_from_llm_candidates():
    ast = migrate_legacy_rule_ast(font_style_rules=[{"font_options": ["F1"], "boldness": 0.4}])
    ast["rules"][0]["conditions"][0]["values"] = [{"id": "F1"}]
    assert any("非空字符串列表" in message for message in validate_rule_ast(ast))

    ast = migrate_legacy_rule_ast(font_style_rules=[{"font_options": ["F1"], "boldness": 0.4}])
    ast["rules"][0]["conditions"] = [
        {"field": "text", "operator": "not_empty", "values": {"bad": "shape"}}
    ]
    assert any("not_empty 条件不能包含" in message for message in validate_rule_ast(ast))

    ast = migrate_legacy_rule_ast(name_color_cycle={"delimiter": "|", "colors": ["Red", "Black"]})
    ast["source_hash"] = {"bad": "hash"}
    ast["rules"][0]["target"]["name"] = {"bad": "target"}
    errors = validate_rule_ast(ast)
    assert any("来源摘要格式无效" in message for message in errors)
    assert any("缺少有效文字目标" in message for message in errors)


def test_context_validation_rejects_unknown_targets_and_pipeline_actions():
    text = "Name 奇数红色偶数白色"
    ast = compile_local_rule_ast(text)

    unknown_target = validate_rule_ast(
        ast,
        natural_text=text,
        context={"pipeline": "generic_rules_only", "text_targets": ["Text1"], "require_known_targets": True},
    )
    unsupported_pipeline = validate_rule_ast(
        ast,
        natural_text=text,
        context={"pipeline": "jjmb_202508", "text_targets": ["Name"], "require_known_targets": True},
    )

    assert any("不存在的文字对象" in message for message in unknown_target)
    assert any("不受当前渲染管线" in message for message in unsupported_pipeline)


def test_context_validation_requires_configured_font_options_before_confirmation():
    ast = migrate_legacy_rule_ast(font_style_rules=[{"font_options": ["F2"], "boldness": 0.4}])

    errors = validate_rule_ast(
        ast,
        context={"pipeline": "generic_rules_only", "font_options": [], "require_known_font_options": True},
    )

    assert any("无法核对字体选项" in message for message in errors)


def test_font_equals_condition_is_validated_and_extracted_for_legacy_pipelines():
    ast = migrate_legacy_rule_ast(font_style_rules=[{"font_options": ["F2"], "boldness": 0.4}])
    ast["rules"][0]["conditions"][0]["operator"] = "equals"

    errors = validate_rule_ast(
        ast,
        context={
            "pipeline": "jjmb_202508",
            "font_options": ["F1"],
            "require_known_font_options": True,
        },
    )

    assert any("未配置的字体选项：F2" in message for message in errors)
    assert font_styles_from_ast(ast) == {"F2": {"boldness": 0.4}}


def test_runtime_conditions_can_match_bound_text_content():
    ast = migrate_legacy_rule_ast(name_color_cycle={"delimiter": "|", "colors": ["Red", "Black"]})
    ast["rules"][0]["conditions"] = [
        {"field": "text", "operator": "equals", "values": ["Alice|Bob"]}
    ]

    assert runtime_actions(ast, target="Name", selections={"text": "Alice|Bob"})
    assert runtime_actions(ast, target="Name", selections={"text": "Other"}) == []


def test_stroke_color_source_is_whitelisted():
    ast = migrate_legacy_rule_ast(font_style_rules=[{"font_options": ["F2"], "boldness": 0.4}])
    ast["rules"][0]["operations"][0]["color_source"] = "background"

    assert any("颜色来源仅支持 fill" in message for message in validate_rule_ast(ast))


def test_migrates_legacy_special_rules_and_compiles_runtime_actions():
    ast = migrate_legacy_rule_ast(
        name_color_cycle={"delimiter": "|", "colors": ["Red", "Black", "Blue"]},
        font_style_rules=[{"font_options": ["F2", "F3"], "boldness": 0.4}],
    )

    actions = runtime_actions(ast, target="Name", selections={"font": "F2"})

    assert [action["type"] for action in actions] == ["fill_color", "stroke_width"]
    assert actions[0]["values"] == ["#FF0000", "#000000", "#0000FF"]
    assert actions[0]["selector"] == {"type": "segments", "delimiter": "|"}
    assert actions[1]["value"] == 0.4


def test_rule_compiler_uses_llm_candidate_then_applies_local_validation(monkeypatch):
    text = "Name 按红色、黑色、蓝色循环"
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    candidate = compile_local_rule_ast(text)
    monkeypatch.setattr(parser, "_call_llm", lambda **kwargs: candidate)

    result = compile_rule_ast(parser, natural_text=text, context={"template_id": "T1"})

    assert result["errors"] == []
    assert result["compiler"] == {"source": "llm", "llm_configured": True}
    assert result["summary"] == ["Name 按 | 分段，循环填充 #FF0000 / #000000 / #0000FF"]


def test_llm_candidate_can_resolve_a_phrase_unknown_to_local_fallback(monkeypatch):
    text = "把 Name 整体填充为红色"
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    candidate = {
        "$schema": RULE_AST_SCHEMA,
        "version": 1,
        "source_hash": "",
        "rules": [
            {
                "id": "rule-1",
                "target": {"type": "text", "name": "Name"},
                "conditions": [],
                "selector": {"type": "whole"},
                "operations": [{"type": "fill_color", "strategy": "fixed", "values": ["#FF0000"]}],
            }
        ],
        "unresolved": [],
    }
    monkeypatch.setattr(parser, "_call_llm", lambda **kwargs: candidate)

    result = compile_rule_ast(
        parser,
        natural_text=text,
        context={"pipeline": "generic_rules_only", "text_targets": ["Name"], "require_known_targets": True},
    )

    assert result["errors"] == []
    assert result["ast"]["unresolved"] == []


def test_local_fallback_is_preview_only_when_llm_is_not_configured():
    text = "Name 奇数红色偶数白色"
    parser = LlmRuleParser(api_key="", base_url="")

    result = compile_rule_ast(
        parser,
        natural_text=text,
        context={"pipeline": "generic_rules_only", "text_targets": ["Name"]},
    )

    assert result["summary"] == ["Name 按 | 分段，循环填充 #FF0000 / #FFFFFF"]
    assert result["errors"][0] == "自然语言规则模型未配置，当前结果仅供预览，不能确认保存。"


def test_llm_failure_or_invalid_json_keeps_fallback_preview_blocked(monkeypatch):
    text = "Name 奇数红色偶数白色"
    parser = LlmRuleParser(api_key="key", base_url="https://example.test/v1")
    monkeypatch.setattr(parser, "_call_llm", lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid JSON")))

    result = compile_rule_ast(
        parser,
        natural_text=text,
        context={"pipeline": "generic_rules_only", "text_targets": ["Name"]},
    )

    assert result["summary"] == ["Name 按 | 分段，循环填充 #FF0000 / #FFFFFF"]
    assert result["errors"][0] == "模型调用失败，未更新规则：invalid JSON"
