(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, OPTION_PRESETS, PRESETS } = ctx;

  function renderContentOptionRows() {
    const target = $("contentOptionRows");
    if (!target) return;
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const mappings = configOptionMappings().length ? configOptionMappings() : inferredMappings();
    target.replaceChildren();
    outputs.forEach((output, index) => {
      const fallback = index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main";
      const outputKey = safeOutputKey(output.key || output.name, fallback, index);
      appendContentGroups(target, outputKey, "design", optionKeysFor(outputKey, "design", mappings, model.designs), model);
      appendContentGroups(target, outputKey, "font", optionKeysFor(outputKey, "font", mappings, model.fonts), model);
    });
    if (!target.children.length) target.appendChild(emptyNode("等待 Design 或 F 选项。"));
  }

  function appendContentGroups(target, output, group, optionKeys, model) {
    optionKeys.forEach((optionKey) => {
      const safeKey = safeOptionKey(optionKey, group);
      if (safeKey) target.appendChild(contentOptionGroup(output, group, safeKey, model));
    });
  }

  function contentOptionGroup(output, group, optionKey, model) {
    const existing = findConfigOption(output, group, optionKey);
    const section = document.createElement("section");
    section.className = "content-option-group";
    section.dataset.output = output;
    section.dataset.group = group;
    section.dataset.option = optionKey;

    const header = document.createElement("div");
    header.className = "content-option-header";
    header.appendChild(lineNode(`${output} · ${groupLabel(group)} ${optionKey}`, group === "design" ? "具体 Design 独立配置" : "具体 F 独立配置"));
    header.appendChild(selectCell("option-content-preset", presetOptions(OPTION_PRESETS), safeOptionPreset(existing.content_preset, recommendedOptionPreset(output, group, optionKey, model))));
    section.appendChild(header);

    const rows = document.createElement("div");
    rows.className = "content-slot-table";
    rows.appendChild(contentSlotHeader());
    contentSlotsFor(output, group, optionKey, model, existing).forEach((slot) => rows.appendChild(contentSlotRow(output, group, optionKey, slot)));
    section.appendChild(rows);
    return section;
  }

  function contentSlotHeader() {
    const row = tableRow("content-slot-head");
    row.append(
      metaCell("slot"),
      metaCell("内容来源"),
      metaCell("业务渲染类型"),
      metaCell("状态"),
      metaCell("素材键"),
      metaCell("X 宽"),
      metaCell("Y 高"),
      metaCell("首尾巴"),
      metaCell("末尾巴"),
      metaCell("字体依赖"),
      metaCell("颜色绑定")
    );
    return row;
  }

  function contentSlotRow(output, group, optionKey, slot) {
    const row = tableRow("content-slot-row");
    row.dataset.output = output;
    row.dataset.group = group;
    row.dataset.option = optionKey;
    row.dataset.slotKey = slot.key;
    row.dataset.anchor = slot.anchor || "";
    const dimensions = objectOf(slot.dimension_rule);
    row.append(
      metaCell(slot.key),
      inputCell("slot-source-field", slot.source_field || ""),
      selectCell("slot-preset", presetOptions(PRESETS), safePreset(slot.preset, "direct_text")),
      selectCell("slot-required", [["required", "必填"], ["optional", "可选"]], slot.required === false ? "optional" : "required"),
      inputCell("slot-asset-key", slot.asset_key || ""),
      inputCell("slot-width-mm", dimensions.width_mm || ""),
      inputCell("slot-height-mm", dimensions.height_mm || ""),
      inputCell("slot-tail-first", tailSample(slot.tails, "first")),
      inputCell("slot-tail-last", tailSample(slot.tails, "last")),
      inputCell("slot-font-dependencies", stringListValue(slot.font_dependencies)),
      inputCell("slot-color-binding", slot.color_binding || "")
    );
    return row;
  }

  function collectContentOptionConfigs() {
    const result = {};
    Array.from(document.querySelectorAll("#contentOptionRows .content-option-group")).forEach((groupRow) => {
      const group = contentGroupName(groupRow.dataset.group);
      const output = safeOutputKey(groupRow.dataset.output, "Output_main", 0);
      const option = safeOptionKey(groupRow.dataset.option, group);
      if (!group || !output || !option) return;
      result[contentOptionMapKey(output, group, option)] = {
        content_preset: safeOptionPreset(rowValue(groupRow, "option-content-preset"), "direct_text"),
        slots: []
      };
    });
    Array.from(document.querySelectorAll("#contentOptionRows .content-slot-row")).forEach((slotRow) => {
      const group = contentGroupName(slotRow.dataset.group);
      const output = safeOutputKey(slotRow.dataset.output, "Output_main", 0);
      const option = safeOptionKey(slotRow.dataset.option, group);
      const key = contentOptionMapKey(output, group, option);
      if (result[key]) result[key].slots.push(slotConfigFromRow(slotRow));
    });
    return result;
  }

  function slotConfigFromRow(row) {
    const key = slotKeyFor(row.dataset.slotKey || rowValue(row, "slot-key") || "slot_name");
    const fallbackField = safeField(key.replace(/^slot_/, "")) || "name";
    return {
      key,
      source_field: safeField(rowValue(row, "slot-source-field")) || fallbackField,
      required: rowValue(row, "slot-required") !== "optional",
      preset: safePreset(rowValue(row, "slot-preset"), "direct_text"),
      anchor: cleanText(row.dataset.anchor || ""),
      tails: tailConfigsFromRow(row, key),
      asset_key: safeIdentifier(rowValue(row, "slot-asset-key"), ""),
      dimension_rule: dimensionRuleFromValues(rowValue(row, "slot-width-mm"), rowValue(row, "slot-height-mm"), "slot"),
      font_dependencies: splitStringList(rowValue(row, "slot-font-dependencies")),
      color_binding: safeIdentifier(rowValue(row, "slot-color-binding"), "")
    };
  }

  function controlledSlots(slots) {
    const source = slots.length ? slots : [{ name: "name" }];
    return source.slice(0, 12).map((item) => {
      const raw = cleanText(item.key || item.name || item.label || "name");
      const key = slotKeyFor(raw);
      const suffix = key.replace(/^slot_/, "");
      const field = safeField(item.source_field || item.field || suffix) || "name";
      return {
        key,
        source_field: field,
        required: item.required === false ? false : true,
        preset: safePreset(item.preset, "direct_text"),
        anchor: cleanText(item.anchor || ""),
        tails: Array.isArray(item.tails) ? item.tails : [],
        asset_key: safeIdentifier(item.asset_key || inferredAssetKey(key, item), ""),
        dimension_rule: objectOf(item.dimension_rule),
        font_dependencies: Array.isArray(item.font_dependencies) ? item.font_dependencies.map(cleanText).filter(Boolean) : [],
        color_binding: safeIdentifier(item.color_binding || "", "")
      };
    });
  }

  function contentOptionPreset(content, output, group, option) {
    const existing = content[contentOptionMapKey(output, group, option)];
    return existing ? existing.content_preset : existingOptionPreset(output, group, option);
  }

  function contentOptionSlots(content, output, group, option, fallbackSlots) {
    const existing = content[contentOptionMapKey(output, group, option)];
    return existing && existing.slots.length ? existing.slots : controlledSlots(existingOptionSlots(output, group, option, fallbackSlots));
  }

  function existingOptionPreset(output, group, option) {
    const found = findConfigOption(output, group, option);
    return safeOptionPreset(found.content_preset, "direct_text");
  }

  function existingOptionSlots(output, group, option, fallbackSlots) {
    const found = findConfigOption(output, group, option);
    return Array.isArray(found.slots) && found.slots.length ? found.slots : scopedScanItemsFor(output, fallbackSlots);
  }

  function findConfigOption(output, group, option) {
    const outputConfig = configOutputs().find((item) => safeOutputKey(item.key, "Output_main", 0) === output);
    const section = objectOf(outputConfig && outputConfig[group]);
    const options = Array.isArray(section.options) ? section.options : [];
    return objectOf(options.find((item) => safeOptionKey(item.key || item.name || item.label, group) === safeOptionKey(option, group)));
  }

  function contentSlotsFor(output, group, optionKey, model, existing) {
    if (Array.isArray(existing.slots) && existing.slots.length) return controlledSlots(existing.slots);
    const scanned = scannedOptionSlots(output, group === "design" ? model.designs : model.fonts, group, optionKey);
    const fallbackSlots = scopedScanItemsFor(output, model.slots);
    return controlledSlots(scanned.length ? scanned : fallbackSlots);
  }

  function scannedOptionSlots(output, items, group, optionKey) {
    const option = objectOf(scopedScanItemsFor(output, items).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    return Array.isArray(option.slots) ? option.slots : [];
  }

  function recommendedOptionPreset(output, group, optionKey, model) {
    const source = group === "design" ? model.designs : model.fonts;
    const option = objectOf(scopedScanItemsFor(output, source).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    return safeOptionPreset(option.content_preset || option.recommended_preset || option.preset, "direct_text");
  }

  function safePreset(value, fallback) {
    return PRESETS.includes(value) ? value : (fallback || "direct_text");
  }

  function safeOptionPreset(value, fallback) {
    return OPTION_PRESETS.includes(value) ? value : (fallback || "direct_text");
  }

  function presetOptions(values) {
    const labels = ctx.PRESET_LABELS || {};
    return values.map((value) => [value, labels[value] || value]);
  }

  function slotKeyFor(value) {
    const raw = cleanText(value || "name").replace(/^slot_/, "");
    return `slot_${safeIdentifier(raw, "name").toLowerCase()}`;
  }

  function contentOptionMapKey(output, group, option) {
    return `${output}::${group}::${option}`;
  }

  function contentGroupName(value) {
    return ["design", "font"].includes(value) ? value : "";
  }

  function groupLabel(group) {
    return group === "font" ? "F" : "Design";
  }

  function tailSample(tails, position) {
    const found = Array.isArray(tails) ? tails.find((tail) => objectOf(tail).position === position) : null;
    return cleanText(objectOf(found).sample || "");
  }

  function tailConfigsFromRow(row, slotKey) {
    return [
      tailConfig(slotKey, "first", rowValue(row, "slot-tail-first")),
      tailConfig(slotKey, "last", rowValue(row, "slot-tail-last"))
    ].filter(Boolean);
  }

  function tailConfig(slotKey, position, sample) {
    const value = cleanText(sample);
    if (!value) return null;
    const suffix = slotKey.replace(/^slot_/, "");
    const sampleKey = safeIdentifier(value.toLowerCase(), position);
    return { key: `tail_${suffix}_${position}_${sampleKey}`, position, sample: value };
  }

  function stringListValue(value) {
    return Array.isArray(value) ? value.map(cleanText).filter(Boolean).join(", ") : "";
  }

  function splitStringList(value) {
    return cleanText(value).split(/[,\n;]+/).map(cleanText).filter(Boolean);
  }

  function inferredAssetKey(slotKey, item) {
    if (item.preset === "asset_replace") return slotKey.replace(/^slot_/, "");
    return "";
  }

  function metaCell(text) {
    const cell = document.createElement("div");
    cell.className = "content-meta-cell";
    cell.textContent = text || "";
    return cell;
  }

  Object.assign(globalThis, {
    renderContentOptionRows,
    contentOptionGroup,
    contentSlotRow,
    collectContentOptionConfigs,
    slotConfigFromRow,
    controlledSlots,
    contentOptionPreset,
    contentOptionSlots,
    existingOptionPreset,
    existingOptionSlots,
    findConfigOption,
    safePreset,
    safeOptionPreset,
    presetOptions,
    slotKeyFor,
    contentOptionMapKey,
    contentGroupName
  });
})();
