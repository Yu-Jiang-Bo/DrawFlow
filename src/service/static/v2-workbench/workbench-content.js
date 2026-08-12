(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, OPTION_PRESETS, PRESETS } = ctx;

  function renderContentOptionRows(selected) {
    const target = $("contentOptionRows");
    if (!target) return;
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const mappings = effectiveOptionMappings();
    target.replaceChildren();
    if (selected) {
      appendSelectedContentGroup(target, selected, model);
    } else {
      outputs.forEach((output, index) => {
        const fallback = index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main";
        const outputKey = safeOutputKey(output.key || output.name, fallback, index);
        appendContentGroups(target, outputKey, "design", optionKeysFor(outputKey, "design", mappings, model.designs), model);
        appendContentGroups(target, outputKey, "font", optionKeysFor(outputKey, "font", mappings, model.fonts), model);
      });
    }
    if (!target.children.length) target.appendChild(emptyNode("等待 Design 或 F 选项。"));
  }

  function appendSelectedContentGroup(target, selected, model) {
    const group = contentGroupName(selected.group);
    const output = safeOutputKey(selected.output, "Output_main", 0);
    const option = safeOptionKey(selected.key, group);
    if (group && output && option) target.appendChild(contentOptionGroup(output, group, option, model));
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

    const requestedOptionPreset = safeOptionPreset(existing.content_preset, recommendedOptionPreset(output, group, optionKey, model));
    let slots = contentSlotsFor(output, group, optionKey, model, existing, requestedOptionPreset);
    const tailPresentation = tailPresentationForSlots(slots);
    const optionPreset = safeTailPreset(requestedOptionPreset, tailPresentation);
    if (optionPreset !== requestedOptionPreset) slots = contentSlotsFor(output, group, optionKey, model, existing, optionPreset);
    const layout = contentSlotLayout(slots, model);

    const header = document.createElement("div");
    header.className = "content-option-header";
    header.appendChild(lineNode(
      `${output} · ${groupLabel(group)} ${optionKey}`,
      tailPresentation.detected ? tailTreatmentDescription(tailPresentation) : (group === "design" ? "具体 Design 独立配置" : "具体 F 独立配置")
    ));
    section.dataset.contentPreset = optionPreset;
    section.dataset.tailPresentation = tailPresentation.detected ? (tailPresentation.verified ? "verified" : "detected") : "none";
    section.appendChild(header);

    const rows = document.createElement("div");
    rows.className = "content-slot-table";
    rows.appendChild(contentSlotHeader(layout));
    slots.forEach((slot) => rows.appendChild(contentSlotRow(output, group, optionKey, slot, layout)));
    section.appendChild(rows);
    return section;
  }

  function contentSlotHeader(layout) {
    const row = tableRow("content-slot-head");
    applyContentSlotLayout(row, layout);
    row.append(
      metaCell("slot"),
      metaCell("内容来源"),
      metaCell("槽位处理（按需覆盖）"),
      metaCell("状态"),
      metaCell("素材键（仅素材）"),
      metaCell("适配宽"),
      metaCell("适配高"),
      metaCell("字体依赖")
    );
    if (layout && layout.showTailSamples) row.appendChild(metaCell("尾巴样本"));
    if (layout && layout.showColorBinding) row.appendChild(metaCell("颜色绑定"));
    return row;
  }

  function contentSlotRow(output, group, optionKey, slot, layout) {
    const row = tableRow("content-slot-row");
    row.dataset.output = output;
    row.dataset.group = group;
    row.dataset.option = optionKey;
    row.dataset.slotKey = slot.key;
    row.dataset.anchor = slot.anchor || "";
    row.__tailConfigs = normalizedTailConfigs(slot.tails);
    row.__colorBinding = safeIdentifier(slot.color_binding || "", "");
    const dimensions = objectOf(slot.dimension_rule);
    row.dataset.dimensionMode = cleanText(dimensions.mode || "") || (slot.anchor ? "anchor" : "slot");
    applyContentSlotLayout(row, layout);
    const tailPresentation = tailPresentationForSlots([slot]);
    const slotPreset = safeTailPreset(safePreset(slot.preset, "direct_text"), tailPresentation);
    row.append(
      metaCell(slot.key),
      inputCell("slot-source-field", slot.source_field || ""),
      selectCell("slot-preset", presetOptions(PRESETS, tailPresentation), slotPreset),
      selectCell("slot-required", [["required", "必填"], ["optional", "可选"]], slot.required === false ? "optional" : "required"),
      readonlyInputCell("slot-asset-key", slot.asset_key || "", "素材替换槽位才会有素材键；普通文字槽位留空。"),
      readonlyInputCell("slot-width-mm", displayDimension(dimensions.width_mm), "按模板定位框取整显示；实际适配仍按模板的精确边界执行。", dimensions.width_mm),
      readonlyInputCell("slot-height-mm", displayDimension(dimensions.height_mm), "按模板定位框取整显示；实际适配仍按模板的精确边界执行。", dimensions.height_mm),
      inputCell("slot-font-dependencies", stringListValue(slot.font_dependencies))
    );
    if (layout && layout.showTailSamples) row.appendChild(tailEvidenceCell(row.__tailConfigs));
    if (layout && layout.showColorBinding) row.appendChild(inputCell("slot-color-binding", slot.color_binding || ""));
    return row;
  }

  function collectContentOptionConfigs() {
    const result = existingContentOptionConfigs();
    Array.from(document.querySelectorAll("#contentOptionRows .content-option-group")).forEach((groupRow) => {
      const group = contentGroupName(groupRow.dataset.group);
      const output = safeOutputKey(groupRow.dataset.output, "Output_main", 0);
      const option = safeOptionKey(groupRow.dataset.option, group);
      if (!group || !output || !option) return;
      result[contentOptionMapKey(output, group, option)] = {
        content_preset: safeOptionPreset(groupRow.dataset.contentPreset, "direct_text"),
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

  function existingContentOptionConfigs() {
    const result = {};
    const model = scanModel(state.scan, state.draft && state.draft.config);
    configOutputs().forEach((output, outputIndex) => {
      const fallback = outputIndex ? `Output_Side${String.fromCharCode(65 + outputIndex)}` : "Output_main";
      const outputKey = safeOutputKey(output.key || output.name, fallback, outputIndex);
      ["design", "font"].forEach((group) => {
        const groupConfig = objectOf(output[group]);
        const options = Array.isArray(groupConfig.options) ? groupConfig.options : [];
        options.forEach((option) => {
          const key = safeOptionKey(option.key || option.name || option.label, group);
          if (!outputKey || !key) return;
          const requestedPreset = safeOptionPreset(option.content_preset, "direct_text");
          const optionContext = scannedOptionForContent(outputKey, group, key, model);
          let slots = Array.isArray(option.slots) ? controlledSlots(option.slots, optionContext, requestedPreset) : [];
          const preset = safeTailPreset(requestedPreset, tailPresentationForSlots(slots));
          if (preset !== requestedPreset && Array.isArray(option.slots)) {
            slots = controlledSlots(option.slots, optionContext, preset);
          }
          result[contentOptionMapKey(outputKey, group, key)] = {
            content_preset: preset,
            slots
          };
        });
      });
    });
    return result;
  }

  function slotConfigFromRow(row) {
    const key = slotKeyFor(row.dataset.slotKey || rowValue(row, "slot-key") || "slot_name");
    const fallbackField = safeField(key.replace(/^slot_/, "")) || "name";
    const anchor = cleanText(row.dataset.anchor || "");
    const dimensionMode = cleanText(row.dataset.dimensionMode || "") || (anchor ? "anchor" : "slot");
    return {
      key,
      source_field: safeField(rowValue(row, "slot-source-field")) || fallbackField,
      required: rowValue(row, "slot-required") !== "optional",
      preset: safePreset(rowValue(row, "slot-preset"), "direct_text"),
      anchor,
      tails: tailConfigsFromRow(row, key),
      asset_key: safeIdentifier(rowValue(row, "slot-asset-key"), ""),
      dimension_rule: dimensionRuleFromValues(readonlyRawValue(row, "slot-width-mm"), readonlyRawValue(row, "slot-height-mm"), dimensionMode),
      font_dependencies: splitStringList(rowValue(row, "slot-font-dependencies")),
      color_binding: colorBindingFromRow(row)
    };
  }

  function controlledSlots(slots, optionContext, optionPreset) {
    const source = slots.length ? slots : [{ name: "name" }];
    return source.slice(0, 12).map((item) => {
      const raw = cleanText(item.key || item.name || item.label || "name");
      const key = slotKeyFor(raw);
      const suffix = key.replace(/^slot_/, "");
      const field = safeField(item.source_field || item.field || suffix) || "name";
      const scannedSlot = scannedSlotForKey(optionContext, key);
      const tails = mergedTailConfigs(item.tails, scannedSlot.tails);
      const slotForPreset = { ...objectOf(item), tails };
      const anchor = inferredAnchorForSlot(item, key, optionContext);
      return {
        key,
        source_field: field,
        required: item.required === false ? false : true,
        preset: slotPresetForOption(slotForPreset, optionPreset),
        anchor,
        tails,
        asset_key: safeIdentifier(item.asset_key || inferredAssetKey(key, item), ""),
        dimension_rule: slotDimensionRule(item, optionContext, key),
        font_dependencies: Array.isArray(item.font_dependencies) ? item.font_dependencies.map(cleanText).filter(Boolean) : [],
        color_binding: safeIdentifier(item.color_binding || "", "")
      };
    });
  }

  function contentOptionPreset(content, output, group, option, model) {
    const existing = content[contentOptionMapKey(output, group, option)];
    if (existing) return existing.content_preset;
    const found = findConfigOption(output, group, option);
    if (OPTION_PRESETS.includes(found.content_preset)) return found.content_preset;
    return recommendedOptionPreset(output, group, option, model || scanModel(state.scan, state.draft && state.draft.config));
  }

  function contentOptionSlots(content, output, group, option, fallbackSlots, model) {
    const existing = content[contentOptionMapKey(output, group, option)];
    if (existing && existing.slots.length) return existing.slots;
    const optionContext = scannedOptionForContent(output, group, option, model);
    return controlledSlots(existingOptionSlots(output, group, option, fallbackSlots, model), optionContext, contentOptionPreset(content, output, group, option, model));
  }

  function existingOptionPreset(output, group, option) {
    const found = findConfigOption(output, group, option);
    return safeOptionPreset(found.content_preset, "direct_text");
  }

  function existingOptionSlots(output, group, option, fallbackSlots, model) {
    const found = findConfigOption(output, group, option);
    if (Array.isArray(found.slots) && found.slots.length) return found.slots;
    if (model) {
      const scanned = scannedOptionSlots(output, group === "design" ? model.designs : model.fonts, group, option);
      if (scanned.length) return scanned;
    }
    return scopedOptionItemsFor(output, group, option, fallbackSlots);
  }

  function findConfigOption(output, group, option) {
    const outputConfig = configOutputs().find((item) => safeOutputKey(item.key, "Output_main", 0) === output);
    const section = objectOf(outputConfig && outputConfig[group]);
    const options = Array.isArray(section.options) ? section.options : [];
    return objectOf(options.find((item) => safeOptionKey(item.key || item.name || item.label, group) === safeOptionKey(option, group)));
  }

  function contentSlotsFor(output, group, optionKey, model, existing, optionPreset) {
    const optionContext = scannedOptionForContent(output, group, optionKey, model);
    if (Array.isArray(existing.slots) && existing.slots.length) return controlledSlots(existing.slots, optionContext, optionPreset || existing.content_preset);
    const scanned = scannedOptionSlotsFromOption(optionContext);
    const fallbackSlots = scopedOptionItemsFor(output, group, optionKey, model.slots);
    return controlledSlots(scanned.length ? scanned : fallbackSlots, optionContext, optionPreset);
  }

  function scannedOptionSlots(output, items, group, optionKey) {
    const option = objectOf(scopedScanItemsFor(output, items).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    return scannedOptionSlotsFromOption(option);
  }

  function scannedOptionForContent(output, group, optionKey, model) {
    const source = group === "design" ? model.designs : model.fonts;
    return objectOf(scopedScanItemsFor(output, source).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
  }

  function scannedOptionSlotsFromOption(option) {
    return Array.isArray(objectOf(option).slots) ? objectOf(option).slots : [];
  }

  function scannedSlotForKey(optionContext, slotKey) {
    return objectOf(scannedOptionSlotsFromOption(optionContext).find((slot) => (
      slotKeyFor(objectOf(slot).key || objectOf(slot).name || objectOf(slot).label || "") === slotKey
    )));
  }

  function recommendedOptionPreset(output, group, optionKey, model) {
    const source = group === "design" ? model.designs : model.fonts;
    const option = objectOf(scopedScanItemsFor(output, source).find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    return recommendedPresetForOption(option);
  }

  function safePreset(value, fallback) {
    return PRESETS.includes(value) ? value : (fallback || "direct_text");
  }

  function safeOptionPreset(value, fallback) {
    return OPTION_PRESETS.includes(value) ? value : (fallback || "direct_text");
  }

  function slotPresetForOption(item, optionPreset) {
    const data = objectOf(item);
    const preset = safeOptionPreset(optionPreset, "");
    const hasAsset = Boolean(safeIdentifier(data.asset_key || inferredAssetKey(slotKeyFor(data.key || data.name || data.label || ""), data), ""));
    const hasTail = normalizedTailConfigs(data.tails).length > 0;
    if (preset === "split_by_pipe") return "split_by_pipe";
    if (preset === "path_text") return "path_text";
    if (preset === "tail_text" && hasTail) return "tail_text";
    if (hasAsset) return safePreset(data.preset, "asset_replace");
    return safePreset(data.preset, "direct_text");
  }

  function presetOptions(values, tailPresentation) {
    const labels = ctx.PRESET_LABELS || {};
    const presentation = objectOf(tailPresentation);
    return values.filter((value) => !(value === "tail_text" && presentation.detected && !presentation.verified)).map((value) => {
      if (value === "direct_text" && presentation.detected && !presentation.verified) {
        return [value, "尾巴文字（已识别）"];
      }
      return [value, labels[value] || value];
    });
  }

  function safeTailPreset(value, tailPresentation) {
    const preset = safePreset(value, "direct_text");
    const presentation = objectOf(tailPresentation);
    return preset === "tail_text" && presentation.detected && !presentation.verified ? "direct_text" : preset;
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

  function scopedOptionItemsFor(output, group, option, scanItems) {
    const scoped = scopedScanItemsFor(output, Array.isArray(scanItems) ? scanItems : []);
    const safeGroup = contentGroupName(group);
    const safeOption = safeOptionKey(option, safeGroup);
    const tagged = scoped.filter((item) => optionScopeValue(item));
    if (!tagged.length) return scoped;
    return tagged.filter((item) => {
      const itemGroup = cleanText(item.group || item.option_group || item.parent_group || item.parentGroup);
      const groupMatches = !itemGroup || itemGroup === safeGroup;
      return groupMatches && safeOptionKey(optionScopeValue(item), safeGroup) === safeOption;
    });
  }

  function optionScopeValue(item) {
    const data = objectOf(item);
    return cleanText(data.option || data.option_key || data.optionKey || data.parent_option || data.parentOption);
  }

  function groupLabel(group) {
    return group === "font" ? "F" : "Design";
  }

  function tailConfigsFromRow(row, slotKey) {
    if (Array.isArray(row.__tailConfigs) && row.__tailConfigs.length) {
      return normalizedTailConfigs(row.__tailConfigs);
    }
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

  function normalizedTailConfigs(tails) {
    return (Array.isArray(tails) ? tails : []).map((tail) => {
      const data = objectOf(tail);
      const key = cleanText(data.key || data.name || "");
      const parsed = parseTailKey(key);
      const position = cleanText(data.position || parsed.position || "").toLowerCase();
      const sample = cleanText(data.sample || data.text || parsed.sample || "");
      if (!key || !["first", "last"].includes(position)) return null;
      const result = { key, position, sample };
      if (data.pua_base !== undefined && data.pua_base !== null && cleanText(data.pua_base) !== "") result.pua_base = data.pua_base;
      if (data.glyph_map && typeof data.glyph_map === "object") result.glyph_map = data.glyph_map;
      return result;
    }).filter(Boolean);
  }

  function mergedTailConfigs(configuredTails, scannedTails) {
    const merged = new Map();
    normalizedTailConfigs(scannedTails).forEach((tail) => merged.set(tail.key, tail));
    normalizedTailConfigs(configuredTails).forEach((tail) => {
      const scanned = merged.get(tail.key) || {};
      merged.set(tail.key, { ...scanned, ...tail });
    });
    return Array.from(merged.values());
  }

  function parseTailKey(key) {
    const match = cleanText(key).match(/^tail_(.+)_(first|last)_([A-Za-z])$/i);
    return match ? { field: match[1], position: match[2].toLowerCase(), sample: match[3] } : {};
  }

  function tailPresentationForSlots(slots) {
    const tails = (Array.isArray(slots) ? slots : [])
      .flatMap((slot) => normalizedTailConfigs(objectOf(slot).tails));
    const positions = unique(tails.map((tail) => tail.position));
    return {
      detected: tails.length > 0,
      verified: tails.length > 0 && tails.every(tailHasGlyphProof),
      positions
    };
  }

  function tailHasGlyphProof(tail) {
    const data = objectOf(tail);
    if (data.pua_base !== undefined && data.pua_base !== null && cleanText(data.pua_base) !== "") {
      return validTailPuaBase(data.pua_base);
    }
    return validTailGlyphMap(data.glyph_map);
  }

  function validTailPuaBase(value) {
    const codepoint = tailCodepoint(value);
    return codepoint !== null && codepoint >= 0xE000 && codepoint + 25 <= 0xF8FF;
  }

  function validTailGlyphMap(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    return "abcdefghijklmnopqrstuvwxyz".split("").every((letter) => {
      const valueForLetter = Object.prototype.hasOwnProperty.call(value, letter) ? value[letter] : value[letter.toUpperCase()];
      const codepoint = tailCodepoint(valueForLetter);
      return codepoint !== null && codepoint >= 0xE000 && codepoint <= 0xF8FF;
    });
  }

  function tailCodepoint(value) {
    if (typeof value === "number") return Number.isInteger(value) ? value : null;
    if (typeof value !== "string") return null;
    const text = value.trim().toLowerCase();
    if (!/^(?:[+-]?\d+|0x[0-9a-f]+)$/.test(text)) return null;
    const codepoint = Number(text);
    return Number.isInteger(codepoint) ? codepoint : null;
  }

  function tailTreatmentDescription(presentation) {
    const positions = Array.isArray(objectOf(presentation).positions) ? presentation.positions : [];
    const endpoint = positions.includes("first") && positions.includes("last") ? "首字和尾字" : (positions.includes("first") ? "首字" : "尾字");
    return `已识别尾巴样式，订单文字的${endpoint}会自动放入尾巴位置，无需手动填写样本。`;
  }

  function tailEvidenceCell(tails) {
    const cell = metaCell(tailSampleSummary(tails));
    cell.classList.add("tail-sample-cell");
    cell.setAttribute("aria-readonly", "true");
    cell.title = "模板尾巴样本仅用于识别；订单文字会自动取对应的首字或尾字。";
    return cell;
  }

  function tailSampleSummary(tails) {
    const labels = { first: "首字", last: "尾字" };
    return normalizedTailConfigs(tails)
      .map((tail) => `${labels[tail.position] || "尾巴"} ${tail.sample}`)
      .join(" · ");
  }

  function contentSlotLayout(slots, model) {
    return {
      showTailSamples: (Array.isArray(slots) ? slots : []).some((slot) => normalizedTailConfigs(objectOf(slot).tails).length),
      showColorBinding: hasActiveColorRules(slots, model)
    };
  }

  function applyContentSlotLayout(row, layout) {
    const current = objectOf(layout);
    if (current.showTailSamples) row.classList.add("has-tail-samples");
    if (current.showColorBinding) row.classList.add("has-color-binding");
  }

  function hasActiveColorRules(slots, model) {
    const currentModel = model || scanModel(state.scan, state.draft && state.draft.config);
    if (Array.isArray(currentModel.colors) && currentModel.colors.length) return true;
    if (colorFieldIsBound()) return true;
    if (configuredColorBindingsExist()) return true;
    return (Array.isArray(slots) ? slots : []).some((slot) => Boolean(safeIdentifier(objectOf(slot).color_binding || "", "")));
  }

  function colorFieldIsBound() {
    const bindings = objectOf(state.draft && state.draft.config && state.draft.config.field_bindings);
    return Boolean(cleanText(bindings.color));
  }

  function configuredColorBindingsExist() {
    return configOutputs().some((output) => ["design", "font"].some((group) => {
      const options = Array.isArray(objectOf(output[group]).options) ? objectOf(output[group]).options : [];
      return options.some((option) => Array.isArray(objectOf(option).slots) && objectOf(option).slots.some((slot) => Boolean(cleanText(objectOf(slot).color_binding))));
    }));
  }

  function contentOptionPresetOptions(output, group, optionKey, model) {
    const currentModel = model || scanModel(state.scan, state.draft && state.draft.config);
    const existing = findConfigOption(output, group, optionKey);
    const optionPreset = safeOptionPreset(existing.content_preset, recommendedOptionPreset(output, group, optionKey, currentModel));
    const slots = contentSlotsFor(output, group, optionKey, currentModel, existing, optionPreset);
    return presetOptions(OPTION_PRESETS, tailPresentationForSlots(slots));
  }

  function recommendedPresetForOption(option) {
    const data = objectOf(option);
    const recommended = safeOptionPreset(data.content_preset || data.recommended_preset || data.preset, "direct_text");
    const tails = tailPresentationForSlots(scannedOptionSlotsFromOption(data));
    if (recommended === "tail_text" && !tails.verified) return "direct_text";
    if (recommended !== "direct_text") return recommended;
    return tails.verified ? "tail_text" : "direct_text";
  }

  function slotDimensionRule(item, optionContext, slotKey) {
    const anchorRule = anchorDimensionRule(item, optionContext, slotKey);
    if (Object.keys(anchorRule).length) return anchorRule;
    const configured = objectOf(item.dimension_rule);
    if (Object.keys(configured).length) return configured;
    const scanned = normalizedDimensionRule(item.dimensions || item, "slot");
    if (Object.keys(scanned).length) return scanned;
    return {};
  }

  function anchorDimensionRule(item, optionContext, slotKey) {
    const anchorKey = inferredAnchorForSlot(item, slotKey, optionContext);
    if (!anchorKey) return {};
    const anchors = Array.isArray(objectOf(optionContext).anchors) ? objectOf(optionContext).anchors : [];
    const anchor = anchors.find((candidate) => cleanText(candidate.key || candidate.name || "") === anchorKey);
    return normalizedDimensionRule(objectOf(anchor).dimensions || anchor, "anchor");
  }

  function inferredAnchorForSlot(item, slotKey, optionContext) {
    const explicit = cleanText(item.anchor || item.anchor_key || item.anchorKey || "");
    if (explicit) return explicit;
    const suffix = cleanText(slotKey).replace(/^slot_/, "");
    if (!suffix) return "";
    const candidateKey = `anchor_${suffix}`;
    const anchors = Array.isArray(objectOf(optionContext).anchors) ? objectOf(optionContext).anchors : [];
    return anchors.some((anchor) => cleanText(anchor.key || anchor.name || "") === candidateKey) ? candidateKey : "";
  }

  function stringListValue(value) {
    return Array.isArray(value) ? value.map(cleanText).filter(Boolean).join(", ") : "";
  }

  function splitStringList(value) {
    return cleanText(value).split(/[,\n;]+/).map(cleanText).filter(Boolean);
  }

  function displayDimension(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? String(Math.trunc(number)) : "";
  }

  function readonlyRawValue(row, field) {
    const input = row.querySelector(`[data-field="${field}"]`);
    if (!input) return "";
    return Object.prototype.hasOwnProperty.call(input.dataset, "rawValue") ? input.dataset.rawValue : input.value;
  }

  function colorBindingFromRow(row) {
    const input = row.querySelector('[data-field="slot-color-binding"]');
    return safeIdentifier(input ? input.value : (row.__colorBinding || ""), "");
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

  function readonlyInputCell(name, value, title, rawValue) {
    const wrap = document.createElement("label");
    const input = document.createElement("input");
    input.dataset.field = name;
    input.value = value || "";
    if (rawValue !== undefined && rawValue !== null && rawValue !== "") input.dataset.rawValue = String(rawValue);
    input.readOnly = true;
    input.setAttribute("aria-readonly", "true");
    if (title) {
      wrap.title = title;
      input.title = title;
    }
    wrap.appendChild(input);
    return wrap;
  }

  Object.assign(globalThis, {
    renderContentOptionRows,
    appendSelectedContentGroup,
    contentOptionGroup,
    contentSlotRow,
    collectContentOptionConfigs,
    existingContentOptionConfigs,
    slotConfigFromRow,
    controlledSlots,
    contentOptionPreset,
    contentOptionSlots,
    contentOptionPresetOptions,
    existingOptionPreset,
    existingOptionSlots,
    findConfigOption,
    scannedOptionForContent,
    safePreset,
    safeOptionPreset,
    slotPresetForOption,
    presetOptions,
    recommendedPresetForOption,
    tailPresentationForSlots,
    tailTreatmentDescription,
    hasActiveColorRules,
    displayDimension,
    slotKeyFor,
    contentOptionMapKey,
    contentGroupName,
    scopedOptionItemsFor,
    optionScopeValue
  });
})();
