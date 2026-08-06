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
    const source = configured.length ? configured : scopedScanItemsFor(item.output, scanned);
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
    [
      ["Output", item ? item.output : "Output_main"],
      ["槽位", `${model.slots.length || 1} 个可控槽位`],
      ["资产", `${model.assets.length} 个可替换资产`],
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
    validateCurrentConfig(false).catch(() => updateCheckRail(collectChecks()));
  }

  function selectedDimensionRules(item) {
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const output = configOutputs().find((candidate) => item && safeOutputKey(candidate.key, "Output_main", 0) === item.output);
    const styleRules = (Array.isArray(objectOf(objectOf(output).style).options) ? objectOf(objectOf(output).style).options : []).flatMap((style) => {
      const rule = objectOf(style.dimensions);
      if (!rule.width_mm || !rule.height_mm) return [];
      return [{
        label: `${objectOf(style).key || "style"} · 最终边界`,
        value: `${rule.width_mm} x ${rule.height_mm} mm · X/Y 独立 · 容差 ${rule.tolerance_mm || 0.007}mm`
      }];
    });
    const slots = Array.isArray(found.slots) ? found.slots : [];
    const slotRules = slots.flatMap((slot) => {
      const rule = objectOf(slot.dimension_rule);
      if (!rule.width_mm || !rule.height_mm) return [];
      return [{
        label: slot.key || "slot",
        value: `${rule.width_mm} x ${rule.height_mm} mm · X/Y 独立 · 容差 ${rule.tolerance_mm || 0.007}mm`
      }];
    });
    return [...styleRules, ...slotRules];
  }

  function selectedFontDependencies(item) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const found = item ? findConfigOption(item.output, item.group, item.key) : {};
    const optionFonts = Array.isArray(found.font_dependencies) ? found.font_dependencies : [];
    const slotFonts = (Array.isArray(found.slots) ? found.slots : []).flatMap((slot) => Array.isArray(slot.font_dependencies) ? slot.font_dependencies : []);
    const scanned = item && item.group === "font" ? [item.key] : scopedScanItemsFor(item && item.output, model.fonts).map((font) => cleanText(font.font || font.name || font.key)).filter(Boolean);
    return unique([...optionFonts, ...slotFonts, ...scanned]);
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
