from src.service.font_style_rules import (
    font_style_by_option,
    normalize_font_style_rules,
    strip_legacy_font_bold_overrides,
    validate_font_style_rules,
)


def test_normalizes_an_unbounded_font_boldness_rule_list():
    rules = [
        {"font_options": ["F2", "F3", "F10", "F11", "F12"], "boldness": "0.4"},
        {"font_options": ["F5", "F6", "F7", "F8", "F9"], "boldness": 0.5},
        {"font_options": [f"D{index}" for index in range(1, 13)], "boldness": 0.6},
    ]

    normalized = normalize_font_style_rules(rules)

    assert normalized == [
        {"font_options": ["F2", "F3", "F10", "F11", "F12"], "boldness": 0.4},
        {"font_options": ["F5", "F6", "F7", "F8", "F9"], "boldness": 0.5},
        {"font_options": [f"D{index}" for index in range(1, 13)], "boldness": 0.6},
    ]
    assert font_style_by_option(normalized)["F12"] == {"boldness": 0.4}
    assert font_style_by_option(normalized)["D12"] == {"boldness": 0.6}


def test_migrates_only_legacy_bold_rules_that_include_an_explicit_value():
    legacy = {
        "F1": {"action": "bold", "bold": True},
        "F2": {"action": "bold", "bold": True, "value": "加粗0.4"},
        "F3": {"bold": True, "boldness": 0.4},
        "F5": {"action": "uppercase"},
    }

    assert normalize_font_style_rules(None, legacy_option_overrides=legacy) == [
        {"font_options": ["F2", "F3"], "boldness": 0.4}
    ]
    assert normalize_font_style_rules([], legacy_option_overrides=legacy) == []


def test_strips_legacy_bold_overrides_after_their_values_are_migrated():
    legacy = {
        "F2": {"action": "bold", "bold": True, "value": "加粗0.4"},
        "F3": {"bold": True, "boldness": 0.4},
        "F5": {"action": "uppercase"},
    }

    assert strip_legacy_font_bold_overrides(legacy) == {"F5": {"action": "uppercase"}}


def test_reports_missing_values_and_duplicate_font_targets():
    assert validate_font_style_rules(
        [
            {"font_options": ["F2"], "boldness": 0.4},
            {"font_options": ["F2", "F3"], "boldness": 0},
            {"font_options": [], "boldness": 0.5},
        ]
    ) == [
        "字体加粗规则第 2 条的加粗值必须是大于 0 的数字。",
        "字体加粗规则第 2 条与第 1 条重复设置了字体 F2。",
        "字体加粗规则第 3 条至少选择一个目标字体。",
    ]
