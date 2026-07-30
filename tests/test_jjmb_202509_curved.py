from pathlib import Path

from src.jjmb_202509_curved_main import (
    build_task,
    CurvedOrderGroup,
    CurvedOrderItem,
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


def test_clean_text_preserves_numeric_title_values():
    assert clean_text("2025") == "2025"
    assert clean_text("2025 Family") == "2025 Family"
    assert clean_text("2. 2025") == "2025"


def test_parse_custom_info_numeric_title_survives_cleaning():
    parsed = parse_custom_info("Title: 2025\nName:1. Dustin")

    assert clean_text(parsed["title"]) == "2025"


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


def test_parse_items_repeats_each_complete_name_and_title_group_by_quantity():
    rows = [
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "生产部门": "ZW",
            "购买数量": "3",
            "定制信息": "Font Options:F3\nTitle:Family\nName:1. Kai\n2. Jc",
        }
    ]

    groups = group_items(parse_items(rows, multi_name_customization=True))

    assert len(groups) == 3
    assert [group.order_no for group in groups] == ["ORDER1", "ORDER1", "ORDER1"]
    assert [[(item.text_type, item.text) for item in group.items] for group in groups] == [
        [("name", "Kai"), ("name", "Jc"), ("title", "Family")],
        [("name", "Kai"), ("name", "Jc"), ("title", "Family")],
        [("name", "Kai"), ("name", "Jc"), ("title", "Family")],
    ]


def test_parse_items_rejects_invalid_quantity_when_multi_name_customization_enabled():
    rows = [
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "购买数量": "1.5",
            "定制信息": "Name:Kai",
        }
    ]

    try:
        parse_items(rows, multi_name_customization=True)
    except ValueError as exc:
        assert str(exc) == "支持多姓名定制的订单数量必须是正整数。"
    else:
        raise AssertionError("invalid quantity should stop the curved render task")


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


def test_build_task_can_keep_debug_frames(tmp_path):
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

    task = build_task(report, tmp_path / "out.ai", groups, columns=1, keep_title_frames=True, keep_name_frames=True)

    assert task["layout"]["keep_title_frames"] is True
    assert task["layout"]["keep_name_frames"] is True
    assert task["output"]["color_mode"] == "CMYK"
    assert task["output"]["pathfinder_merge"] is True
    assert task["font_map"]["F1"]["bounds_shape_ratio"] == {}


def test_build_task_applies_layout_dimension_overrides(tmp_path):
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

    task = build_task(
        report,
        tmp_path / "out.ai",
        groups,
        columns=1,
        color_mode="RGB",
        layout_overrides={
            "name_width_mm": 18,
            "name_height_mm": 6,
            "title_width_mm": 42,
            "title_height_mm": 8,
        },
    )

    assert task["layout"]["name_width_mm"] == 18.0
    assert task["layout"]["name_height_mm"] == 6.0
    assert task["layout"]["title_width_mm"] == 42.0
    assert task["layout"]["title_height_mm"] == 8.0
    assert task["output"]["color_mode"] == "RGB"


def test_build_task_can_request_internal_quality_preview(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    groups = group_items(
        parse_items(
            [{"模板": "JJMB202509231236046265", "内部订单号": "ORDER1", "订单明细id": "1", "定制信息": "Name:Kai"}]
        )
    )

    task = build_task(report, tmp_path / "out.ai", groups, columns=1, preview_png=tmp_path / "preview.png")

    assert task["output"]["preview_png_path"].endswith("preview.png")
    assert task["output"]["preview_dpi"] == 300


def test_build_task_includes_named_title_template_ai(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    title_template = tmp_path / "title-design.ai"
    title_template.write_text("ai", encoding="utf-8")
    groups = [
        CurvedOrderGroup(
            order_no="ORDER1",
            items=[
                CurvedOrderItem(
                    order_no="ORDER1",
                    detail_id="1",
                    department="ZW",
                    font_option="F1",
                    text="2025",
                    text_type="title",
                    quantity_index=1,
                )
            ],
        )
    ]

    task = build_task(report, tmp_path / "out.ai", groups, columns=1, title_template_ai=title_template)

    assert task["title_template"]["ai_path"] == str(title_template.resolve())
    assert task["title_template"]["text_name_pattern"] == "TITLE_{font}_TEXT"
    assert task["title_template"]["bounds_name_pattern"] == "TITLE_{font}_BOUNDS"


def test_curved_renderer_outlines_and_merges_each_text_item_independently():
    source = Path("scripts/illustrator/render_202509_curved.jsx").read_text(encoding="utf-8")
    outline_body = source[source.index("function outlineText(items, reportProgress)"):source.index("function failRender")]
    outline_loop = source[
        source.index("function outlineText(items, reportProgress)") : source.index("function outlineTextEntry")
    ]
    fit_body = source[source.index("function fitPageItemToRect"):source.index("function alignPageItemToRect")]

    assert "cleanupOutline(outline);" in source
    assert "function cleanupOutlines(items)" not in source
    assert 'failRender("Text outline failed at item " + (i + 1)' in source
    assert "var itemTextItems = packOrderBlocks && outputConfig.outline_text ? [] : textItems;" in source
    assert "if (outputConfig.outline_text) outlineText(itemTextItems, false);" in source
    assert "cleanupStats.failed += 1;" in source
    assert "var OUTLINE_BATCH_SIZE = 25;" in source
    assert "function shouldSettleOutlineBatch(processed, total)" in source
    assert outline_body.count("settleIllustrator();") == 1
    assert "writeRenderDebug(\"outlining\", \"\", 0);" in outline_body
    assert "for (var i = 0; i < FIT_ITERATIONS; i++)" in fit_body
    assert "app.redraw()" not in fit_body
    assert "function settleIllustrator()" in source
    assert 'writeRenderDebug("failed", message, itemIndex);' in source
    assert "doc.close(SaveOptions.DONOTSAVECHANGES);" in source
    assert "function exportPreviewPNG(doc, file, dpi)" in source
    assert 'failRender("Failed to save AI or export preview: "' in source
    assert 'previewPath.replace(/\\.png$/i, "")' in source
    assert "Preview PNG was not generated." in source
    assert 'textItems.push({ item: tf, rect: frameRect, fitMode: "contain" });' in source
    assert 'outlineChildren: !isTextFrame(clonedText)' in source
    assert "function outlineTextEntry(entry, itemIndex)" in source
    assert "function collectTextFrames(container)" in source
    assert "function addTextFrame(frames, frame)" in source
    assert "var outline = source.createOutline();" in source
    assert "outlineTextEntry(entry, i + 1);" in outline_loop
    assert "source.createOutline();" not in outline_loop
    assert "safeErrorText(e0)" in outline_loop
    assert 'failRender("Layout failed: " + safeErrorText(error), 0);' in source
    assert 'failRender("Failed to save AI or export preview: " + safeErrorText(e1), 0);' in source
    assert "function drawCurvedTitleFromTemplate(layer, text, fontOption" in source
    assert "TITLE_{font}_TEXT" in source
    assert "sourceText.duplicate(layer, ElementPlacement.PLACEATEND)" in source
    assert "titleTemplateStats.used += 1;" in source
    assert "titleTemplate: titleTemplateStats" in source
    assert "abortRenderUnexpected(eLayout);" in source
    assert "function abortRenderUnexpected(error)" in source
    assert "function pageItemBounds(item)" in source
    assert "function fitOutlinedEntry(item, entry)" in source
    assert "fitPageItemWithinRect(item, entry.rect);" in source
    assert "function fitPageItemWithinRect(item, rect)" in source
    assert "Math.min(targetW / w, targetH / h)" in source
    assert "Math.min(1, targetW / w, targetH / h)" not in source
    assert "function clampPageItemToRect(item, rect)" in source
    assert "preview.fsName" not in source
    assert "Cannot open render task JSON." in source
    assert '"Cannot open JSON: " + file.fsName' not in source
    assert source.index("saveAsAI(doc, output, String(outputConfig.compatibility || \"Illustrator 8\"));") < source.index("savedDoc = app.open(output);")
    assert source.index("savedDoc = app.open(output);") < source.index("exportPreviewPNG(savedDoc")
    assert "if (doc) doc.close(SaveOptions.DONOTSAVECHANGES);" in source
