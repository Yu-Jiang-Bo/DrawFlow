(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderTemplateStats(items) {
    const target = $("templateListStats");
    if (!target) return;
    const source = Array.isArray(items) ? items : state.templates;
    const published = source.filter((item) => objectOf(item.publication).current_version).length;
    const drafts = source.filter((item) => item.draft || !objectOf(item.publication).current_version).length;
    const updated = source.length ? "刚刚" : "-";
    target.replaceChildren(
      statRow("正式模板", published),
      statRow("待发布草稿", drafts),
      statRow("最近更新", updated),
      versionPolicyNode()
    );
  }


  function statRow(label, value) {
    const row = document.createElement("div");
    row.className = "template-stat-row";
    const span = document.createElement("span");
    const strong = document.createElement("strong");
    span.textContent = label;
    strong.textContent = String(value);
    row.append(span, strong);
    return row;
  }


  function versionPolicyNode() {
    const row = document.createElement("div");
    row.className = "version-policy-note";
    row.textContent = "版本策略：保留当前正式版与上一回滚版";
    return row;
  }


  function renderScanMetrics(summary) {
    const target = $("scanSummaryMetrics");
    if (!target) return;
    target.replaceChildren(
      metricNode("Output", summary.outputs || 0),
      metricNode("Design", summary.designs || 0),
      metricNode("Font", summary.fonts || 0),
      metricNode("可变槽位", summary.slots || 0),
      metricNode("素材库", summary.assets || 0)
    );
  }


  function metricNode(label, value) {
    const node = document.createElement("div");
    node.className = "scan-metric";
    const span = document.createElement("span");
    const strong = document.createElement("strong");
    span.textContent = label;
    strong.textContent = String(value);
    node.append(span, strong);
    return node;
  }


  function scanWarningText(summary, hasScan) {
    if (!hasScan) return "等待扫描结果。完成扫描后先核对规范标注字段，再进入结构与字段核验。";
    if ((summary.outputs || 0) > 1) return "待核验：检测到多个 Output，请进入下一步填写中文部件名并确认订单字段绑定。";
    return "待核验：扫描摘要只陈述 AI 文件事实，字段绑定和选项映射需要进入下一步人工确认。";
  }


  function renderScanProgress(message, mode) {
    const target = $("scanProgress");
    if (!target) return;
    const status = mode || (state.isScanning ? "active" : "idle");
    const hasScan = scanSummary(state.scan || {}).total > 0 || Object.keys(state.scan || {}).length > 0;
    const steps = [
      ["文件已保存", state.uploadFile || state.draft || hasScan ? "success" : ""],
      ["Illustrator 结构扫描", hasScan ? "success" : (status === "active" ? "active" : "")],
      ["规范变量提取", hasScan ? "success" : ""],
      [message || (hasScan ? "等待人工核验" : "等待选择 .ai 文件"), hasScan ? "active" : ""]
    ];
    target.replaceChildren(...steps.map(([text, className]) => scanStepNode(text, className)));
  }


  function scanStepNode(text, className) {
    const step = document.createElement("div");
    step.className = `scan-step ${className || ""}`.trim();
    const body = document.createElement("div");
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    strong.textContent = text;
    span.textContent = className === "success" ? "已完成" : (className === "active" ? "当前步骤" : "等待");
    body.append(strong, span);
    step.appendChild(body);
    return step;
  }


  function setWorkbenchStage(stage) {
    const next = stage === "structure" ? "structure" : "upload";
    state.stage = next;
    const app = $("v2WorkbenchApp");
    if (app) app.dataset.workbenchStage = next;
    setHidden("backToUploadBtn", next !== "structure");
    setText("v2PageTitle", next === "structure" ? "结构与字段核验" : "V2 模板配置工作台");
    if (next === "structure") {
      renderStructureTree();
      renderTables();
      validateCurrentConfig(false).catch(() => updateCheckRail(configChecks()));
    } else {
      renderScanSummary();
      updateCheckRail(defaultChecks());
    }
    updateDraftButtons();
  }


  Object.assign(globalThis, {
    renderTemplateStats,
    renderScanMetrics,
    renderScanProgress,
    setWorkbenchStage,
    scanWarningText
  });
})();
