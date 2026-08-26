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
  const OPTION_PRESETS = [...PRESETS.filter((preset) => preset !== "asset_replace"), "mixed_slots"];
  const PRESET_LABELS = {
    direct_text: "替换文本",
    split_by_pipe: "按 | 顺序拆分",
    initial_with_text: "素材替换 · 首字母素材 + 正文",
    multi_initials: "素材替换 · 多首字母素材",
    path_text: "路径文字",
    tail_text: "尾巴文字",
    design_font_combo: "替换文本 · Design + Font 组合",
    asset_replace: "素材替换",
    mixed_slots: "按槽位分别处理（自动）"
  };

  const state = {
    templates: [],
    selectedTemplateId: "",
    draft: null,
    isPublishedView: false,
    scan: {},
    validation: null,
    lastValidatedConfig: null,
    draftLoadRequestId: 0,
    validationRequestId: 0,
    expanded: { designs: false, fonts: false, tree: {} },
    uploadFile: null,
    lastUploadFile: null,
    isScanning: false,
    isSavingDraft: false,
    isTrialRendering: false,
    isPublicationChecking: false,
    isPublishing: false,
    trialGeneration: 0,
    trialRequestId: 0,
    activeTrialRequestId: 0,
    versionRequestId: 0,
    versionsStatus: "idle",
    versionsError: "",
    versionsTemplateId: "",
    trial: null,
    publication: null,
    versions: [],
    previewOutputIndex: 0,
    previewSampleValues: {},
    previewMessage: "",
    stage: "upload",
    optionRules: { pendingOnly: false, selectedIndex: 0 }
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
  globalThis.renderStructureTree = globalThis.renderStructureTree || renderStructureTreeFallback;

  document.addEventListener("DOMContentLoaded", initWorkbench);

  function initWorkbench() {
    const requestedTemplateId = initialTemplateId();
    bindEvents();
    renderInitialState();
    loadTemplates(requestedTemplateId)
      .then((loaded) => {
        if (loaded && requestedTemplateId && state.selectedTemplateId === requestedTemplateId) {
          globalThis.setWorkbenchStage("structure");
        }
      })
      .catch((error) => showScanFailure(friendlyError(error, "模板列表加载失败，请稍后重试。")));
  }

  function initialTemplateId() {
    try {
      return String(new URLSearchParams(window.location.search).get("template_id") || "").trim();
    } catch (_) {
      return "";
    }
  }

  function bindEvents() {
    on("templateSearch", "input", renderTemplateList);
    on("refreshTemplatesBtn", "click", () => {
      refreshSharedTemplates().catch((error) => showScanFailure(friendlyError(error, "共享模板刷新失败，请稍后重试。")));
    });
    on("templateId", "input", handleDraftFieldInput);
    on("templateName", "input", handleDraftFieldInput);
    on("shopName", "input", handleDraftFieldInput);
    on("structureSearch", "input", renderStructureTree);
    on("toggleDesignsBtn", "click", () => toggleSection("designs"));
    on("toggleFontsBtn", "click", () => toggleSection("fonts"));
    on("saveDraftBtn", "click", saveDraft);
    on("trialRenderBtn", "click", () => globalThis.trialRenderCurrentDraft());
    on("publishVersionBtn", "click", () => globalThis.publishCurrentDraft());
    on("scanTemplateBtn", "click", () => uploadSelectedAiFile(false));
    on("rescanTemplateBtn", "click", () => uploadSelectedAiFile(true));
    on("aiFile", "change", handleFileInput);
    on("retryScanBtn", "click", retryScan);
    on("closeScanFailedBtn", "click", closeScanFailure);
    on("enterStructureBtn", "click", () => globalThis.setWorkbenchStage("structure"));
    on("backToUploadBtn", "click", () => globalThis.setWorkbenchStage("upload"));
    on("pendingOnlyBtn", "click", togglePendingOnlyOptions);
    on("optionRuleSearch", "input", renderOptionRuleStage);
    on("optionContentPreset", "change", () => {
      invalidatePreviewIfAvailable("配置已修改，请重新试渲染。");
      applySelectedOptionControls();
    });
    on("confirmStageBtn", "click", confirmCurrentStage);
    on("saveAndNextOptionBtn", "click", saveDraftAndSelectNextOption);
    on("rerunTrialRenderBtn", "click", () => globalThis.trialRenderCurrentDraft());
    on("closePreflightFailedBtn", "click", closePreflightFailure);
    on("returnToSampleDataBtn", "click", closePreflightFailure);
    on("newTemplateBtn", "click", () => {
      clearDraftView();
      globalThis.setWorkbenchStage("upload");
    });
    on("createDraftFromPublishedBtn", "click", () => {
      createDraftFromPublished().catch((error) => showScanFailure(friendlyError(error, "创建草稿失败，请稍后重试。")));
    });
    document.querySelectorAll("#v2CheckRail .check-item").forEach((item) => {
      item.addEventListener("click", () => {
        const key = item.dataset.checkKey || "";
        if (["slots", "content", "dimensions", "colors"].includes(key)) globalThis.setWorkbenchStage("rules");
        else if (key === "preview") globalThis.setWorkbenchStage("preview");
        else globalThis.setWorkbenchStage("structure");
      });
    });
    bindDropzone();
  }

  function on(id, type, handler) {
    const el = $(id);
    if (el) el.addEventListener(type, handler);
  }

  function handleDraftFieldInput() {
    invalidatePreviewIfAvailable("模板信息已修改，请重新试渲染。");
    updateDraftButtons();
  }

  function invalidatePreviewIfAvailable(message) {
    if (typeof globalThis.invalidateTrialResult === "function") globalThis.invalidateTrialResult(message);
  }

  function renderInitialState() {
    setText("draftStatusBadge", "未选择模板");
    setText("draftVersion", "-");
    renderScanProgress("等待选择 .ai 文件", "idle");
    renderScanSummary();
    setText("publishBlockerText", "请先完成草稿配置与人工核验。");
    setText("draftSaveStatusText", "尚未保存本次修改。");
    setDisabled("publishVersionBtn", true);
    setDisabled("trialRenderBtn", true);
    globalThis.setWorkbenchStage("upload");
    updateCheckRail(defaultChecks());
    updateDraftButtons();
  }


  function renderStructureTreeFallback() {
    const target = $("structureTree");
    if (!target) return;
    target.replaceChildren();
    if (typeof scanModel !== "function") {
      target.appendChild(emptyNode("页面正在加载，请稍后重试。"));
      return;
    }
    const model = scanModel(state.scan || {}, state.draft && state.draft.config);
    const search = valueOf("structureSearch").trim().toLowerCase();
    if (!model || !modelHasItems(model)) {
      target.appendChild(emptyNode("等待扫描结果"));
      setText("selectedNodeSummary", "扫描接口未就绪或尚未返回结构。");
      return;
    }
    const root = document.createElement("section");
    root.className = "structure-tree-root";
    const total = model.designs.length + model.fonts.length + model.styles.length + model.colors.length + model.slots.length + model.assets.length;
    root.appendChild(fallbackTreeRow("Template", `${total} 个变量`, 0, "template", "Template 根组"));
    fallbackOutputs(model).forEach((output, index) => appendFallbackOutput(root, model, output, index, search));
    appendFallbackGroup(root, "Colors", model.colors, 1, "colors", search, false);
    target.appendChild(root);
    appendFallbackFixedObjects(target, model);
    if (globalThis.updateToggleButtons) globalThis.updateToggleButtons();
  }


  function fallbackOutputs(model) {
    if (model.outputs && model.outputs.length) return model.outputs;
    return [{ key: "Output_main", name: "Output_main", display_name: "主效果图" }];
  }


  function appendFallbackOutput(root, model, output, index, search) {
    const key = outputKey(output, index);
    root.appendChild(fallbackTreeRow(key, output.display_name || (key === "Output_main" ? "主效果图" : ""), 1, "output", `输出：${key}`));
    appendFallbackGroup(root, "Style", scopedFallbackItems(model.styles, key, model.outputs.length), 2, "styles", search, false);
    appendFallbackGroup(root, "Design", scopedFallbackItems(model.designs, key, model.outputs.length), 2, "designs", search, !state.expanded.designs);
    appendFallbackGroup(root, "Font", scopedFallbackItems(model.fonts, key, model.outputs.length), 2, "fonts", search, !state.expanded.fonts);
  }


  function appendFallbackGroup(root, label, items, depth, kind, search, collapsed) {
    const visible = filterFallbackItems(items || [], search);
    if (!visible.length) return;
    root.appendChild(fallbackTreeRow(label, `${items.length} 项`, depth, "group", `${label}：${items.length} 项`));
    const shown = collapsed && !search ? visible.slice(0, 3) : visible;
    shown.forEach((item) => {
      const name = item.key || item.name || item.label || label;
      const slots = Array.isArray(item.slots) ? item.slots.map((slot) => slot.key || slot.name).filter(Boolean).slice(0, 3).join(" · ") : "";
      root.appendChild(fallbackTreeRow(name, slots, depth + 1, kind, fallbackSummary(kind, item)));
    });
  }


  function appendFallbackFixedObjects(target, model) {
    const count = fallbackFixedObjectTotal(model);
    if (!count) return;
    const summary = document.createElement("section");
    summary.className = "structure-fixed-summary";
    summary.append(lineNode("未命名固定对象", String(count)), metaNode("固定图案只计数，不展开显示"));
    target.appendChild(summary);
  }


  function fallbackFixedObjectTotal(model) {
    const outputs = Array.isArray(state.scan && state.scan.outputs) ? state.scan.outputs : [];
    const fromSummary = outputs.reduce((total, output) => total + Number(objectOf(output).summary && objectOf(objectOf(output).summary).fixed_objects || 0), 0);
    if (fromSummary) return fromSummary;
    return (model.fixedObjects || []).reduce((total, item) => total + Number(item.count || item.fixed_object_count || 1), 0);
  }


  function fallbackTreeRow(title, meta, depth, kind, summary) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `structure-tree-row depth-${Math.min(depth, 4)}`;
    row.dataset.nodeKind = kind || "";
    row.appendChild(lineNode(title, meta));
    row.addEventListener("click", () => setText("selectedNodeSummary", summary || `${title}${meta ? `；${meta}` : ""}`));
    return row;
  }


  function scopedFallbackItems(items, outputKey, outputCount) {
    const scoped = (items || []).filter((item) => cleanText(item.output || item.output_key || "") === outputKey);
    if (scoped.length) return scoped;
    return outputCount > 1 ? [] : (items || []);
  }


  function filterFallbackItems(items, search) {
    if (!search) return items;
    return items.filter((item) => JSON.stringify(item).toLowerCase().includes(search));
  }


  function outputKey(output, index) {
    const raw = cleanText(output.key || output.name || "");
    if (raw) return raw;
    return index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main";
  }


  function fallbackSummary(kind, item) {
    const name = item.key || item.name || item.label || "未命名";
    const output = item.output ? `；输出：${item.output}` : "";
    return `类型：${kind}；名称：${name}${output}`;
  }

})();


