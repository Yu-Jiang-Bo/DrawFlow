from pathlib import Path

from src.service.v2_workbench_page import INDEX_HTML


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSS = (PROJECT_ROOT / "src/service/static/v2-workbench/workbench.css").read_text(encoding="utf-8")
JS = "\n".join(
    (PROJECT_ROOT / f"src/service/static/v2-workbench/{name}").read_text(encoding="utf-8")
    for name in [
        "workbench.js",
        "workbench-dom.js",
        "workbench-api.js",
        "workbench-scan-model.js",
        "workbench-form-model.js",
        "workbench-config.js",
        "workbench-view.js",
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
    "templateId",
    "templateName",
    "shopName",
    "draftStatusBadge",
    "draftVersion",
    "aiDropzone",
    "aiFile",
    "scanTemplateBtn",
    "rescanTemplateBtn",
    "cancelScanBtn",
    "scanProgress",
    "scanSummary",
    "scanEmptyState",
    "structureSearch",
    "structureTree",
    "toggleDesignsBtn",
    "toggleFontsBtn",
    "outputConfigRows",
    "fieldBindingRows",
    "optionMappingRows",
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
    assert 'href="/v2/templates/workbench"' in INDEX_HTML
    assert 'data-nav-target="v2-workbench"' in INDEX_HTML
    assert 'href="/static/v2-workbench/workbench.css"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-dom.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-api.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-scan-model.js"' in INDEX_HTML
    assert 'src="/static/v2-workbench/workbench-view.js"' in INDEX_HTML
    assert 'class="v2-shell" id="v2WorkbenchApp"' in INDEX_HTML
    assert 'class="workspace-grid"' in INDEX_HTML
    assert 'class="bottom-action-bar"' in INDEX_HTML

    for element_id in REQUIRED_IDS:
        assert f'id="{element_id}"' in INDEX_HTML


def test_v2_workbench_page_has_exact_eight_check_items():
    assert INDEX_HTML.count('class="check-item"') == 8
    for key in CHECK_KEYS:
        assert f'data-check-key="{key}"' in INDEX_HTML
    assert '["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]' in JS


def test_v2_workbench_uses_controlled_business_inputs():
    assert 'type="file" accept=".ai"' in INDEX_HTML
    assert "Output_main" in INDEX_HTML
    assert "Design03" in INDEX_HTML
    assert "F10" in INDEX_HTML
    assert "字段绑定" in INDEX_HTML
    assert "订单原值映射" in INDEX_HTML
    assert "/local/templates/scan" in JS
    assert "/assets/" in JS
    assert "buildControlledConfig" in JS
    assert "field_bindings" in JS
    assert "option_mappings" in JS
    assert "showScanFailure" in JS
    assert "sanitizeMessage" in JS


def test_v2_workbench_does_not_expose_forbidden_ui_concepts():
    combined = "\n".join([INDEX_HTML, CSS, JS])
    for text in ["磁盘使用量", "JSON 编辑", "自然语言规则", "JSX"]:
        assert text not in combined
    assert 'id="publishVersionBtn" type="button" disabled' in INDEX_HTML


def test_v2_workbench_static_styles_cover_desktop_layout_and_states():
    assert ".v2-header" in CSS
    assert ".workspace-grid" in CSS
    assert "grid-template-columns: minmax(260px, 300px) minmax(0, 1fr) minmax(260px, 300px)" in CSS
    assert "@media (max-width: 1280px)" in CSS
    assert "@media (max-width: 1100px)" in CSS
    assert ".upload-zone.dragover" in CSS
    assert ".structure-node" in CSS
    assert ".structured-row" in CSS
    assert "url(" not in CSS
    assert "gradient" not in CSS.lower()


def test_v2_workbench_routes_are_isolated_from_legacy_page():
    assert "from .v2_workbench_page import INDEX_HTML as V2_WORKBENCH_HTML" in SERVER
    assert 'path == "/v2/templates/workbench"' in SERVER
    assert 'path.startswith("/static/v2-workbench/")' in SERVER
    assert '"workbench-scan-actions.js"' in SERVER
    assert "self._send_html(WORKBENCH_HTML)" in SERVER
