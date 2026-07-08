from src.service.web_page import INDEX_HTML


def test_render_page_exposes_parse_test_and_render_actions():
    assert 'id="dryRunBtn"' in INDEX_HTML
    assert "解析测试" in INDEX_HTML
    assert "生成效果图" in INDEX_HTML
    assert "/download/render_task" in INDEX_HTML
    assert "render-task-panel" in INDEX_HTML
    assert "只解析订单并生成 render task JSON" in INDEX_HTML
    assert "清空当前订单文件和任务结果" in INDEX_HTML


def test_render_page_has_progress_overlay():
    assert 'id="renderProgressOverlay"' in INDEX_HTML
    assert 'id="progressBar"' in INDEX_HTML
    assert "showProgress" in INDEX_HTML
    assert "tickProgress" in INDEX_HTML
    assert "调用 Illustrator" in INDEX_HTML
    assert "生成 AI 文件" in INDEX_HTML
    assert 'return ["上传订单表格", "解析订单字段", "调用 Illustrator", "生成 AI 文件", "完成收尾"]' in INDEX_HTML


def test_template_rule_compile_uses_progress_overlay():
    assert 'showProgress("templateRule")' in INDEX_HTML
    assert "正在编译模板规则" in INDEX_HTML
    assert "正在调用规则编译服务，请不要重复点击" in INDEX_HTML
    assert "setTemplateRulePreviewDisabled" in INDEX_HTML
    assert 'return ["提交规则内容", "调用规则编译", "生成业务说明", "完成收尾"]' in INDEX_HTML


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
    assert "尺寸规则" in INDEX_HTML
    assert "describeDimensions" in INDEX_HTML
    assert "默认色彩模式" in INDEX_HTML
    assert "输出色彩" in INDEX_HTML
    assert "describeOutputSettings" in INDEX_HTML


def test_template_asset_list_has_download_and_delete_actions():
    assert "data-template-download" not in INDEX_HTML
    assert "data-template-delete" not in INDEX_HTML
    assert "data-asset-download" in INDEX_HTML
    assert "data-asset-delete" in INDEX_HTML
    assert 'data-asset-delete="primary"' in INDEX_HTML
    assert "disabled title=\"尺寸/作图区模板" not in INDEX_HTML
    assert "deleteTemplateAsset(" in INDEX_HTML
    assert "结构配置" in INDEX_HTML
    assert "template_rules_config" in INDEX_HTML
    assert "window.confirm" in INDEX_HTML
    assert 'id="referenceAiFile"' in INDEX_HTML
    assert "简单模板可只传这一项" in INDEX_HTML
    assert "尺寸/作图区模板（可选" in INDEX_HTML
    assert "尺寸/作图区模板" in INDEX_HTML
    assert "独立设计模板" in INDEX_HTML
    assert "displayTemplateAiRole" in INDEX_HTML
