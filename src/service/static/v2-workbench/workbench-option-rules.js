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
    renderContentOptionRows();
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

  function renderAssetBindingRows(item) {
    const target = $("assetBindingRows");
    if (!target) return;
    target.replaceChildren();
    if (!item || item.group !== "design") {
      target.appendChild(emptyNode("当前选项不需要素材库绑定。"));
      return;
    }
    const assets = scanModel(state.scan, state.draft && state.draft.config).assets.slice(0, 3);
    const source = assets.length ? assets : [{ name: `${item.label}_asset`, file_name: "asset.ai" }];
    source.forEach((asset) => {
      const row = document.createElement("div");
      row.className = "asset-binding-row";
      row.append(lineNode(cleanText(asset.name || asset.key || "素材"), cleanText(asset.file_name || asset.filename || "Template 图层资产")));
      row.appendChild(statusBadge(item.status === "confirmed" ? "confirmed" : "pending"));
      target.appendChild(row);
    });
  }

  function renderCapabilityEvidence(item) {
    const target = $("capabilityEvidenceRows");
    if (!target) return;
    target.replaceChildren();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    [
      ["Output", item ? item.output : "Output_main"],
      ["槽位", `${model.slots.length || 1} 个可控槽位`],
      ["资产", `${model.assets.length} 个可替换资产`],
      ["状态", item ? statusLabel(item.status) : "等待选择"]
    ].forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "capability-evidence-row";
      row.appendChild(lineNode(label, value));
      target.appendChild(row);
    });
  }

  function renderRuleEvidencePanels(item) {
    renderColorRuleRows(item);
    renderDimensionRuleRows(item);
    renderFontDependencyRows(item);
  }

  function renderColorRuleRows() {
    const target = $("colorRuleRows");
    if (!target) return;
    target.replaceChildren();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const colors = model.colors;
    if (!colors.length) {
      target.appendChild(actionEvidenceRow("无可配置颜色样本", "Template/Colors 未扫描到色块，可确认为仅做生产颜色标注。", "确认无需颜色规则", () => {
        setManualCheck("colors", "confirmed", "无可配置颜色项，仅由公共输出层处理颜色标注");
      }));
      return;
    }
    colors.slice(0, 8).forEach((color) => {
      const name = cleanText(color.key || color.name || color.label || "Color");
      const mode = color.allow_recolor === false ? "仅标注" : "允许实际变色";
      target.appendChild(evidenceRow(name, `${color.space || "RGB"} · ${mode}`));
    });
  }

  function renderDimensionRuleRows(item) {
    const target = $("dimensionRuleRows");
    if (!target) return;
    target.replaceChildren();
    const rules = selectedDimensionRules(item);
    if (!rules.length) {
      target.appendChild(evidenceRow("尺寸边界", "等待扫描 Style 尺寸或槽位边界规则。"));
      return;
    }
    rules.slice(0, 6).forEach((rule) => target.appendChild(evidenceRow(rule.label, rule.value)));
  }

  function renderFontDependencyRows(item) {
    const target = $("fontDependencyRows");
    if (!target) return;
    target.replaceChildren();
    const fonts = selectedFontDependencies(item);
    if (!fonts.length) {
      target.appendChild(evidenceRow("字体依赖", "等待扫描字体或选项字体依赖。"));
      return;
    }
    fonts.slice(0, 8).forEach((font) => target.appendChild(evidenceRow(font, "待本机字体检查确认")));
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

  function selectedDimensionRules(item) {
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const slots = Array.isArray(found.slots) ? found.slots : [];
    return slots.flatMap((slot) => {
      const rule = objectOf(slot.dimension_rule);
      if (!rule.width_mm || !rule.height_mm) return [];
      return [{
        label: slot.key || "slot",
        value: `${rule.width_mm} x ${rule.height_mm} mm · 容差 ${rule.tolerance_mm || "待确认"}`
      }];
    });
  }

  function selectedFontDependencies(item) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const optionFonts = Array.isArray(found.font_dependencies) ? found.font_dependencies : [];
    const slotFonts = (Array.isArray(found.slots) ? found.slots : []).flatMap((slot) => Array.isArray(slot.font_dependencies) ? slot.font_dependencies : []);
    const scanned = item && item.group === "font" ? [item.key] : model.fonts.map((font) => cleanText(font.font || font.name || font.key)).filter(Boolean);
    return unique([...optionFonts, ...slotFonts, ...scanned]);
  }

  function evidenceRow(label, value) {
    const row = document.createElement("div");
    row.className = "capability-evidence-row";
    row.appendChild(lineNode(label, value));
    return row;
  }

  function actionEvidenceRow(label, value, action, handler) {
    const row = evidenceRow(label, value);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-subtle compact-btn";
    button.textContent = action;
    button.addEventListener("click", handler);
    row.appendChild(button);
    return row;
  }

  function setManualCheck(key, status, reason) {
    const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
    if (!item) return;
    item.dataset.status = status;
    item.dataset.reason = reason || "";
    updateCheckRail(collectChecks());
    if (state.draft) validateCurrentConfig(false).catch(() => updateCheckRail(collectChecks()));
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
    const visible = filteredRuleOptions();
    if (typeof globalThis.saveDraft === "function") await globalThis.saveDraft();
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
    const mappings = configOptionMappings().length ? configOptionMappings() : inferredMappings();
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
        preset: recommendedOptionPreset(group, safeKey, model)
      });
    });
  }

  function optionStatus(output, group, key) {
    const found = findConfigOption(output, group, key);
    if (found.content_preset || (Array.isArray(found.slots) && found.slots.length)) return "confirmed";
    return "pending";
  }

  function recommendedOptionPreset(group, optionKey, model) {
    const source = group === "design" ? model.designs : model.fonts;
    const option = objectOf(source.find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
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
    renderRuleEvidencePanels,
    renderColorRuleRows,
    selectRuleOption,
    togglePendingOnlyOptions,
    saveDraftAndSelectNextOption
  });
})();
