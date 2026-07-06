from src.jjmb_202509_curved_main import (
    build_task,
    clean_text,
    group_items,
    normalize_font,
    parse_custom_info,
    parse_items,
    split_names,
)


def test_parse_custom_info_extracts_font_title_and_names():
    parsed = parse_custom_info(
        "Style Option:4 People\n"
        "Font Options:F14\n"
        "Title:Merry Christmas 2025\n"
        "Name:1. Mom\n"
        "2. Taylor"
    )

    assert parsed["font"] == "F14"
    assert parsed["title"] == "Merry Christmas 2025"
    assert parsed["names"] == "1. Mom\n2. Taylor"


def test_split_names_accepts_numbered_inline_and_multiline_values():
    assert split_names("1. Kai\n2. Jc\n3. Noah") == ["Kai", "Jc", "Noah"]
    assert split_names("1. Tanya   2. Neel   3.Ansh") == ["Tanya", "Neel", "Ansh"]
    assert split_names("1. Jose, 2. Kaylee , 3. Vienna") == ["Jose", "Kaylee", "Vienna"]
    assert split_names("Azamat\nAnna\nAlan\nAdam") == ["Azamat", "Anna", "Alan", "Adam"]


def test_clean_text_decodes_html_entities_and_strips_markers():
    assert clean_text("4. LiL&#39; Alex") == "LiL' Alex"


def test_normalize_font_defaults_invalid_values_to_f1():
    assert normalize_font("F14") == "F14"
    assert normalize_font("") == "F1"
    assert normalize_font("F99") == "F1"


def test_parse_items_adds_default_title_when_title_missing():
    rows = [
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "生产部门": "ZW",
            "定制信息": "Font Options:F3\nName:1. Kai\n2. Jc",
        }
    ]

    group = group_items(parse_items(rows))[0]

    assert group.order_no == "ORDER1"
    assert [(item.text_type, item.text) for item in group.items] == [
        ("name", "Kai"),
        ("name", "Jc"),
        ("title", "Merry Christmas"),
    ]


def test_group_items_keeps_different_detail_rows_separate():
    rows = [
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "生产部门": "ZW",
            "定制信息": "Font Options:F3\nName:1. Kai",
        },
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "2",
            "生产部门": "ZW",
            "定制信息": "Font Options:F14\nName:1. Nora",
        },
    ]

    groups = group_items(parse_items(rows))

    assert [group.order_no for group in groups] == ["ORDER1", "ORDER1"]
    assert [[item.text for item in group.items] for group in groups] == [
        ["Kai", "Merry Christmas"],
        ["Nora", "Merry Christmas"],
    ]


def test_build_task_can_keep_title_frames(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    groups = group_items(
        parse_items(
            [
                {
                    "模板": "JJMB202509231236046265",
                    "内部订单号": "ORDER1",
                    "订单明细id": "1",
                    "生产部门": "ZW",
                    "定制信息": "Font Options:F1\nName:Kai",
                }
            ]
        )
    )

    task = build_task(report, tmp_path / "out.ai", groups, columns=1, keep_title_frames=True)

    assert task["layout"]["keep_title_frames"] is True
    assert task["font_map"]["F1"]["bounds_shape_ratio"] == {}
