(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderAssetBindingRows(item) {
    const target = $("assetBindingRows");
    if (!target) return;
    target.replaceChildren();
    if (!item || item.group !== "design") {
      target.appendChild(emptyNode("当前选项不需要素材库绑定。"));
      return;
    }
    const found = findConfigOption(item.output, item.group, item.key);
    const configured = Array.isArray(found.assets) ? found.assets : [];
    const scanned = scanModel(state.scan, state.draft && state.draft.config).assets;
    const source = configured.length ? configured : scopedOptionItemsFor(item.output, item.group, item.key, scanned);
    if (!source.length) {
      target.appendChild(emptyNode("等待 Assets 扫描或在槽位行填写素材键。"));
      return;
    }
    source.forEach((asset) => {
      const key = cleanText(asset.asset_key || asset.key || asset.name || "素材");
      const slot = cleanText(asset.slot || `slot_${key}`);
      const values = supportedValuesLabel(asset);
      const row = document.createElement("div");
      row.className = "asset-binding-row";
      row.append(lineNode(key, `支持 ${values} · ${slot}`));
      row.appendChild(evidenceStatusBadge(values === "待确认" ? "pending" : "confirmed"));
      target.appendChild(row);
    });
  }

  function renderCapabilityEvidence(item) {
    const target = $("capabilityEvidenceRows");
    if (!target) return;
    target.replaceChildren();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const slots = item ? selectedOptionSlotsForEvidence(item, model) : model.slots;
    const assets = item && item.group === "design" ? selectedOptionAssetsForEvidence(item, model) : [];
    [
      ["Output", item ? item.output : "Output_main"],
      ["槽位", `${slots.length || 1} 个可控槽位`],
      ["资产", `${assets.length} 个可替换资产`],
      ["状态", item ? statusLabel(item.status) : "等待选择"]
    ].forEach(([label, value]) => target.appendChild(evidenceRow(label, value)));
  }

  function renderRuleEvidencePanels(item) {
    renderColorRuleRows();
    renderDimensionRuleRows(item);
    renderFontDependencyRows(item);
  }

  function renderColorRuleRows() {
    const target = $("colorRuleRows");
    if (!target) return;
    target.replaceChildren();
    const colors = scanModel(state.scan, state.draft && state.draft.config).colors;
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

  function applySelectedOptionControls() {
    const item = filteredRuleOptions()[state.optionRules.selectedIndex] || ruleOptionItems()[0];
    if (!item) return;
    const preset = valueOf("optionContentSeparator") === "pipe" ? "split_by_pipe" : valueOf("optionContentPreset");
    const group = Array.from(document.querySelectorAll("#contentOptionRows .content-option-group")).find((row) => (
      row.dataset.output === item.output && row.dataset.group === item.group && row.dataset.option === item.key
    ));
    const select = group && group.querySelector('[data-field="option-content-preset"]');
    if (!select) return;
    select.value = safeOptionPreset(preset, "direct_text");
    Array.from(document.querySelectorAll("#contentOptionRows .content-slot-row"))
      .filter((row) => row.dataset.output === item.output && row.dataset.group === item.group && row.dataset.option === item.key)
      .forEach((row) => {
        const slotSelect = row.querySelector('[data-field="slot-preset"]');
        if (slotSelect) slotSelect.value = syncedSlotPreset(row, slotSelect, select.value);
      });
    validateCurrentConfig(false).catch(() => updateCheckRail(collectChecks()));
  }

  function syncedSlotPreset(row, slotSelect, optionPreset) {
    const tails = [
      rowValue(row, "slot-tail-first"),
      rowValue(row, "slot-tail-last")
    ].filter(Boolean).map((sample, index) => ({ key: `tail_sync_${index}_${sample}`, position: index ? "last" : "first", sample }));
    const item = {
      key: row && row.dataset ? row.dataset.slotKey : "",
      preset: slotSelect.value,
      asset_key: rowValue(row, "slot-asset-key"),
      tails
    };
    return typeof slotPresetForOption === "function" ? slotPresetForOption(item, optionPreset) : safePreset(optionPreset, "direct_text");
  }

  function selectedDimensionRules(item) {
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const output = configOutputs().find((candidate) => item && safeOutputKey(candidate.key, "Output_main", 0) === item.output);
    const styleRules = (Array.isArray(objectOf(objectOf(output).style).options) ? objectOf(objectOf(output).style).options : []).flatMap((style) => {
      const rule = objectOf(style.dimensions);
      if (!rule.width_mm || !rule.height_mm) return [];
      return [{
        label: `${objectOf(style).key || "style"} · 最终边界`,
        value: `${rule.width_mm} x ${rule.height_mm} mm · 误差上限 ${rule.tolerance_mm || 0.007}mm，禁止超出`
      }];
    });
    const slots = Array.isArray(found.slots) ? found.slots : [];
    const slotRules = slots.flatMap((slot) => {
      const rule = objectOf(slot.dimension_rule);
      if (!rule.width_mm || !rule.height_mm) return [];
      return [{
        label: slot.key || "slot",
        value: `${rule.width_mm} x ${rule.height_mm} mm · 误差上限 ${rule.tolerance_mm || 0.007}mm，禁止超出`
      }];
    });
    return [...styleRules, ...slotRules];
  }

  function selectedFontDependencies(item) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const optionFonts = Array.isArray(found.font_dependencies) ? found.font_dependencies : [];
    const slots = item ? selectedOptionSlotsForEvidence(item, model) : [];
    const slotFonts = slots.flatMap((slot) => Array.isArray(slot.font_dependencies) ? slot.font_dependencies : []);
    const scannedOption = item ? selectedScanOptionForEvidence(item, model) : {};
    const scannedOptionFonts = [scannedOption.font_name, scannedOption.font].map(cleanText).filter(Boolean);
    const scanned = item && item.group === "font" ? [item.key] : scannedOptionFonts;
    return unique([...optionFonts, ...slotFonts, ...scanned]);
  }

  function selectedOptionSlotsForEvidence(item, model) {
    const found = findConfigOption(item.output, item.group, item.key);
    if (Array.isArray(found.slots) && found.slots.length) return found.slots;
    const scannedOption = selectedScanOptionForEvidence(item, model);
    if (Array.isArray(scannedOption.slots) && scannedOption.slots.length) return scannedOption.slots;
    return scopedOptionItemsFor(item.output, item.group, item.key, model.slots);
  }

  function selectedOptionAssetsForEvidence(item, model) {
    const found = findConfigOption(item.output, item.group, item.key);
    if (Array.isArray(found.assets) && found.assets.length) return found.assets;
    const scannedOption = selectedScanOptionForEvidence(item, model);
    if (Array.isArray(scannedOption.assets) && scannedOption.assets.length) return scannedOption.assets;
    return scopedOptionItemsFor(item.output, item.group, item.key, model.assets);
  }

  function selectedScanOptionForEvidence(item, model) {
    const source = item.group === "font" ? model.fonts : model.designs;
    return objectOf(scopedScanItemsFor(item.output, source).find((option) => (
      safeOptionKey(option.key || option.name || option.label, item.group) === item.key
    )));
  }

  function supportedValuesLabel(asset) {
    const value = asset.supported_values || asset.values || asset.characters || asset.range || [];
    if (Array.isArray(value) && value.length) return `${value.length} 个`;
    if (typeof value === "string" && value.trim()) return value;
    return "待确认";
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

  function evidenceStatusBadge(status) {
    const badge = document.createElement("span");
    badge.className = `stage-status-pill ${status === "confirmed" ? "success" : status === "blocked" ? "blocked" : "warn"}`;
    badge.textContent = statusLabel(status);
    return badge;
  }

  function statusLabel(status) {
    return (ctx.STATUS_LABELS && ctx.STATUS_LABELS[status]) || "待校验";
  }

  Object.assign(globalThis, {
    renderAssetBindingRows,
    renderCapabilityEvidence,
    renderRuleEvidencePanels,
    renderColorRuleRows,
    applySelectedOptionControls
  });
})();
