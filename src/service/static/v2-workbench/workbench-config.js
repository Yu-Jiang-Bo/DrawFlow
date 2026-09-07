(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, CHECK_KEYS } = ctx;
  const DIMENSION_TOLERANCE_MM = 0.007;

  function buildControlledConfig() {
    const basics = formBasics();
    const outputs = collectOutputRows();
    const mappings = collectOptionMappingRows();
    const checks = collectChecks();
    const config = {
      "$schema": "custom-renderer/v2-template-contract",
      schema_version: 1,
      template: {
        template_id: basics.template_id,
        name: basics.name,
        shop_name: basics.shop_name,
        component_key: "main",
        scope: "local"
      },
      outputs: outputs.map((output) => withControlledGroups(output, mappings)),
      output: collectOutputPolicy(),
      colors: collectControlledColors(),
      field_bindings: collectFieldBindings(),
      option_mappings: mappings,
      checks,
      preview: { sample_rows: [], evidence: {} },
      audit: nextAudit()
    };
    const renderMode = collectRenderMode();
    if (renderMode) config.render_mode = renderMode;
    return config;
  }

  function collectRenderMode() {
    const existing = objectOf(state.draft && state.draft.config);
    if (["single_customization", "multi_customization"].includes(state.pendingRenderMode)) {
      return state.pendingRenderMode;
    }
    const single = document.getElementById("singleCustomizationTemplate");
    const multi = document.getElementById("multiCustomizationTemplate");
    if (multi && multi.checked) return "multi_customization";
    if (single && single.checked) return "single_customization";
    return storedRenderMode(existing);
  }

  function syncRenderModeControls() {
    const existing = objectOf(state.draft && state.draft.config);
    const mode = ["single_customization", "multi_customization"].includes(state.pendingRenderMode)
      ? state.pendingRenderMode
      : storedRenderMode(existing);
    const single = document.getElementById("singleCustomizationTemplate");
    const multi = document.getElementById("multiCustomizationTemplate");
    if (single) single.checked = mode === "single_customization";
    if (multi) multi.checked = mode === "multi_customization";
  }

  function storedRenderMode(config) {
    if (config.render_mode === "multi_customization") return "multi_customization";
    if (config.render_mode === "single_customization") return "single_customization";
    const legacy = objectOf(config.multi_name_customization);
    if (!config.render_mode && legacy.enabled === true) return "multi_customization";
    return !state.draft && !Object.keys(config).length ? "single_customization" : "";
  }

  function collectOutputPolicy() {
    const existing = objectOf(state.draft && state.draft.config && state.draft.config.output);
    const outline = document.getElementById("outlineTextToggle");
    const merge = document.getElementById("pathfinderMergeToggle");
    return {
      outline_text: outline ? outline.checked : existing.outline_text !== false,
      pathfinder_merge: merge ? merge.checked : existing.pathfinder_merge !== false
    };
  }

  function syncOutputPolicyControls() {
    const existing = objectOf(state.draft && state.draft.config && state.draft.config.output);
    const outline = document.getElementById("outlineTextToggle");
    const merge = document.getElementById("pathfinderMergeToggle");
    if (outline) outline.checked = existing.outline_text !== false;
    if (merge) merge.checked = existing.pathfinder_merge !== false;
  }



  function collectOutputRows() {
    const rows = Array.from(document.querySelectorAll("#outputConfigRows .output-row")).filter((row) => !row.className.includes("table-head"));
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const result = rows.map((row, index) => {
      const key = cleanText(rowValue(row, "output-key"));
      const singleMain = rows.length === 1 && key === "Output_main";
      const existing = existingOutputConfig(key);
      return {
        key,
        display_name: cleanText(rowValue(row, "output-name")) || (singleMain ? "主效果图" : ""),
        component_key: safeIdentifier(rowValue(row, "output-component"), singleMain ? "main" : ""),
        scope: "local",
        style: { field: outputGroupField(key, "style", existing, model), options: [] },
        design: { field: outputGroupField(key, "design", existing, model), options: [] },
        font: { field: outputGroupField(key, "font", existing, model), options: [] }
      };
    });
    return result.length ? result : [emptyOutput()];
  }

  function existingOutputConfig(key) {
    return objectOf(configOutputs().find((item) => safeOutputKey(item.key || item.name, "Output_main", 0) === key));
  }

  function outputGroupField(output, group, existing, model) {
    const existingGroup = objectOf(existing[group]);
    const scannedItems = group === "style" ? model.styles : group === "font" ? model.fonts : model.designs;
    if (!hasScanBackedGroupForOutput(output, group, scannedItems)) return "";
    return safeField(existingGroup.field) || inferredGroupField(group);
  }

  function hasScanBackedGroupForOutput(output, group, scannedItems) {
    if (scopedScanItemsFor(output, scannedItems).length) return true;
    return configOptionMappings().some((mapping) => (
      safeOutputKey(mapping.output, "Output_main", 0) === output
      && mapping.group === group
      && optionExistsInUnscopedScanItems(scannedItems, mapping.target, group)
    ));
  }



  function withControlledGroups(output, mappings) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    return {
      ...output,
      style: { field: output.style.field, options: styleOptionsFor(output.key, mappings, model.styles) },
      design: { field: output.design.field, options: designOptionsFor(output.key, mappings, model.designs, model.slots) },
      font: { field: output.font.field, options: fontOptionsFor(output.key, mappings, model.fonts, model.slots) }
    };
  }



  function collectFieldBindings() {
    const allowed = inferredFields();
    const result = {};
    Array.from(document.querySelectorAll("#fieldBindingRows .field-binding-row")).forEach((row) => {
      const key = safeField(rowValue(row, "binding-field"));
      const value = cleanText(rowValue(row, "binding-column"));
      if (key && value && fieldBindingAllowed(key, allowed)) result[key] = value;
    });
    return result;
  }

  function fieldBindingAllowed(field, allowed) {
    const key = safeField(field);
    return Boolean(key) && allowed.includes(key);
  }



  function collectOptionMappingRows() {
    const rows = Array.from(document.querySelectorAll("#optionMappingRows .option-mapping-row")).map((row) => {
      const group = rowValue(row, "mapping-group");
      const output = safeOutputKey(rowValue(row, "mapping-output"), "Output_main", 0);
      const target = safeOptionKey(rowValue(row, "mapping-target"), group);
      return {
        field: safeField(rowValue(row, "mapping-field")),
        source_value: cleanText(rowValue(row, "mapping-source")),
        target,
        output,
        group: ["style", "design", "font", "color"].includes(group) ? group : "design"
      };
    }).filter((item) => item.field && item.source_value && item.target && item.output && item.group);
    return mergeOptionMappings(scanBackedOptionMappings(rows), inferredMappings());
  }

  function effectiveOptionMappings() {
    const configured = scanBackedOptionMappings(configOptionMappings());
    return mergeOptionMappings(configured, inferredMappings());
  }

  function mergeOptionMappings(primary, fallback) {
    const result = [];
    const seenPrimaryTargets = new Set();
    const seenFallbackTargets = new Set();
    const add = (mapping, source) => {
      const group = ["style", "design", "font", "color"].includes(mapping.group) ? mapping.group : "design";
      const normalized = {
        field: safeField(mapping.field),
        source_value: cleanText(mapping.source_value),
        target: safeOptionKey(mapping.target, group),
        output: safeOutputKey(mapping.output, "Output_main", 0),
        group
      };
      if (!normalized.field || !normalized.source_value || !normalized.target || !normalized.output) return;
      const targetKey = `${normalized.output}::${normalized.group}::${normalized.target}`;
      if (source === "fallback") {
        if (seenPrimaryTargets.has(targetKey) || seenFallbackTargets.has(targetKey)) return;
        seenFallbackTargets.add(targetKey);
      } else {
        seenPrimaryTargets.add(targetKey);
      }
      result.push(normalized);
    };
    (Array.isArray(primary) ? primary : []).forEach((mapping) => add(mapping, "primary"));
    (Array.isArray(fallback) ? fallback : []).forEach((mapping) => add(mapping, "fallback"));
    return result;
  }

  function scanBackedOptionMappings(mappings) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    return (Array.isArray(mappings) ? mappings : []).map((mapping) => {
      const group = ["style", "design", "font", "color"].includes(mapping.group) ? mapping.group : "design";
      return {
        field: safeField(mapping.field),
        source_value: cleanText(mapping.source_value),
        target: safeOptionKey(mapping.target, group),
        output: safeOutputKey(mapping.output, "Output_main", 0),
        group
      };
    }).filter((mapping) => mapping.field && mapping.source_value && mapping.target && optionMappingHasScannedTarget(mapping, model));
  }

  function optionMappingHasScannedTarget(mapping, model) {
    if (mapping.group === "color") {
      return model.colors.some((item) => safeOptionKey(item.key || item.name || item.label, "color") === mapping.target);
    }
    const source = mapping.group === "style" ? model.styles : mapping.group === "font" ? model.fonts : model.designs;
    return scopedScanItemsFor(mapping.output, source)
      .some((item) => safeOptionKey(item.key || item.name || item.label, mapping.group) === mapping.target)
      || optionExistsInUnscopedScanItems(source, mapping.target, mapping.group);
  }

  function optionExistsInUnscopedScanItems(scanItems, target, group) {
    const items = Array.isArray(scanItems) ? scanItems : [];
    if (items.some((item) => outputScopeKey(item))) return false;
    const safeTarget = safeOptionKey(target, group);
    return items.some((item) => safeOptionKey(item.key || item.name || item.label, group) === safeTarget);
  }


  function collectChecks() {
    const result = defaultChecks();
    CHECK_KEYS.forEach((key) => {
      const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
      const status = item ? String(item.dataset.status || "") : "";
      if (["confirmed", "pending", "blocked"].includes(status)) result[key] = { status, reason: manualCheckReasonForConfig(item.dataset.reason || "") };
    });
    const outputRows = Array.from(document.querySelectorAll("#outputConfigRows .output-row"));
    if (outputRows.length === 1 && safeOutputKey(rowValue(outputRows[0], "output-key"), "Output_main", 0) === "Output_main") {
      result.output = { status: "confirmed", reason: "单 Output_main 自动确认" };
    }
    return result;
  }

  function manualCheckReasonForConfig(value) {
    let reason = cleanText(value);
    const emptySentences = ["人工核验项还没有确认", "人工核验项还没有确认。", "人工核验项被标记为阻断", "人工核验项被标记为阻断。"];
    const prefixes = ["人工核验项还没有确认：", "人工核验项还没有确认:", "人工核验项被标记为阻断：", "人工核验项被标记为阻断:"];
    let changed = true;
    while (changed) {
      if (emptySentences.includes(reason)) return "";
      changed = false;
      prefixes.forEach((prefix) => {
        if (reason.indexOf(prefix) === 0) {
          reason = cleanText(reason.slice(prefix.length));
          changed = true;
        }
      });
    }
    if (emptySentences.includes(reason)) return "";
    return looksLikeValidationReason(reason) ? "" : reason;
  }


  function looksLikeValidationReason(reason) {
    if (!reason) return false;
    const markers = ["还没有绑定到真实表头", "还没有映射到订单原值", "发布前预览缺少", "缺少代表性测试数据"];
    if (markers.some((marker) => reason.includes(marker))) return true;
    const pairs = [
      ["槽位内容来源", "真实表头"],
      ["订单字段", "真实表头"],
      ["颜色扫描值", "还没有"],
      ["素材范围", "还没有"],
      ["最终边界", "还没有"],
      ["最终边界", "不允许"],
      ["同一作用域", "重复"],
      ["同一作用域", "不允许"]
    ];
    return pairs.some(([left, right]) => reason.includes(left) && reason.includes(right));
  }



  function collectControlledColors() {
    return scanModel(state.scan, state.draft && state.draft.config).colors.map((item, index) => {
      const name = cleanText(item.name || item.key || item.label || `Color${index + 1}`);
      const value = item.value;
      if (Array.isArray(value) && value.length === 3 && value.every(isFiniteNumber)) {
        return { key: safeIdentifier(name, `Color${index + 1}`), zh_name: name, space: "RGB", value: value.map(Number), allow_recolor: true };
      }
      if (Array.isArray(value) && value.length === 4 && value.every(isFiniteNumber)) {
        return { key: safeIdentifier(name, `Color${index + 1}`), zh_name: name, space: "CMYK", value: value.map(Number), allow_recolor: true };
      }
      return null;
    }).filter(Boolean);
  }



  function nextAudit() {
    const config = objectOf(state.draft && state.draft.config);
    const audit = objectOf(config.audit);
    return {
      scan_version: "",
      template_sha256: "",
      config_version: Number(audit.config_version || 0) + 1
    };
  }



  function styleOptionsFor(output, mappings, styles) {
    const dimensions = collectStyleDimensionConfigs();
    const keys = unique([...optionKeysFor(output, "style", mappings, styles), ...Object.keys(dimensions[output] || {})]);
    return keys.map((key) => ({
      key: safeOptionKey(key, "style"),
      label: key,
      dimensions: styleDimensionsFor(output, key, dimensions, styles),
      component_key: "",
      scope: "local"
    })).filter((item) => item.key);
  }



  function designOptionsFor(output, mappings, designs, slots) {
    const content = collectContentOptionConfigs();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    return optionKeysFor(output, "design", mappings, designs).map((key) => {
      const optionSlots = contentOptionSlots(content, output, "design", key, slots, model);
      return {
        key: safeOptionKey(key, "design"),
        label: key,
        content_preset: contentOptionPreset(content, output, "design", key, model),
        component_key: "",
        scope: "local",
        font_dependencies: optionFontDependencies(output, "design", key, optionSlots),
        slots: optionSlots,
        assets: optionAssetsFor(output, "design", key, optionSlots, model.assets)
      };
    }).filter((item) => item.key);
  }



  function fontOptionsFor(output, mappings, fonts, slots) {
    const content = collectContentOptionConfigs();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    return optionKeysFor(output, "font", mappings, fonts).map((key) => {
      const optionKey = safeOptionKey(key, "font");
      const optionSlots = contentOptionSlots(content, output, "font", key, slots, model)
        .map((slot) => cleanFontOptionSlotDependencies(optionKey, slot));
      return {
        key: optionKey,
        label: key,
        content_preset: contentOptionPreset(content, output, "font", key, model),
        component_key: "",
        scope: "local",
        font_dependencies: optionFontDependencies(output, "font", key, optionSlots, []),
        slots: optionSlots,
        assets: []
      };
    }).filter((item) => item.key);
  }

  function cleanFontOptionSlotDependencies(optionKey, slot) {
    return {
      ...slot,
      font_dependencies: Array.isArray(slot.font_dependencies)
        ? slot.font_dependencies.filter((font) => !isFontOptionSelfDependency("font", optionKey, font))
        : []
    };
  }



  function optionKeysFor(output, group, mappings, scanItems) {
    const scanned = scopedScanItemsFor(output, scanItems).map((item) => safeOptionKey(item.key || item.name || item.label, group)).filter(Boolean);
    const scannedKeys = new Set(scanned);
    const mapped = mappings
      .filter((item) => item.output === output && item.group === group)
      .map((item) => safeOptionKey(item.target, group))
      .filter((target) => scannedKeys.has(target) || optionExistsInUnscopedScanItems(scanItems, target, group));
    return unique([...mapped, ...scanned]).slice(0, 30);
  }



  function scopedScanItemsFor(output, scanItems) {
    const scoped = scanItems.filter((item) => outputScopeKey(item));
    if (scoped.length) return scoped.filter((item) => outputScopeKey(item) === output);
    return currentOutputCount() > 1 ? [] : scanItems;
  }



  function outputScopeKey(item) {
    const data = objectOf(item);
    const nested = objectOf(data.output);
    const candidates = [
      nested.key,
      nested.name,
      data.output_key,
      data.outputKey,
      data.parent_output,
      data.parentOutput,
      data.output,
      data.artboard_key,
      data.page_key
    ];
    const found = candidates.map((candidate) => cleanText(candidate)).find((text) => text === "Output_main" || /^Output_Side[A-Z]$/.test(text));
    return found || "";
  }



  function currentOutputCount() {
    const rows = document.querySelectorAll("#outputConfigRows .output-row");
    if (rows.length) return rows.length;
    const configured = configOutputs();
    if (configured.length) return configured.length;
    return inferredOutputs().length;
  }

  function collectStyleDimensionConfigs() {
    const result = {};
    Array.from(document.querySelectorAll("#styleDimensionRows .style-dimension-row")).filter((row) => !row.className.includes("table-head")).forEach((row) => {
      const output = safeOutputKey(rowValue(row, "style-output") || row.dataset.output, "Output_main", 0);
      const key = safeOptionKey(rowValue(row, "style-key") || row.dataset.styleKey, "style");
      if (!output || !key) return;
      const dimensions = dimensionRuleFromValues(styleDimensionValue(row, "style-width-mm"), styleDimensionValue(row, "style-height-mm"), "fixed");
      if (!result[output]) result[output] = {};
      result[output][key] = dimensions;
    });
    return result;
  }

  function styleDimensionValue(row, field) {
    const input = row.querySelector(`[data-field="${field}"]`);
    if (!input) return "";
    return input.value;
  }

  function styleDimensionsFor(output, key, collected, styles) {
    const rowDimensions = objectOf(objectOf(collected[output])[safeOptionKey(key, "style")]);
    if (Object.keys(rowDimensions).length) return rowDimensions;
    const configured = objectOf(findConfigOption(output, "style", key).dimensions);
    if (Object.keys(configured).length) return normalizedDimensionRule(configured, "fixed");
    const scanned = objectOf(scopedScanItemsFor(output, styles).find((item) => safeOptionKey(item.key || item.name || item.label, "style") === safeOptionKey(key, "style")));
    return normalizedDimensionRule(scanned.dimensions || scanned, "style");
  }

  function optionAssetsFor(output, group, key, slots, scannedAssets) {
    const existing = Array.isArray(findConfigOption(output, group, key).assets) ? findConfigOption(output, group, key).assets : [];
    const scopedAssets = scopedOptionItemsFor(output, group, key, scannedAssets);
    return slots.filter((slot) => slot.asset_key).map((slot) => {
      const assetKey = safeIdentifier(slot.asset_key, "");
      const existingAsset = objectOf(existing.find((asset) => asset.asset_key === assetKey));
      const scannedAsset = objectOf(scopedAssets.find((asset) => safeIdentifier(asset.asset_key || asset.key || asset.name, "") === assetKey));
      return {
        asset_key: assetKey,
        slot: slot.key,
        supported_values: supportedValuesFor(existingAsset, scannedAsset),
        component_key: "",
        scope: "local"
      };
    }).filter((asset) => asset.asset_key && asset.slot);
  }

  function optionFontDependencies(output, group, key, slots, defaults) {
    const existing = findConfigOption(output, group, key);
    const optionKey = safeOptionKey(key, group);
    return unique([
      ...(Array.isArray(defaults) ? defaults : []),
      ...(Array.isArray(existing.font_dependencies) ? existing.font_dependencies : []),
      ...slots.flatMap((slot) => Array.isArray(slot.font_dependencies) ? slot.font_dependencies : [])
    ].map(cleanText)).filter((font) => !isFontOptionSelfDependency(group, optionKey, font));
  }

  function isFontOptionSelfDependency(group, optionKey, value) {
    return group === "font"
      && /^F[1-9]\d*$/i.test(String(optionKey || ""))
      && safeOptionKey(value, "font") === optionKey;
  }

  function supportedValuesFor(existing, scanned) {
    const values = existing.supported_values || scanned.supported_values || scanned.values || scanned.characters || scanned.range || [];
    if (Array.isArray(values)) return values.map(cleanText).filter(Boolean);
    if (typeof values === "string") return values.split(/[,\s]+/).map(cleanText).filter(Boolean);
    return [];
  }

  function dimensionRuleFromValues(width, height, mode) {
    const normalized = {};
    const widthNumber = Number(width);
    const heightNumber = Number(height);
    if (Number.isFinite(widthNumber) && widthNumber > 0) normalized.width_mm = widthNumber;
    if (Number.isFinite(heightNumber) && heightNumber > 0) normalized.height_mm = heightNumber;
    if (normalized.width_mm || normalized.height_mm) {
      normalized.mode = mode || "fixed";
      normalized.tolerance_mm = DIMENSION_TOLERANCE_MM;
    }
    return normalized;
  }

  function normalizedDimensionRule(value, mode) {
    const dimensions = objectOf(value);
    return dimensionRuleFromValues(dimensions.width_mm, dimensions.height_mm, dimensions.mode || mode);
  }






  Object.assign(globalThis, {
    buildControlledConfig,
    collectRenderMode,
    syncRenderModeControls,
    storedRenderMode,
    collectOutputRows,
    withControlledGroups,
    collectFieldBindings,
    fieldBindingAllowed,
    collectOptionMappingRows,
    hasScanBackedGroupForOutput,
    effectiveOptionMappings,
    scanBackedOptionMappings,
    collectChecks,
    manualCheckReasonForConfig,
    collectControlledColors,
    collectOutputPolicy,
    syncOutputPolicyControls,
    nextAudit,
    styleOptionsFor,
    designOptionsFor,
    fontOptionsFor,
    optionKeysFor,
    scopedScanItemsFor,
    collectStyleDimensionConfigs,
    dimensionRuleFromValues,
    normalizedDimensionRule
  });
})();
