from src.service.web_page import INDEX_HTML


def test_render_page_exposes_parse_test_and_render_actions():
    assert 'id="dryRunBtn"' in INDEX_HTML
    assert "解析测试" in INDEX_HTML
    assert "生成效果图" in INDEX_HTML
    assert "/download/render_task" in INDEX_HTML


def test_template_form_lists_supported_template_types():
    for template_type in [
        "pure_text",
        "pure_text_color_design",
        "pure_text_style",
        "curved_title_text",
        "annotated_ai",
        "asset_split",
    ]:
        assert f'value="{template_type}"' in INDEX_HTML
