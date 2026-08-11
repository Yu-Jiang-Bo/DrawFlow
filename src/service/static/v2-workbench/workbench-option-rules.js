(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderOptionRuleStage() {
    const items = filteredRuleOptions();
    if (state.optionRules.selectedIndex >= items.length) state.optionRules.selectedIndex = Math.max(items.length - 1, 0);
    const current = items[state.optionRules.selectedIndex] || ruleOptionItems()[0] || null;
    renderOptionRuleList(items, current);
    renderOptionRuleControls(current);
    renderContentOptionRows(current);
    renderAssetBindingRows(current);
    renderCapabilityEvidence(current);
    renderRuleEvidencePanels(current);
  }

  function renderOptionRuleList(items, current) {
    const target = $("optionRuleList");
    if (!target) return;
    target.replaceChildren();
    items.forEach((item, index) => target.appendChild(optionRuleNode(item, index, current)));
    if (!items.length) target.appendChild(emptyNode("没有匹配的选项。"));
    setText("optionRuleCount", `${items.length} 项`);
    const all = ruleOptionItems();
    const pending = all.filter((item) => item.status !== "confirmed").length;
    setText("optionRuleStats", `待处理 ${pending} / 全部 ${all.length}`);
    syncPendingOnlyButton();
  }

  function renderOptionRuleControls(item) {
    setText("selectedOptionTitle", item ? `${item.output} · ${item.label}` : "选择一个 Design 或 F 选项");
    setText("selectedOptionPendingBadge", item ? statusLabel(item.status) : "待处理");
    fillSelect("optionContentPreset", presetOptions(ctx.OPTION_PRESETS), item ? item.preset : "direct_text");
    fillSelect("optionContentSeparator", [["pipe", "按 | 顺序拆分"], ["none", "不拆分"]], item && item.preset === "split_by_pipe" ? "pipe" : "none");
  }

  function optionRuleNode(item, index, current) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-rule-item";
    if (current && item.id === current.id) button.classList.add("active");
    button.appendChild(lineNode(item.label, `${item.output} · ${item.group === "font" ? "F" : "Design"}`));
    button.appendChild(statusBadge(item.status));
    button.addEventListener("click", () => selectRuleOption(index));
    return button;
  }

  function selectRuleOption(index) {
    state.optionRules.selectedIndex = Math.max(Number(index) || 0, 0);
    renderOptionRuleStage();
  }

  function togglePendingOnlyOptions() {
    state.optionRules.pendingOnly = !state.optionRules.pendingOnly;
    state.optionRules.selectedIndex = 0;
    renderOptionRuleStage();
  }

  async function saveDraftAndSelectNextOption() {
    const wasRuleStage = state.stage === "rules";
    const visible = filteredRuleOptions();
    if (typeof globalThis.saveDraft === "function") await globalThis.saveDraft();
    if (!wasRuleStage) {
      state.optionRules.selectedIndex = 0;
      if (typeof globalThis.setWorkbenchStage === "function") globalThis.setWorkbenchStage("rules");
      return;
    }
    const nextLength = filteredRuleOptions().length || visible.length;
    state.optionRules.selectedIndex = nextLength ? (state.optionRules.selectedIndex + 1) % nextLength : 0;
    renderOptionRuleStage();
  }

  function filteredRuleOptions() {
    const search = cleanText(valueOf("optionRuleSearch")).toLowerCase();
    return ruleOptionItems().filter((item) => {
      if (state.optionRules.pendingOnly && item.status === "confirmed") return false;
      if (!search) return true;
      return `${item.label} ${item.output} ${item.group}`.toLowerCase().includes(search);
    });
  }

  function ruleOptionItems() {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const mappings = effectiveOptionMappings();
    const result = [];
    outputs.forEach((output, outputIndex) => {
      const fallback = outputIndex ? `Output_Side${String.fromCharCode(65 + outputIndex)}` : "Output_main";
      const outputKey = safeOutputKey(output.key || output.name, fallback, outputIndex);
      appendRuleOptions(result, outputKey, "design", optionKeysFor(outputKey, "design", mappings, model.designs), model);
      appendRuleOptions(result, outputKey, "font", optionKeysFor(outputKey, "font", mappings, model.fonts), model);
    });
    return result;
  }

  function appendRuleOptions(result, output, group, keys, model) {
    keys.forEach((key) => {
      const safeKey = safeOptionKey(key, group);
      if (!safeKey) return;
      result.push({
        id: `${output}:${group}:${safeKey}`,
        output,
        group,
        key: safeKey,
        label: safeKey,
        status: optionStatus(output, group, safeKey),
        preset: recommendedOptionPreset(output, group, safeKey, model)
      });
    });
  }

  function optionStatus(output, group, key) {
    const found = findConfigOption(output, group, key);
    if (found.content_preset || (Array.isArray(found.slots) && found.slots.length)) return "confirmed";
    return "pending";
  }

  function recommendedOptionPreset(output, group, optionKey, model) {
    const source = group === "design" ? model.designs : model.fonts;
    const option = objectOf(scopedScanItemsFor(output, source).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    return safeOptionPreset(option.content_preset || option.recommended_preset || option.preset, "direct_text");
  }

  function fillSelect(id, options, value) {
    const select = $(id);
    if (!select) return;
    select.replaceChildren();
    options.forEach(([optionValue, label]) => {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = value || (options[0] && options[0][0]) || "";
  }

  function syncPendingOnlyButton() {
    const button = $("pendingOnlyBtn");
    if (!button) return;
    button.classList.toggle("active", Boolean(state.optionRules.pendingOnly));
    button.setAttribute("aria-pressed", state.optionRules.pendingOnly ? "true" : "false");
    button.textContent = state.optionRules.pendingOnly ? "显示全部选项" : "仅显示待处理选项";
  }

  function statusBadge(status) {
    const badge = document.createElement("span");
    badge.className = `stage-status-pill ${status === "confirmed" ? "success" : status === "blocked" ? "blocked" : "warn"}`;
    badge.textContent = statusLabel(status);
    return badge;
  }

  function statusLabel(status) {
    return (ctx.STATUS_LABELS && ctx.STATUS_LABELS[status]) || "待校验";
  }

  Object.assign(globalThis, {
    renderOptionRuleStage,
    renderOptionRuleList,
    selectRuleOption,
    filteredRuleOptions,
    ruleOptionItems,
    togglePendingOnlyOptions,
    saveDraftAndSelectNextOption
  });
})();
