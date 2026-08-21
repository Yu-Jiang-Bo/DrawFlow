from pathlib import Path

from src.service.job_store import JobStore
from src.service.web_page import INDEX_HTML


def test_page_uses_drawflow_branding():
    assert "<title>DrawFlow</title>" in INDEX_HTML
    assert "<h1>DrawFlow</h1>" in INDEX_HTML
    assert "订单效果图与模板管理" in INDEX_HTML
    assert "制图渲染工作台" not in INDEX_HTML


def test_main_tabs_link_to_v2_template_workbench():
    assert '<a class="tab" href="/v2/templates/workbench">V2 工作台</a>' in INDEX_HTML


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
    assert "/local/render" in INDEX_HTML
    assert "/local/jobs/" in INDEX_HTML
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


def test_render_page_preserves_gateway_error_codes_and_explains_browser_fetch_failures():
    assert "function requestErrorFromText(text)" in INDEX_HTML
    assert "function normalizeRenderError(error)" in INDEX_HTML
    assert "value = value.message || value.error || value.detail || null" in INDEX_HTML
    assert 'typeof value.message === "string"' in INDEX_HTML
    assert "failure.message || failure.code" in INDEX_HTML
    assert "error.code = String(failure.code || \"\")" in INDEX_HTML
    assert 'code === "template_not_published"' in INDEX_HTML
    assert 'code === "central_unreachable"' in INDEX_HTML
    assert "failed to fetch" in INDEX_HTML
    assert "127.0.0.1:8766" in INDEX_HTML
    assert "await loadJobs().catch(() => {})" in INDEX_HTML
    assert "String(error && error.message ? error.message : error || \"\")" not in INDEX_HTML


def test_render_page_has_progress_overlay():
    assert 'id="renderProgressOverlay"' in INDEX_HTML
    assert 'id="progressBar"' not in INDEX_HTML
    assert 'id="progressCount"' not in INDEX_HTML
    assert 'id="progressPercent"' not in INDEX_HTML
    assert "showProgress" in INDEX_HTML
    assert "tickProgress" not in INDEX_HTML
    assert "pollRenderProgress" not in INDEX_HTML
    assert "currentRunningJob" not in INDEX_HTML
    assert "hasRealRenderProgress" not in INDEX_HTML
    assert "progressPollTimer" not in INDEX_HTML
    assert "progressTimer" not in INDEX_HTML
    assert "`已渲染 ${boundedCurrent}/${total}`" not in INDEX_HTML
    assert 'document.getElementById("progressPercent").textContent = "实时"' not in INDEX_HTML
    assert "调用 Illustrator" in INDEX_HTML
    assert "生成 AI 文件" in INDEX_HTML
    assert 'return ["上传订单表格", "解析订单字段", "调用 Illustrator", "生成 AI 文件", "完成收尾"]' in INDEX_HTML


def test_job_store_merges_live_progress_file(tmp_path):
    store = JobStore(tmp_path)
    record = store.create({"template_id": "T1"})
    progress_file = tmp_path / record["job_id"] / "progress.json"
    progress_file.write_text('{"current": 153, "total": 199, "stage": "生成 AI 文件"}', encoding="utf-8")

    loaded = store.load(record["job_id"])
    recent = store.list_recent(1)[0]

    assert loaded["progress"]["current"] == 153
    assert loaded["progress"]["total"] == 199
    assert recent["progress"]["current"] == 153


def test_render_page_downloads_the_department_primary_delivery():
    assert "outputs.primary_output" in INDEX_HTML
    assert "function primaryOutputKey(outputs)" in INDEX_HTML
    assert 'if (outputs.output_bundle) return "output_bundle"' in INDEX_HTML
    assert "下载全部成品 ZIP" in INDEX_HTML
    assert "下载 PNG 成品" in INDEX_HTML


def test_render_page_lists_v2_workbench_templates_without_legacy_actions():
    assert 'v2_illustrator_template: "V2 工作台模板"' in INDEX_HTML
    assert "!isV2Template(template) && template.status" in INDEX_HTML
    assert "function isV2Template(template)" in INDEX_HTML


def test_legacy_render_page_downloads_the_department_primary_delivery():
    source = Path("src/service/http_server.py").read_text(encoding="utf-8")

    assert "function primaryOutputKey(outputs)" in source
    assert 'outputs.output_png' in source
    assert 'download/${encodeURIComponent(outputKey)}' in source


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
    assert 'return options.length ? options.join(" / ") : "未识别"' in INDEX_HTML
    assert 'return values.join(" / ")' not in INDEX_HTML


def test_template_form_hides_type_and_status_from_user():
    assert 'id="templateType"' not in INDEX_HTML
    assert 'id="templateStatus"' not in INDEX_HTML
    assert 'form.append("template_type", buildTemplateRulePayload().template_type)' in INDEX_HTML
    assert 'form.append("status", "draft")' in INDEX_HTML
    assert "function inferTemplateTypeFromForm" in INDEX_HTML
    assert "内部模板类型" not in INDEX_HTML


def test_template_form_does_not_expose_text_output_switches():
    assert 'id="outputOutlineText"' not in INDEX_HTML
    assert 'id="outputPathfinderMerge"' not in INDEX_HTML
    assert 'outline_text: document.getElementById("outputOutlineText").checked' not in INDEX_HTML
    assert 'pathfinder_merge: document.getElementById("outputPathfinderMerge").checked' not in INDEX_HTML
    assert 'form.append("outline_text"' not in INDEX_HTML
    assert 'form.append("pathfinder_merge"' not in INDEX_HTML


def test_template_rule_editor_is_business_readable():
    assert "选项组角色" in INDEX_HTML
    assert "尺寸规则" in INDEX_HTML
    assert "尺寸对象" in INDEX_HTML
    assert "文字内容设置" in INDEX_HTML
    assert "多个文字位置（可选）" in INDEX_HTML
    assert "映射与文字策略" in INDEX_HTML
    assert "映射、文字策略与验证样例" not in INDEX_HTML
    assert "适用设计/选项" in INDEX_HTML
    assert "变量前缀" in INDEX_HTML
    assert 'id="addDimensionRowBtn"' in INDEX_HTML
    assert 'id="addTextSequenceRowBtn"' in INDEX_HTML
    assert "添加尺寸" in INDEX_HTML
    assert "添加多个文字位置" in INDEX_HTML
    assert "默认值" in INDEX_HTML
    assert "模板特殊规则（可选）" in INDEX_HTML
    assert "文本效果规则" not in INDEX_HTML
    assert "添加文本效果" not in INDEX_HTML
    assert "其他说明（可选，不参与渲染）" not in INDEX_HTML
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
    assert 'id="templateSpecialRules"' in INDEX_HTML
    assert 'id="compileSpecialRulesBtn"' in INDEX_HTML
    assert 'id="specialRuleStatus"' in INDEX_HTML
    assert 'id="specialRulePreview"' in INDEX_HTML
    assert 'id="fontStyleRuleRows"' not in INDEX_HTML
    assert 'id="addFontStyleRuleBtn"' not in INDEX_HTML
    assert "data-override-target" not in INDEX_HTML
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
    assert "placeholder='{\"" not in INDEX_HTML
    assert "placeholder='[{\"" not in INDEX_HTML
    assert "JSON 格式错误" not in INDEX_HTML


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
    assert 'id="validationSampleJson"' not in INDEX_HTML
    assert "prepareBusinessRuleEditor" in INDEX_HTML
    assert "profileWrapper.hidden = true" in INDEX_HTML
    assert "保存版本备注" in INDEX_HTML
    assert 'id="templateRuleNote"' not in INDEX_HTML
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
    assert "/local/templates/scan" in INDEX_HTML
    assert "中央服务不直接调用 Illustrator" in INDEX_HTML
    assert "扫描草稿已生成" in INDEX_HTML
    assert "data-template-disable" not in INDEX_HTML
    assert "function disableTemplate" not in INDEX_HTML
    assert "data-template-activate" in INDEX_HTML
    assert "/activate" in INDEX_HTML
    assert "data-template-remove" in INDEX_HTML
    assert 'id="templateRemoveConfirmOverlay"' in INDEX_HTML
    assert 'id="templateRemoveConfirmInput"' in INDEX_HTML
    assert "function openTemplateRemoveConfirm" in INDEX_HTML
    assert "function confirmTemplateRemoval" in INDEX_HTML
    assert 'state.templates.filter(template => template.status === "active")' in INDEX_HTML
    assert 'existingTemplate.status === "active"' in INDEX_HTML
    assert "已启用模板请通过“上传并扫描 .ai 模板”更新文件或基础信息" in INDEX_HTML

    fill_body = INDEX_HTML[
        INDEX_HTML.index("function fillTemplateRuleFields"):
        INDEX_HTML.index("function legacyOptionGroups")
    ]
    assert "resetTemplateRuleFields()" not in fill_body
    assert 'document.getElementById("fieldSources").value = formatFieldSources' in INDEX_HTML


def test_template_rule_check_infers_hidden_business_fields():
    assert "currentRulePackProfile" in INDEX_HTML
    assert "mergeTextPolicies" in INDEX_HTML
    assert "mergeValidationSample" not in INDEX_HTML
    assert "rules.order_bindings = isPlainObject(rules.order_bindings)" in INDEX_HTML
    assert "rules.text_policies = mergeTextPolicies" in INDEX_HTML
    assert "const sample = mergeValidationSample" not in INDEX_HTML
    assert "sequences.forEach(item =>" in INDEX_HTML
    assert "rules.slot_mappings.forEach(item =>" in INDEX_HTML
    assert "result[field] = field" in INDEX_HTML
    assert "delete validation.sample" in INDEX_HTML
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
    assert "完整对象定位、坐标和颜色信息已收起" in INDEX_HTML
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
    assert "其他说明（可选，不参与渲染）" not in INDEX_HTML
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
    assert "delete savedBaseConfig.font_style_rules" in INDEX_HTML
    assert "function collectFontStyleRules" not in INDEX_HTML
    assert "function displayFontStyleRules" not in INDEX_HTML
    assert "legacyFontStyleRules" not in INDEX_HTML
    assert "function nonBoldOptionOverrides" in INDEX_HTML
    assert "option_overrides: nonBoldOptionOverrides(baseConfig.option_overrides)" in INDEX_HTML
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
    assert 'postJson("/api/templates/rules/compile"' in INDEX_HTML
    assert "special_rules_text: specialRulesText" in INDEX_HTML
    assert "rule_ast: state.compiledRuleAst || undefined" in INDEX_HTML
    assert "state.specialRulesDirty" in INDEX_HTML


def test_template_rule_uses_one_natural_language_special_rule_editor():
    assert "模板特殊规则（可选）" in INDEX_HTML
    assert "这里只描述无法用固定项表达的特殊渲染逻辑" in INDEX_HTML
    assert 'id="templateSpecialRules"' in INDEX_HTML
    assert 'id="compileSpecialRulesBtn"' in INDEX_HTML
    assert "function compileSpecialRules" in INDEX_HTML
    assert "function renderSpecialRulePreview" in INDEX_HTML
    assert "function describeSpecialRuleAst" in INDEX_HTML
    assert "内容已修改，需要重新编译" in INDEX_HTML
    assert "编译服务未返回可执行规则，请修改描述后重试" in INDEX_HTML
    assert "特殊规则已编译，请核对执行摘要后保存" in INDEX_HTML
    assert "Name 多色循环（可选）" not in INDEX_HTML
    assert "字体加粗规则（可选）" not in INDEX_HTML
    assert 'id="nameColorRows"' not in INDEX_HTML
    assert 'id="fontStyleRuleRows"' not in INDEX_HTML
    assert "function collectNameColorCycle" not in INDEX_HTML
    assert "function collectFontStyleRules" not in INDEX_HTML


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


def test_template_rule_exposes_multi_name_customization_switch():
    assert 'id="multiNameCustomization"' in INDEX_HTML
    assert "支持多姓名定制" in INDEX_HTML
    assert 'id="quantitySourceColumn"' in INDEX_HTML
    assert "function syncMultiNameCustomization" in INDEX_HTML
    assert "multi_name_customization: { enabled: textRule.multi_name_enabled }" in INDEX_HTML
    assert "displayMultiNameCustomization" in INDEX_HTML
