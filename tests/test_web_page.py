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


def test_template_rule_editor_is_business_readable():
    assert "编译后的规则说明" in INDEX_HTML
    assert "结构化规则 JSON" not in INDEX_HTML
    assert "新建空白" not in INDEX_HTML
    assert "templateRulePreviewSignature" in INDEX_HTML
    assert "请先点击“生成预览”" in INDEX_HTML


def test_template_asset_list_has_download_and_delete_actions():
    assert "data-template-download" not in INDEX_HTML
    assert "data-template-delete" not in INDEX_HTML
    assert "data-asset-download" in INDEX_HTML
    assert "data-asset-delete" in INDEX_HTML
    assert 'data-asset-delete="primary"' in INDEX_HTML
    assert "disabled title=\"尺寸/作图区模板" not in INDEX_HTML
    assert "deleteTemplateAsset(" in INDEX_HTML
    assert "window.confirm" in INDEX_HTML
    assert 'id="referenceAiFile"' in INDEX_HTML
    assert "简单模板可只传这一项" in INDEX_HTML
    assert "尺寸/作图区模板（可选" in INDEX_HTML
    assert "尺寸/作图区模板" in INDEX_HTML
    assert "独立设计模板" in INDEX_HTML
    assert "displayTemplateAiRole" in INDEX_HTML
