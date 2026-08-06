(function () {
  "use strict";

  const API_ROOT = "/api/v2/templates";
  const CHECK_KEYS = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
  const CHECK_LABELS = {
    output: "1 Output 结构",
    fields: "2 订单字段",
    options: "3 选项映射",
    slots: "4 槽位要求",
    content: "5 处理预设",
    dimensions: "6 尺寸边界",
    colors: "7 颜色规则",
    preview: "8 样例预览"
  };
  const STATUS_LABELS = { confirmed: "已核验", pending: "待校验", blocked: "阻断" };
  const STATUS_CLASS = { confirmed: "success", pending: "warn", blocked: "blocked" };
  const PRESETS = ["direct_text", "split_by_pipe", "initial_with_text", "multi_initials", "path_text", "tail_text", "design_font_combo", "asset_replace"];
  const OPTION_PRESETS = PRESETS.filter((preset) => preset !== "asset_replace");
  const PRESET_LABELS = {
    direct_text: "替换文本",
    split_by_pipe: "替换文本 · 按 | 拆分",
    initial_with_text: "素材替换 · 首字母素材 + 正文",
    multi_initials: "素材替换 · 多首字母素材",
    path_text: "路径文字",
    tail_text: "尾巴文字",
    design_font_combo: "替换文本 · Design + Font 组合",
    asset_replace: "素材替换"
  };

  const state = {
    templates: [],
    selectedTemplateId: "",
    draft: null,
    scan: {},
    validation: null,
    expanded: { designs: false, fonts: false },
    uploadFile: null,
    lastUploadFile: null,
    isScanning: false,
    stage: "upload"
  };

  const $ = (id) => document.getElementById(id);

  globalThis.DrawFlowV2WorkbenchContext = {
    API_ROOT,
    CHECK_KEYS,
    CHECK_LABELS,
    STATUS_LABELS,
    STATUS_CLASS,
    PRESETS,
    OPTION_PRESETS,
    PRESET_LABELS,
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
    on("aiFile", "change", handleFileInput);
    on("retryScanBtn", "click", retryScan);
    on("closeScanFailedBtn", "click", closeScanFailure);
    on("enterStructureBtn", "click", () => globalThis.setWorkbenchStage("structure"));
    on("backToUploadBtn", "click", () => globalThis.setWorkbenchStage("upload"));
    on("newTemplateBtn", "click", () => {
      clearDraftView();
      globalThis.setWorkbenchStage("upload");
    });
    document.querySelectorAll("#v2CheckRail .check-item").forEach((item) => {
      item.addEventListener("click", () => globalThis.setWorkbenchStage("structure"));
    });
    bindDropzone();
  }

  function on(id, type, handler) {
    const el = $(id);
    if (el) el.addEventListener(type, handler);
  }

  function renderInitialState() {
    setText("draftStatusBadge", "未选择模板");
    setText("draftVersion", "-");
    renderScanProgress("等待选择 .ai 文件", "idle");
    renderScanSummary();
    setText("publishBlockerText", "请先完成草稿配置与人工核验。");
    setDisabled("publishVersionBtn", true);
    setDisabled("trialRenderBtn", true);
    globalThis.setWorkbenchStage("upload");
    updateCheckRail(defaultChecks());
    updateDraftButtons();
  }

})();


