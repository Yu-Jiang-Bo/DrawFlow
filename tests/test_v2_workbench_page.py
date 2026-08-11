from pathlib import Path

from src.service.v2_workbench_page import INDEX_HTML


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSS = (PROJECT_ROOT / "src/service/static/v2-workbench/workbench.css").read_text(encoding="utf-8")
STAGE_CSS = (PROJECT_ROOT / "src/service/static/v2-workbench/workbench-stages.css").read_text(encoding="utf-8")
ALL_CSS = CSS + "\n" + STAGE_CSS
JS = "\n".join(
    (PROJECT_ROOT / f"src/service/static/v2-workbench/{name}").read_text(encoding="utf-8")
    for name in [
        "workbench.js",
        "workbench-dom.js",
        "workbench-api.js",
        "workbench-scan-model.js",
        "workbench-form-model.js",
        "workbench-config.js",
        "workbench-content.js",
        "workbench-style-dimensions.js",
        "workbench-option-rules.js",
        "workbench-rule-evidence.js",
        "workbench-stage-view.js",
        "workbench-view.js",
        "workbench-structure-tree.js",
        "workbench-draft-actions.js",
        "workbench-scan-actions.js",
    ]
)
SERVER = (PROJECT_ROOT / "src/service/http_server.py").read_text(encoding="utf-8")

CHECK_KEYS = [
    "output",
    "fields",
    "options",
    "slots",
    "content",
    "dimensions",
    "colors",
    "preview",
]

REQUIRED_IDS = [
    "v2WorkbenchApp",
    "v2CheckRail",
    "templateList",
    "templateSearch",
    "newTemplateBtn",
    "templateListStats",
    "templateId",
    "templateName",
    "shopName",
    "currentTemplateContext",
    "backToUploadBtn",
    "draftStatusBadge",
    "draftVersion",
    "uploadScanBadge",
    "aiDropzone",
    "aiFile",
    "scanTemplateBtn",
    "rescanTemplateBtn",
    "scanProgress",
    "scanRunningOverlay",
    "scanRunningTitle",
    "scanRunningMessage",
    "scanSummaryMetrics",
    "scanSummaryWarning",
    "scanSummary",
    "scanEmptyState",
    "enterStructureBtn",
    "structureSearch",
    "structureTree",
    "toggleDesignsBtn",
    "toggleFontsBtn",
    "outputConfigRows",
    "fieldBindingRows",
    "optionMappingRows",
    "styleDimensionRows",
    "contentOptionRows",
    "selectedNodeSummary",
    "blockerList",
    "draftSummary",
    "saveDraftBtn",
    "trialRenderBtn",
    "publishVersionBtn",
    "publishBlockerText",
    "scanFailedOverlay",
    "scanFailedMessage",
    "retryScanBtn",
    "closeScanFailedBtn",
]


def test_v2_workbench_page_exposes_independent_entry_contract():
    assert "<title>DrawFlow · V2 模板配置工作台</title>" in INDEX_HTML
    assert 'href="/templates" data-nav-target="templates" aria-current="page"' in INDEX_HTML
    assert 'data-nav-target="v2-workbench"' not in INDEX_HTML
    assert 'href="/static/v2-workbench/workbench.css"' in INDEX_HTML
    assert 'href="/static/v2-workbench/workbench-stages.css"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-dom.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-api.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-scan-model.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-content.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-style-dimensions.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-option-rules.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-rule-evidence.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-stage-view.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-view.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-structure-tree.js"' in INDEX_HTML
    assert 'class="v2-shell" id="v2WorkbenchApp" data-workbench-stage="upload"' in INDEX_HTML
    assert 'class="workspace-grid"' in INDEX_HTML
    assert 'class="bottom-action-bar"' in INDEX_HTML

    for element_id in REQUIRED_IDS:
        assert f'id="{element_id}"' in INDEX_HTML
    assert 'id="templateIdMirror"' not in INDEX_HTML
    assert 'id="templateNameMirror"' not in INDEX_HTML
    assert 'id="shopNameMirror"' not in INDEX_HTML
    assert 'id="cancelScanBtn"' not in INDEX_HTML


def test_v2_workbench_upload_stage_hides_later_configuration():
    upload_start = INDEX_HTML.index('data-stage-panel="upload" aria-label="上传与扫描"')
    structure_start = INDEX_HTML.index('data-stage-panel="structure" aria-label="扫描结构"')
    upload_markup = INDEX_HTML[upload_start:structure_start]
    for forbidden in ["structureTree", "outputConfigRows", "fieldBindingRows", "optionMappingRows", "contentOptionRows"]:
        assert forbidden not in upload_markup
    assert "模板草稿" in upload_markup
    assert "上传并扫描模板" in upload_markup
    assert "扫描摘要" in upload_markup
    assert "进入结构与字段核验" in upload_markup
    assert 'data-stage-panel="rules"' in INDEX_HTML


def test_v2_workbench_page_has_exact_eight_check_items():
    assert INDEX_HTML.count('class="check-item"') == 8
    for key in CHECK_KEYS:
        assert f'data-check-key="{key}"' in INDEX_HTML
    assert '["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]' in JS


def test_v2_workbench_has_independent_rules_stage_contract():
    assert 'data-stage-panel="rules" aria-label="选项列表"' in INDEX_HTML
    assert 'data-stage-panel="rules" aria-label="选项渲染规则"' in INDEX_HTML
    assert 'data-stage-panel="rules" aria-label="模板能力与依赖"' in INDEX_HTML
    for element_id in [
        "optionRuleSearch",
        "optionRuleList",
        "optionRuleStats",
        "pendingOnlyBtn",
        "selectedOptionTitle",
        "selectedOptionPendingBadge",
        "optionContentPreset",
        "optionContentSeparator",
        "contentOptionRows",
        "assetBindingRows",
        "templateCapabilityPanel",
        "capabilityEvidenceRows",
        "colorRuleRows",
        "dimensionRuleRows",
        "fontDependencyRows",
        "saveAndNextOptionBtn",
    ]:
        assert f'id="{element_id}"' in INDEX_HTML
    assert 'const allowed = ["upload", "structure", "rules", "preview"]' in JS
    assert 'globalThis.setWorkbenchStage("rules")' in JS
    assert "renderOptionRuleStage" in JS
    assert '#v2WorkbenchApp[data-workbench-stage="rules"] .workspace-grid' in STAGE_CSS
    assert 'id="structureContentOptionRows"' not in INDEX_HTML


def test_v2_workbench_has_preview_publish_and_preflight_contract():
    assert 'data-stage-panel="preview" aria-label="样例预览与发布"' in INDEX_HTML
    for element_id in [
        "previewSampleRows",
        "previewSideTabs",
        "previewArtworkPane",
        "rerunTrialRenderBtn",
        "previewValidationRows",
        "versionPublishPanel",
        "publishNotes",
        "preflightFailedOverlay",
        "preflightFailedTitle",
        "preflightFailedMessage",
        "preflightIssueList",
        "closePreflightFailedBtn",
        "returnToSampleDataBtn",
    ]:
        assert f'id="{element_id}"' in INDEX_HTML
    assert 'globalThis.setWorkbenchStage("preview")' in JS
    assert "showPreflightFailure" in JS
    assert "closePreflightFailure" in JS
    assert '#v2WorkbenchApp[data-workbench-stage="preview"] .workspace-grid' in STAGE_CSS
    assert ".preflight-dialog" in CSS


def test_v2_workbench_uses_controlled_business_inputs():
    assert 'type="file" accept=".ai"' in INDEX_HTML
    assert "Output_main" in INDEX_HTML
    assert "Design03" in INDEX_HTML
    assert "F10" in INDEX_HTML
    assert "字段绑定" in INDEX_HTML
    assert "订单原值映射" in INDEX_HTML
    assert "/local/templates/scan" in JS
    assert "/assets/" not in JS
    assert "buildControlledConfig" in JS
    assert "field_bindings" in JS
    assert "option_mappings" in JS
    assert "content_preset" in JS
    assert "styleDimensionRows" in INDEX_HTML
    assert "0.007mm" in INDEX_HTML
    assert "dimensionRuleFromValues" in JS
    assert "slot-asset-key" in JS
    assert "slot-tail-first" in JS
    assert "slot-font-dependencies" in JS
    assert "slot-color-binding" in JS
    assert "output-component" in JS
    assert "component_key" in JS
    assert "替换文本" in JS
    assert "路径文字" in JS
    assert "尾巴文字" in JS
    assert "素材替换" in JS
    assert "showScanFailure" in JS
    assert "sanitizeMessage" in JS
    assert "setScanningOverlay" in JS
    assert "cancelScan" not in JS


def test_v2_workbench_does_not_expose_forbidden_ui_concepts():
    combined = "\n".join([INDEX_HTML, CSS, JS])
    for text in ["磁盘使用量", "JSON 编辑", "自然语言规则", "JSX"]:
        assert text not in combined
    assert 'id="publishVersionBtn" type="button" disabled' in INDEX_HTML


def test_v2_workbench_static_styles_cover_desktop_layout_and_states():
    assert ".v2-header" in ALL_CSS
    assert ".workspace-grid" in ALL_CSS
    assert "grid-template-columns: minmax(260px, 300px) minmax(0, 1fr) minmax(260px, 300px)" in CSS
    assert '#v2WorkbenchApp[data-workbench-stage="upload"] .workspace-grid' in STAGE_CSS
    assert '#v2WorkbenchApp[data-workbench-stage="structure"] .workspace-grid' in STAGE_CSS
    assert "@media (max-width: 1280px)" in CSS
    assert "@media (max-width: 1100px)" in CSS
    assert ".upload-zone.dragover" in CSS
    assert ".scan-running-dialog" in STAGE_CSS
    assert "@keyframes scan-running-slide" in STAGE_CSS
    assert ".structure-node" in CSS
    assert ".structured-row" in CSS
    assert ".content-option-group" in CSS
    assert ".content-slot-row" in CSS
    assert "position: sticky; bottom: 0" in CSS
    assert ".structured-row.style-dimension-row" in CSS
    assert "url(" not in ALL_CSS
    assert "gradient" not in ALL_CSS.lower()


def test_v2_workbench_routes_are_isolated_from_legacy_page():
    assert "from .v2_workbench_page import INDEX_HTML as V2_WORKBENCH_HTML" in SERVER
    assert 'path == "/v2/templates/workbench"' in SERVER
    assert 'path.startswith("/static/v2-workbench/")' in SERVER
    assert '"workbench-scan-actions.js"' in SERVER
    assert '"workbench-content.js"' in SERVER
    assert '"workbench-style-dimensions.js"' in SERVER
    assert '"workbench-option-rules.js"' in SERVER
    assert '"workbench-rule-evidence.js"' in SERVER
    assert '"workbench-stages.css"' in SERVER
    assert '"workbench-stage-view.js"' in SERVER
    assert '"workbench-structure-tree.js"' in SERVER
    assert "self._send_html(WORKBENCH_HTML)" in SERVER
