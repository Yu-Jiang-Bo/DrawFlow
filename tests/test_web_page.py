from src.service.web_page import INDEX_HTML


def test_render_page_exposes_single_render_action():
    assert 'id="dryRunBtn"' not in INDEX_HTML
    assert 'id="resetTaskBtn"' not in INDEX_HTML
    assert 'id="taskMessage"' not in INDEX_HTML
    assert 'id="resultJobId"' not in INDEX_HTML
    assert 'id="resultStatus"' not in INDEX_HTML
    assert 'id="resultItems"' not in INDEX_HTML
    assert 'id="resultDownload"' not in INDEX_HTML
    assert 'id="renderTemplateStatus"' not in INDEX_HTML
    assert 'id="templateStatusBadge"' not in INDEX_HTML
    assert 'id="recentJobs"' not in INDEX_HTML
    assert 'id="refreshJobsBtn"' not in INDEX_HTML
    assert "生成效果图" in INDEX_HTML
    assert "/download/render_task" in INDEX_HTML
    assert "render-task-panel" in INDEX_HTML
    assert "render-layout" in INDEX_HTML
    assert "只解析订单并生成 render task JSON" not in INDEX_HTML
    assert "清空当前订单文件和任务结果" not in INDEX_HTML
    assert "当前模板状态" not in INDEX_HTML
    assert "最近任务" not in INDEX_HTML


def test_render_page_uses_business_error_dialog():
    assert 'id="renderErrorOverlay"' in INDEX_HTML
    assert 'role="alertdialog"' in INDEX_HTML
    assert "showRenderError" in INDEX_HTML
    assert "explainRenderError" in INDEX_HTML
    assert "非技术" not in INDEX_HTML
    assert "请先上传订单表格" in INDEX_HTML
    assert "模板缺少本次订单需要的字体样本或字体规则" in INDEX_HTML


def test_render_page_has_progress_overlay():
    assert 'id="renderProgressOverlay"' in INDEX_HTML
    assert 'id="progressBar"' in INDEX_HTML
    assert "showProgress" in INDEX_HTML
    assert "tickProgress" in INDEX_HTML
    assert "调用 Illustrator" in INDEX_HTML
    assert "生成 AI 文件" in INDEX_HTML
    assert 'return ["上传订单表格", "解析订单字段", "调用 Illustrator", "生成 AI 文件", "完成收尾"]' in INDEX_HTML


def test_template_rule_form_uses_structured_check():
    assert 'id="newTemplateBtn"' in INDEX_HTML
    assert 'id="checkTemplateRuleBtn"' in INDEX_HTML
    assert "新增模板" in INDEX_HTML
    assert "检查规则" in INDEX_HTML
    assert "规则检查结果" in INDEX_HTML
    assert "模板特有规则" not in INDEX_HTML
    assert "编译后的规则说明" not in INDEX_HTML
    assert "正在编译模板规则" not in INDEX_HTML
    assert "setTemplateRulePreviewDisabled" not in INDEX_HTML


def test_template_rule_preview_normalizes_object_options():
    assert "function normalizeOptions" in INDEX_HTML
    assert "function optionText" in INDEX_HTML
    assert 'values.join(" / ")' not in INDEX_HTML


def test_template_form_hides_type_and_status_from_user():
    assert 'id="templateType"' not in INDEX_HTML
    assert 'id="templateStatus"' not in INDEX_HTML
    assert 'form.append("template_type", buildTemplateRulePayload().template_type)' in INDEX_HTML
    assert 'form.append("status", "draft")' in INDEX_HTML
    assert "function inferTemplateTypeFromForm" in INDEX_HTML
    assert "内部模板类型" not in INDEX_HTML


def test_template_rule_editor_is_business_readable():
    assert "选项组角色" in INDEX_HTML
    assert "尺寸规则" in INDEX_HTML
    assert "尺寸对象" in INDEX_HTML
    assert "文字内容设置" in INDEX_HTML
    assert "多个文字位置（可选）" in INDEX_HTML
    assert "适用设计/选项" in INDEX_HTML
    assert "变量前缀" in INDEX_HTML
    assert 'id="addDimensionRowBtn"' in INDEX_HTML
    assert 'id="addTextSequenceRowBtn"' in INDEX_HTML
    assert "添加尺寸" in INDEX_HTML
    assert "添加多个文字位置" in INDEX_HTML
    assert "默认值" in INDEX_HTML
    assert "特殊处理" in INDEX_HTML
    assert "文本效果规则" not in INDEX_HTML
    assert "添加文本效果" not in INDEX_HTML
    assert "其他说明（可选，不参与渲染）" in INDEX_HTML
    assert "规则检查结果" in INDEX_HTML
    assert "data-option-group-name" in INDEX_HTML
    assert "data-dimension-target" in INDEX_HTML
    assert "data-text-sequence-field" in INDEX_HTML
    assert "data-text-sequence-delimiter" in INDEX_HTML
    assert "data-text-sequence-prefix" in INDEX_HTML
    assert "data-text-sequence-count" in INDEX_HTML
    assert "data-slot-source" not in INDEX_HTML
    assert "槽位映射" not in INDEX_HTML
    assert "尺寸模式" in INDEX_HTML
    assert "固定制图尺寸" in INDEX_HTML
    assert 'id="dimensionMode"' in INDEX_HTML
    assert 'id="fixedDimensionFields"' in INDEX_HTML
    assert 'id="fixedWidth"' in INDEX_HTML
    assert 'id="fixedHeight"' in INDEX_HTML
    assert "dimension-mode-card" in INDEX_HTML
    assert "data-override-target" in INDEX_HTML
    assert 'id="textSourceColumn"' in INDEX_HTML
    assert 'id="textTargetName"' in INDEX_HTML
    assert 'id="textEffectRows"' not in INDEX_HTML
    assert 'data-effect-target' not in INDEX_HTML
    assert 'data-effect-selector' not in INDEX_HTML
    assert 'data-effect-action' not in INDEX_HTML
    assert 'data-effect-values' not in INDEX_HTML
    assert 'id="alternatingColorEnabled"' not in INDEX_HTML
    assert "结构化规则 JSON" not in INDEX_HTML
    assert "新建空白" not in INDEX_HTML
    assert "默认色彩模式" in INDEX_HTML
    assert "输出色彩" in INDEX_HTML
    assert "rule_source: \"structured_form\"" in INDEX_HTML
    assert "buildCanonicalRulePack" in INDEX_HTML


def test_template_rule_supports_fixed_dimensions():
    assert 'option value="fixed">固定制图尺寸</option>' in INDEX_HTML
    assert "collectFixedDimensions" in INDEX_HTML
    assert "dimension_mode: dimensionMode" in INDEX_HTML
    assert "dimensions.Fixed" in INDEX_HTML
    assert "固定宽度和固定高度" in INDEX_HTML
    assert "syncDimensionMode" in INDEX_HTML
    assert 'document.getElementById("dimensionRows").hidden = fixed' in INDEX_HTML
    assert 'document.getElementById("addDimensionRowBtn").hidden = fixed' in INDEX_HTML
    assert 'document.getElementById("fixedDimensionFields").hidden = !fixed' in INDEX_HTML
    assert 'document.getElementById("fixedWidth").disabled = !fixed' in INDEX_HTML
    assert 'document.getElementById("fixedHeight").disabled = !fixed' in INDEX_HTML
    assert '!(fixed && key === "Fixed")' in INDEX_HTML
    assert "displayDimensionTargets(draft.dimensions || {}, draft.dimension_mode)" in INDEX_HTML
    assert 'document.getElementById("fixedWidth").value = fixed' in INDEX_HTML
    assert 'document.getElementById("fixedHeight").value = fixed' in INDEX_HTML


def test_template_onboarding_requires_scan_check_and_confirmation():
    assert 'id="templateProfile"' in INDEX_HTML
    assert 'id="scanEvidence"' in INDEX_HTML
    assert 'id="scanEvidenceRaw" readonly' in INDEX_HTML
    assert "查看原始扫描明细" in INDEX_HTML
    assert 'id="fieldSources" readonly' in INDEX_HTML
    assert 'id="restoreSuggestionsBtn"' in INDEX_HTML
    assert 'id="addOptionGroupBtn"' in INDEX_HTML
    assert 'id="orderBindingsJson"' in INDEX_HTML
    assert 'id="assetMappingsJson"' in INDEX_HTML
    assert 'id="textPoliciesJson"' in INDEX_HTML
    assert 'id="outputTransformsJson"' in INDEX_HTML
    assert 'id="validationSampleJson"' in INDEX_HTML
    assert "prepareBusinessRuleEditor" in INDEX_HTML
    assert "profileWrapper.hidden = true" in INDEX_HTML
    assert "保存版本备注" in INDEX_HTML
    assert "不参与渲染" in INDEX_HTML
    assert 'id="templateRuleNote"' in INDEX_HTML
    assert "collectTextEffects" not in INDEX_HTML
    assert 'id="rescanTemplateBtn"' in INDEX_HTML
    assert "rescanTemplate" in INDEX_HTML
    assert 'id="uploadScanTemplateBtn"' in INDEX_HTML
    assert "uploadAndScanTemplate" in INDEX_HTML
    assert "检查并保存规则" in INDEX_HTML
    assert INDEX_HTML.index('id="uploadScanTemplateBtn"') < INDEX_HTML.index("选项组角色")
    assert INDEX_HTML.count('addEventListener("click", uploadAndScanTemplate)') == 1
    assert "文件已保存为草稿，但扫描未完成" in INDEX_HTML
    assert "formatScanEvidence" in INDEX_HTML
    assert "formatRawScanEvidence" in INDEX_HTML
    assert "formatFieldSources" in INDEX_HTML
    assert "请先点击“上传并扫描 .ai 模板”，扫描完成后再保存规则" in INDEX_HTML
    assert "/rules/check" in INDEX_HTML
    assert "/rules/confirm" in INDEX_HTML
    assert "/rules/rollback" in INDEX_HTML
    assert "data-rule-rollback" in INDEX_HTML
    assert "/scan" in INDEX_HTML
    assert "扫描草稿已生成" in INDEX_HTML
    assert "data-template-disable" in INDEX_HTML
    assert "data-template-remove" in INDEX_HTML
    assert 'state.templates.filter(template => template.status === "active")' in INDEX_HTML
    assert 'existingTemplate.status === "active"' in INDEX_HTML
    assert "请先停用模板，再修改文件或基础信息" in INDEX_HTML

    fill_body = INDEX_HTML[
        INDEX_HTML.index("function fillTemplateRuleFields"):
        INDEX_HTML.index("function legacyOptionGroups")
    ]
    assert "resetTemplateRuleFields()" not in fill_body
    assert 'document.getElementById("fieldSources").value = formatFieldSources' in INDEX_HTML


def test_template_rule_check_infers_hidden_business_fields():
    assert "currentRulePackProfile" in INDEX_HTML
    assert "mergeTextPolicies" in INDEX_HTML
    assert "mergeValidationSample" in INDEX_HTML
    assert "rules.order_bindings = isPlainObject(rules.order_bindings)" in INDEX_HTML
    assert "rules.text_policies = mergeTextPolicies" in INDEX_HTML
    assert "const sample = mergeValidationSample" in INDEX_HTML
    assert "sequences.forEach(item =>" in INDEX_HTML
    assert "rules.slot_mappings.forEach(item =>" in INDEX_HTML
    assert "result[field] = field" in INDEX_HTML
    assert "if (sequences.length)" in INDEX_HTML
    assert "Object.values(splitGroups).forEach" in INDEX_HTML
    assert "请选择模板规则类型" not in INDEX_HTML
    assert "模板类型仅供系统参考" in INDEX_HTML
    assert "每个模板文字对象都要有对应的订单内容来源" in INDEX_HTML
    assert "文字内容设置" in INDEX_HTML


def test_template_rule_payload_preserves_legacy_config():
    assert "templateRuleBaseConfig" in INDEX_HTML
    assert "...baseConfig" in INDEX_HTML
    assert "mergeDesignOptions(baseConfig.design_options, designOptions)" in INDEX_HTML
    assert "state.textSequenceRowsTouched && !slotMappings.length ? [] : baseConfig.slots" in INDEX_HTML
    assert 'type: match.type || "text_fit_box"' in INDEX_HTML
    assert "buildAssetsRulePayload(baseConfig)" in INDEX_HTML
    assert "Array.isArray(baseConfig.slot_mappings)" in INDEX_HTML
    assert "isEditingExistingTemplate" in INDEX_HTML
    assert "strict && (!draft.defaults || !draft.defaults.font)" in INDEX_HTML
    assert "existingTemplate.template_type" in INDEX_HTML


def test_template_rule_uses_text_sequences_instead_of_column_slots():
    assert "function collectTextSequences" in INDEX_HTML
    assert "function slotMappingsFromTextSequences" in INDEX_HTML
    assert "function legacyTextSequences" in INDEX_HTML
    assert "function mergeTextSequences" in INDEX_HTML
    assert "function mergeDimensions" in INDEX_HTML
    assert "text_sequences: textSequences" in INDEX_HTML
    assert "buildSequenceVariables(variablePrefix, startIndex, count)" in INDEX_HTML
    assert "delimiter: delimiter || (count > 1 ? \"|\" : \"\")" in INDEX_HTML
    assert "row_index: index" in INDEX_HTML
    assert "function setTextSequenceRows" in INDEX_HTML
    assert "function setDimensionRows" in INDEX_HTML
    assert "data-remove-text-sequence-row" in INDEX_HTML
    assert "data-remove-dimension-row" in INDEX_HTML
    assert "return visible.map(sequence =>" in INDEX_HTML
    assert "dimensionRowsTouched" in INDEX_HTML
    assert "textSequenceRowsTouched" in INDEX_HTML
    assert "? collectedDimensions" in INDEX_HTML
    assert "? mergeTextSequences([], collectedTextSequences)" in INDEX_HTML
    assert "legacySlotMappingRows = !state.textSequenceRowsTouched" in INDEX_HTML
    assert 'raw_text: state.dimensionRowsTouched ? ""' in INDEX_HTML
    assert "字段拆分与变量序列" in INDEX_HTML
    assert "Name1、Name2、Name3" in INDEX_HTML


def test_template_type_preserves_existing_before_inference():
    body = INDEX_HTML[
        INDEX_HTML.index("function inferTemplateTypeFromForm"):
        INDEX_HTML.index("function templateRuleMissingItems")
    ]
    assert body.index("existingTemplate.template_type") < body.index("if (hasDesignAssets)")
    assert body.index("state.templateRuleBaseConfig.template_type") < body.index("if (hasDesignGroup)")


def test_scan_evidence_defaults_to_summary_and_keeps_raw_details_collapsed():
    assert 'id="scanEvidenceLabel">扫描结果摘要（只读）' in INDEX_HTML
    assert 'class="preview-box readonly-summary" id="scanEvidence"' in INDEX_HTML
    assert 'class="advanced-rule-box scan-evidence-details"' in INDEX_HTML
    assert "完整对象路径、坐标和颜色信息已收起" in INDEX_HTML
    assert "fontMappings" in INDEX_HTML
    assert "compareTemplateOptionNames" in INDEX_HTML
    assert "items.reduce" in INDEX_HTML
    assert "items.filter(item => item && item.name)" in INDEX_HTML
    assert 'document.getElementById("scanEvidence").textContent = formatScanEvidence(evidence)' in INDEX_HTML
    assert 'document.getElementById("scanEvidenceRaw").value = formatRawScanEvidence(evidence)' in INDEX_HTML


def test_template_rules_prefill_fixed_options_before_optional_supplement():
    assert "查看系统审计明细（可选）" in INDEX_HTML
    assert "当前配置与系统建议不同" in INDEX_HTML
    assert "文字内容设置" in INDEX_HTML
    assert "其他说明（可选，不参与渲染）" in INDEX_HTML
    assert "多个文字位置（可选）" in INDEX_HTML
    assert "文本效果规则" not in INDEX_HTML
    assert 'id="textSourceColumn"' in INDEX_HTML
    assert 'id="textTargetName"' in INDEX_HTML
    assert "function collectTextContentRule" in INDEX_HTML
    assert "function collectTextEffects" not in INDEX_HTML
    assert "function effectRowsFromConfig" not in INDEX_HTML
    assert 'data-effect-condition' not in INDEX_HTML
    assert "function parseEffectCondition" not in INDEX_HTML
    assert "function formatEffectCondition" not in INDEX_HTML
    assert "#textEffectRows" not in INDEX_HTML
    assert "#D71920,#000000" not in INDEX_HTML
    assert "文本效果规则" not in INDEX_HTML
    assert "delete savedBaseConfig.effects" in INDEX_HTML
    assert "delete savedBaseConfig.text_sequence_styles" in INDEX_HTML
    assert "加粗" in INDEX_HTML
    assert "option_overrides" in INDEX_HTML
    assert "function prefillScannedOptionSuggestions" in INDEX_HTML
    assert "function mergeScannedOptionGroups" in INDEX_HTML
    assert "const groups = mergeScannedOptionGroups(savedGroups, config);" in INDEX_HTML
    assert "font_options: normalizeOptions(config.font_options)" in INDEX_HTML
    assert '["font_options", "design_font_options", "design_options", "style_options"]' in INDEX_HTML
    assert 'value="design_font_options"' in INDEX_HTML
    assert "独立设计字体" in INDEX_HTML
    assert ">忽略</option>" not in INDEX_HTML
    assert 'id="designAssetMappingRows"' in INDEX_HTML
    assert "collectDesignAssetMappings" in INDEX_HTML
    assert 'data-design-asset-group' in INDEX_HTML
    assert 'id="designFontAiFiles"' in INDEX_HTML
    assert "独立设计字体资源" in INDEX_HTML
    assert "独立设计资源（可选，可多选）" in INDEX_HTML
    assert 'form.append("design_font_assets", file)' in INDEX_HTML
    assert "订单选项" in INDEX_HTML
    assert "例如 F10 或 D1" in INDEX_HTML
    assert "function compactOptionRange" in INDEX_HTML
    assert "return numbers.length === 1" in INDEX_HTML
    assert "optionGroupsTouched: false" in INDEX_HTML
    assert "state.optionGroupsTouched = true" in INDEX_HTML
    assert "font_options: state.optionGroupsTouched ? fontOptions" in INDEX_HTML
    assert "design_font_options: state.optionGroupsTouched" in INDEX_HTML
    assert "const current = buildTemplateRulePayload();" in INDEX_HTML
    assert "!hasConfiguredRuleValue(merged[key])" in INDEX_HTML


def test_scanned_option_suggestions_render_as_editable_option_groups():
    load_body = INDEX_HTML[
        INDEX_HTML.index("async function loadTemplateRuleText"):
        INDEX_HTML.index("function renderAssetRows")
    ]
    onboarding_body = INDEX_HTML[
        INDEX_HTML.index("function fillOnboardingFields"):
        INDEX_HTML.index("function prefillScannedOptionSuggestions")
    ]
    assert "fillOnboardingFields(pack, onboarding.versions || [], onboarding.scan_evidence || {})" in load_body
    assert "fillTemplateRuleFields(pack.rules || {})" not in load_body
    assert "fillTemplateRuleFields(editableRules)" in onboarding_body


def test_template_asset_list_has_download_and_delete_actions():
    assert "data-template-download" not in INDEX_HTML
    assert "data-template-delete" not in INDEX_HTML
    assert "data-asset-download" in INDEX_HTML
    assert "data-asset-delete" in INDEX_HTML
    assert 'data-asset-delete="primary"' in INDEX_HTML
    assert "disabled title=\"尺寸/作图区模板" not in INDEX_HTML
    assert "deleteTemplateAsset(" in INDEX_HTML
    assert "template_rules_config" in INDEX_HTML
    assert "window.confirm" in INDEX_HTML
    assert 'id="referenceAiFile"' in INDEX_HTML
    assert "简单模板可只传这一项" in INDEX_HTML
    assert "尺寸/作图区模板（可选" in INDEX_HTML
    assert "尺寸/作图区模板" in INDEX_HTML
    assert "独立设计资源" in INDEX_HTML
    assert "displayTemplateAiRole" in INDEX_HTML
