(function () {
  "use strict";

  const API_ROOT = "/api/v2/templates";
  const CHECK_KEYS = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
  const CHECK_LABELS = {
    output: "输出结构",
    fields: "字段绑定",
    options: "选项映射",
    slots: "槽位核验",
    content: "内容预设",
    dimensions: "尺寸核验",
    colors: "颜色/字体",
    preview: "预览核验"
  };
  const STATUS_LABELS = { confirmed: "已核验", pending: "待核验", blocked: "阻断" };
  const STATUS_CLASS = { confirmed: "success", pending: "warn", blocked: "blocked" };
  const PRESETS = ["direct_text", "split_by_pipe", "initial_with_text", "multi_initials", "path_text", "tail_text", "design_font_combo", "asset_replace"];

  const state = {
    templates: [],
    selectedTemplateId: "",
    draft: null,
    scan: {},
    validation: null,
    expanded: { designs: false, fonts: false },
    uploadFile: null,
    lastUploadFile: null,
    scanController: null,
    isScanning: false
  };

  const $ = (id) => document.getElementById(id);

  globalThis.DrawFlowV2WorkbenchContext = {
    API_ROOT,
    CHECK_KEYS,
    CHECK_LABELS,
    STATUS_LABELS,
    STATUS_CLASS,
    PRESETS,
    state,
    $
  };
  globalThis.$ = $;

  document.addEventListener("DOMContentLoaded", initWorkbench);

  function initWorkbench() {
    bindEvents();
    renderInitialState();
    loadTemplates().catch((error) => showScanFailure(friendlyError(error, "模板列表加载失败，请稍后重试。")));
  }

  function bindEvents() {
    on("templateSearch", "input", renderTemplateList);
    on("templateId", "input", updateDraftButtons);
    on("templateName", "input", updateDraftButtons);
    on("shopName", "input", updateDraftButtons);
    on("structureSearch", "input", renderStructureTree);
    on("toggleDesignsBtn", "click", () => toggleSection("designs"));
    on("toggleFontsBtn", "click", () => toggleSection("fonts"));
    on("saveDraftBtn", "click", saveDraft);
    on("trialRenderBtn", "click", () => showTransientStatus("试渲染接口未就绪，当前先完成草稿配置。"));
    on("publishVersionBtn", "click", () => showTransientStatus("发布接口未接入，当前不会伪造发布结果。"));
    on("scanTemplateBtn", "click", () => uploadSelectedAiFile(false));
    on("rescanTemplateBtn", "click", () => uploadSelectedAiFile(true));
    on("cancelScanBtn", "click", cancelScan);
    on("aiFile", "change", handleFileInput);
    on("retryScanBtn", "click", retryScan);
    on("closeScanFailedBtn", "click", closeScanFailure);
    bindDropzone();
  }

  function on(id, type, handler) {
    const el = $(id);
    if (el) el.addEventListener(type, handler);
  }

  function renderInitialState() {
    setText("draftStatusBadge", "未选择模板");
    setText("draftVersion", "-");
    setText("scanProgress", "等待选择 .ai 文件");
    setText("scanSummary", "等待扫描结果");
    setText("scanEmptyState", "等待扫描结果，扫描接口未就绪时可先保存文件。");
    setText("publishBlockerText", "请先完成草稿配置与人工核验。");
    setDisabled("publishVersionBtn", true);
    setDisabled("trialRenderBtn", true);
    renderStructureTree();
    renderTables();
    updateCheckRail(defaultChecks());
    updateDraftButtons();
  }

})();


