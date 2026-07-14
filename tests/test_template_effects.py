import pytest

from src.service.template_effects import (
    TemplateEffectError,
    compile_text_effects,
    validate_template_effects,
)


def effect(action_type, value, *, positions="all", when=None):
    item = {
        "stage": "text",
        "target": {"field": "text", "name": "Name"},
        "selector": {"type": "split", "delimiter": "|", "positions": positions, "trim": True},
        "actions": [{"type": action_type, "value": value}],
    }
    if when:
        item["when"] = when
    return item


def test_compiles_multiple_actions_without_template_specific_branch():
    rules = {
        "effects": [
            effect(
                "set_fill_color",
                {"type": "cycle", "values": ["#D71920", "#FFFFFF"]},
            ),
            effect("set_tracking", {"type": "literal", "value": 25}, positions="odd"),
        ]
    }

    result = compile_text_effects(" Alice | Bob | Carol ", "text", "Name", rules)

    assert result == [
        {
            "type": "set_fill_color",
            "ranges": [
                {"start": 1, "length": 5, "value": "#D71920"},
                {"start": 9, "length": 3, "value": "#FFFFFF"},
                {"start": 15, "length": 5, "value": "#D71920"},
            ],
        },
        {
            "type": "set_tracking",
            "ranges": [
                {"start": 1, "length": 5, "value": 25},
                {"start": 15, "length": 5, "value": 25},
            ],
        },
    ]


def test_effect_condition_uses_current_option_selections():
    rules = {
        "effects": [
            effect(
                "set_font_size",
                {"type": "literal", "value": 18},
                when={"selections": {"font": ["F2", "F3"]}},
            )
        ]
    }

    assert compile_text_effects("Alice", "text", "Name", rules, {"font": "F1"}) == []
    assert compile_text_effects("Alice", "text", "Name", rules, {"font": "F2"})[0]["type"] == "set_font_size"


def test_validation_rejects_code_execution_and_non_numeric_values():
    effects = [
        effect("run_script", {"type": "literal", "value": "alert(1)"}),
        effect("set_tracking", {"type": "cycle", "values": [10, "wide"]}),
    ]

    errors = validate_template_effects(
        effects,
        {"text": "names"},
        [{"field": "text", "slot": "Name"}],
        [],
    )

    assert any("run_script" in message for message in errors)
    assert any("numeric values" in message for message in errors)


def test_validation_rejects_invalid_colors_numbers_and_conditions():
    effects = [
        effect("set_fill_color", {"type": "literal", "value": "not-a-color"}),
        effect("set_font_size", {"type": "literal", "value": "nan"}),
        effect(
            "set_tracking",
            {"type": "literal", "value": 10},
            when={"selections": {"template_profile": ["special"]}},
        ),
        effect(
            "set_tracking",
            {"type": "literal", "value": 10},
            when={"selections": {"font": []}},
        ),
    ]

    errors = validate_template_effects(
        effects,
        {"text": "names"},
        [{"field": "text", "slot": "Name"}],
        [],
    )

    assert any("named color or 6-digit hex" in message for message in errors)
    assert any("numeric values" in message for message in errors)
    assert any("unsupported selection field: template_profile" in message for message in errors)
    assert any("at least one option value: font" in message for message in errors)


def test_validation_rejects_selector_fields_not_supported_by_editor():
    item = effect("set_tracking", {"type": "literal", "value": 10})
    item["selector"]["indices"] = [1, 3]

    errors = validate_template_effects(
        [item],
        {"text": "names"},
        [{"field": "text", "slot": "Name"}],
        [],
    )

    assert any("unsupported selector keys: indices" in message for message in errors)


def test_validation_and_compiler_reject_bare_action_values():
    item = effect("set_fill_color", {"type": "literal", "value": "#FF0000"})
    item["actions"][0]["value"] = "#FF0000"

    errors = validate_template_effects(
        [item],
        {"text": "names"},
        [{"field": "text", "slot": "Name"}],
        [],
    )

    assert any("literal or cycle object" in message for message in errors)
    with pytest.raises(TemplateEffectError, match="literal or cycle object"):
        compile_text_effects("Alice", "text", "Name", {"effects": [item]})


def test_compiler_fails_closed_if_validation_is_bypassed():
    rules = {"effects": [effect("run_script", {"type": "literal", "value": "x"})]}

    with pytest.raises(TemplateEffectError, match="run_script"):
        compile_text_effects("Alice", "text", "Name", rules)
