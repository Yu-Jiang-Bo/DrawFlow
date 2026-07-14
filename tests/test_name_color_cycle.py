from src.service.name_color_cycle import normalize_name_color_cycle, validate_name_color_cycle


def test_normalizes_an_unbounded_name_color_cycle():
    colors = ["#d71920", "#000000", "#0000ff", "#00aa00", "#ffaa00", "#663399"]

    assert normalize_name_color_cycle({"delimiter": "|", "colors": colors}) == {
        "delimiter": "|",
        "colors": [color.upper() for color in colors],
    }


def test_validates_required_delimiter_minimum_colors_and_hex_values():
    assert validate_name_color_cycle({"delimiter": "", "colors": ["#D71920"]}) == [
        "Name 多色循环请填写分隔符。",
        "Name 多色循环至少需要两个颜色。",
    ]
    assert validate_name_color_cycle({"delimiter": "|", "colors": ["#D71920", "red"]}) == [
        "Name 多色循环第 2 个颜色必须为 #RRGGBB 格式。"
    ]
