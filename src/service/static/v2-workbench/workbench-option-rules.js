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
    updateStageActionButtons();
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
    const options = item && typeof contentOptionPresetOptions === "function"
      ? contentOptionPresetOptions(item.output, item.group, item.key)
      : presetOptions(ctx.OPTION_PRESETS);
    const selected = fillSelect("optionContentPreset", options, item ? item.preset : "direct_text");
    const select = $("optionContentPreset");
    const automatic = options.length === 1 && options[0][0] === "mixed_slots";
    if (select) {
      select.disabled = automatic;
      select.setAttribute("aria-readonly", automatic ? "true" : "false");
    }
    setText("optionProcessingHelp", optionProcessingHelpText(selected));
  }

  function optionProcessingHelpText(preset) {
    if (preset === "mixed_slots") {
      return "此设计有多种槽位处理，请在下方分别确认。内容不拆分，顶部不会改写下方设置。";
    }
    if (preset === "split_by_pipe") {
      return "两个槽位都填写同一个内容来源（例如 name）。系统按第 1 段、第 2 段分配；name1、name2 是独立内容来源。";
    }
    return "系统会按当前处理方式推荐槽位处理；需要时可在下方逐项调整。";
  }

  function optionRuleNode(item, index, current) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-rule-item";
    button.dataset.output = item.output;
    button.dataset.option = item.key;
    button.dataset.group = item.group;
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
    const selectedIndex = state.optionRules.selectedIndex;
    const selectedId = visible[selectedIndex] && visible[selectedIndex].id;
    const previousChecks = typeof globalThis.collectChecks === "function" ? globalThis.collectChecks() : null;
    if (typeof globalThis.markCurrentStageConfirmed === "function") {
      globalThis.markCurrentStageConfirmed();
      if (typeof globalThis.updateCheckRail === "function" && typeof globalThis.collectChecks === "function") {
        globalThis.updateCheckRail(globalThis.collectChecks());
      }
    }
    const saveResult = typeof globalThis.saveDraft === "function" ? await globalThis.saveDraft() : null;
    const saved = saveResult === true || Boolean(saveResult && saveResult.saved);
    if (!saved && previousChecks && (!saveResult || saveResult.failure !== "validation") && typeof globalThis.updateCheckRail === "function") {
      globalThis.updateCheckRail(previousChecks);
    }
    if (!saved) return;
    if (!wasRuleStage) {
      state.optionRules.selectedIndex = 0;
      if (typeof globalThis.setWorkbenchStage === "function") globalThis.setWorkbenchStage("rules");
      return;
    }
    const refreshed = filteredRuleOptions();
    const refreshedIndex = refreshed.findIndex((item) => item.id === selectedId);
    const nextIndex = refreshedIndex >= 0 ? refreshedIndex + 1 : selectedIndex;
    if (!refreshed.length || nextIndex >= refreshed.length) {
      if (typeof globalThis.setWorkbenchStage === "function") globalThis.setWorkbenchStage("preview");
      return;
    }
    state.optionRules.selectedIndex = nextIndex;
    renderOptionRuleStage();
  }

  function updateStageActionButtons() {
    const stage = state.stage;
    setHidden("confirmStageBtn", stage !== "preview");
    setHidden("saveAndNextOptionBtn", !["structure", "rules"].includes(stage));
    if (stage === "structure") setText("saveAndNextOptionBtn", "确认并开始配置选项");
    if (stage === "rules") {
      const items = filteredRuleOptions();
      setText("saveAndNextOptionBtn", !items.length || state.optionRules.selectedIndex >= items.length - 1 ? "确认并进入样例预览" : "确认并配置下一个选项");
    }
    if (stage === "preview") setText("confirmStageBtn", "确认样例预览");
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
      const configured = findConfigOption(output, group, safeKey);
      result.push({
        id: `${output}:${group}:${safeKey}`,
        output,
        group,
        key: safeKey,
        label: safeKey,
        status: optionStatus(output, group, safeKey),
        preset: safeOptionPreset(configured.content_preset, recommendedOptionPreset(output, group, safeKey, model))
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
    return typeof recommendedPresetForOption === "function"
      ? recommendedPresetForOption(option)
      : safeOptionPreset(option.content_preset || option.recommended_preset || option.preset, "direct_text");
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
    const selected = options.some(([optionValue]) => optionValue === value) ? value : ((options[0] && options[0][0]) || "");
    select.value = selected;
    return selected;
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
    saveDraftAndSelectNextOption,
    updateStageActionButtons
  });
})();
