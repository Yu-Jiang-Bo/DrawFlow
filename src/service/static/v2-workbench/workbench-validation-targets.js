(function () {
  "use strict";
  const { CHECK_KEYS } = globalThis.DrawFlowV2WorkbenchContext;

  function validationTargetForIssue(issue) {
    const path = cleanText(objectOf(issue).path);
    const code = cleanText(objectOf(issue).code);
    const checkMatch = path.match(/^\$\.checks\.([^.[\]]+)$/);
    if (checkMatch && CHECK_KEYS.includes(checkMatch[1])) {
      const checkKey = checkMatch[1];
      const stage = ["slots", "content", "dimensions", "colors"].includes(checkKey) ? "rules" : checkKey === "preview" ? "preview" : "structure";
      return { stage, kind: "check", checkKey };
    }
    const templateMatch = path.match(/^\$\.template\.(template_id|name|shop_name)$/);
    if (templateMatch) {
      const fields = {
        template_id: "templateId",
        name: "templateName",
        shop_name: "shopName"
      };
      return { stage: "upload", kind: "basic", controlId: fields[templateMatch[1]] };
    }
    const bindingMatch = path.match(/^\$\.field_bindings(?:\.([^.[\]]+))?$/);
    if (bindingMatch) return { stage: "structure", kind: "binding", fieldKey: bindingMatch[1] || "" };

    if (path === "$.option_mappings") return { stage: "structure", kind: "area", areaId: "optionMappingRows" };
    const mappingMatch = path.match(/^\$\.option_mappings\[(\d+)\](?:\.([A-Za-z_]+))?$/);
    if (mappingMatch) {
      const fields = {
        field: "mapping-field",
        source_value: "mapping-source",
        target: "mapping-target",
        output: "mapping-output",
        group: "mapping-group"
      };
      return { stage: "structure", kind: "mapping", index: Number(mappingMatch[1]), field: fields[mappingMatch[2]] || "" };
    }
    if (path.startsWith("$.colors")) {
      if (code === "color_samples_pending") return { stage: "rules", kind: "action", controlId: "confirmNoColorRulesBtn" };
      return { stage: "upload", kind: "rescan", controlId: "rescanTemplateBtn" };
    }
    if (path.startsWith("$.preview")) {
      const controlId = code === "preview_sample_pending" ? "previewSampleRows" : "rerunTrialRenderBtn";
      return { stage: "preview", kind: "action", controlId };
    }
    if (path === "$.outputs") {
      if (code === "dimension_pending") return { stage: "upload", kind: "rescan", controlId: "rescanTemplateBtn" };
      return { stage: "structure", kind: "area", areaId: "outputConfigRows" };
    }

    const outputMatch = path.match(/^\$\.outputs\[(\d+)\](.*)$/);
    if (!outputMatch) return null;
    const outputIndex = Number(outputMatch[1]);
    const suffix = outputMatch[2] || "";
    const outputFields = {
      ".key": "output-key",
      ".display_name": "output-name",
      ".component_key": "output-component"
    };
    if (Object.prototype.hasOwnProperty.call(outputFields, suffix)) {
      return { stage: "structure", kind: "output", index: outputIndex, field: outputFields[suffix] };
    }

    const groupFieldMatch = suffix.match(/^\.(style|design|font)\.field$/);
    if (groupFieldMatch && code === "field_binding_missing") {
      const fieldKey = cleanText(objectOf(validationOutputConfig(outputIndex)[groupFieldMatch[1]]).field);
      return { stage: "structure", kind: "binding", fieldKey };
    }
    const groupOptionsMatch = suffix.match(/^\.(style|design|font)\.options$/);
    if (groupOptionsMatch) {
      return rescanValidationTarget({ outputIndex, outputKey: validationOutputKey(outputIndex), group: groupOptionsMatch[1] });
    }

    const optionMatch = suffix.match(/^\.(style|design|font)\.options\[(\d+)\](.*)$/);
    if (!optionMatch) return { stage: "structure", kind: "output", index: outputIndex, field: "" };
    const group = optionMatch[1];
    const optionIndex = Number(optionMatch[2]);
    const optionSuffix = optionMatch[3] || "";
    const optionTarget = validationOptionTarget(outputIndex, group, optionIndex);

    if (code === "option_mapping_missing" && optionSuffix === ".key") {
      return { ...optionTarget, stage: "structure", kind: "mapping-option", field: "mapping-source" };
    }
    if (code === "contract_invalid" && [".key", ".font_dependencies"].some((value) => optionSuffix === value || optionSuffix.startsWith(`${value}[`))) {
      return optionRescanValidationTarget(optionTarget, optionSuffix);
    }
    const bindingSlotMatch = optionSuffix.match(/^\.slots\[(\d+)\]\.source_field$/);
    if (bindingSlotMatch && code === "field_binding_missing") {
      const option = validationOptionConfig(outputIndex, group, optionIndex);
      const slots = Array.isArray(option.slots) ? option.slots : [];
      const fieldKey = cleanText(objectOf(slots[Number(bindingSlotMatch[1])]).source_field);
      return { stage: "structure", kind: "binding", fieldKey };
    }
    if (code === "mixed_slots_requires_multiple_slots") {
      return optionRescanValidationTarget(optionTarget, optionSuffix);
    }

    const editableSlotTarget = editableOptionSlotTarget(issue, optionTarget);
    if (editableSlotTarget) return editableSlotTarget;
    if (scanOwnedOptionIssue(issue, optionSuffix)) return optionRescanValidationTarget(optionTarget, optionSuffix);

    if (group === "style") {
      const fields = {
        ".dimensions.width_mm": "style-width-mm",
        ".dimensions.height_mm": "style-height-mm"
      };
      if (code === "dimension_pending" && optionSuffix === ".dimensions") {
        const dimensions = objectOf(validationOptionConfig(outputIndex, group, optionIndex).dimensions);
        fields[optionSuffix] = Number(dimensions.width_mm) > 0 ? "style-height-mm" : "style-width-mm";
      }
      if (["dimension_tolerance_pending", "dimension_tolerance_invalid"].includes(code) && optionSuffix === ".dimensions") {
        fields[optionSuffix] = "style-width-mm";
      }
      return { ...optionTarget, stage: "structure", kind: "style", field: fields[optionSuffix] || "" };
    }

    const slotMatch = optionSuffix.match(/^\.slots\[(\d+)\](.*)$/);
    if (slotMatch) {
      const slotFields = {
        ".source_field": "slot-source-field",
        ".preset": "slot-preset",
        ".required": "slot-required",
        ".asset_key": "slot-asset-key",
        ".font_dependencies": "slot-font-dependencies",
        ".color_binding": "slot-color-binding",
        ".dimension_rule.width_mm": "slot-width-mm",
        ".dimension_rule.height_mm": "slot-height-mm"
      };
      return {
        ...optionTarget,
        stage: "rules",
        kind: "slot",
        slotIndex: Number(slotMatch[1]),
        field: slotFields[slotMatch[2]] || ""
      };
    }
    if (optionSuffix === ".content_preset") {
      const option = validationOptionConfig(outputIndex, group, optionIndex);
      if (cleanText(option.content_preset) === "mixed_slots") {
        return { ...optionTarget, stage: "rules", kind: "slot", slotIndex: 0, field: "slot-preset" };
      }
      return { ...optionTarget, stage: "rules", kind: "option-preset" };
    }
    return { ...optionTarget, stage: "rules", kind: "option" };
  }

  function rescanValidationTarget(identity) {
    return { ...objectOf(identity), stage: "upload", kind: "rescan", controlId: "rescanTemplateBtn" };
  }

  function optionRescanValidationTarget(optionTarget, suffix) {
    const slotMatch = cleanText(suffix).match(/^\.slots\[(\d+)\]/);
    const assetMatch = cleanText(suffix).match(/^\.assets\[(\d+)\]/);
    return rescanValidationTarget({
      ...objectOf(optionTarget),
      scanItemKind: slotMatch ? "slot" : assetMatch ? "asset" : "option",
      scanItemIndex: slotMatch ? Number(slotMatch[1]) : assetMatch ? Number(assetMatch[1]) : -1
    });
  }

  function editableOptionSlotTarget(issue, optionTarget) {
    const code = cleanText(objectOf(issue).code);
    const option = validationOptionConfig(optionTarget.outputIndex, optionTarget.group, optionTarget.optionIndex);
    const slots = Array.isArray(option.slots) ? option.slots.map(objectOf) : [];
    const sourcePredicates = {
      initial_asset_source_missing: (slot) => cleanText(slot.preset) === "asset_replace" && !cleanText(slot.source_field),
      initial_text_source_missing: (slot) => cleanText(slot.preset) !== "asset_replace" && !cleanText(slot.source_field),
      multi_initials_source_missing: (slot) => cleanText(slot.asset_key) && !cleanText(slot.source_field),
      tail_text_source_missing: (slot) => Array.isArray(slot.tails) && slot.tails.length > 0 && !cleanText(slot.source_field),
      mixed_slots_source_missing: (slot) => !cleanText(slot.source_field),
      direct_text_slot_invalid: (slot) => !cleanText(slot.source_field)
    };
    const presetPredicates = {
      multi_initials_asset_preset_missing: (slot) => cleanText(slot.asset_key) && cleanText(slot.preset) !== "asset_replace",
      mixed_slots_preset_invalid: (slot) => !["direct_text", "tail_text", "path_text"].includes(cleanText(slot.preset)),
      split_by_pipe_slot_preset_invalid: (slot) => cleanText(slot.preset) !== "split_by_pipe"
    };
    const field = Object.prototype.hasOwnProperty.call(sourcePredicates, code) ? "slot-source-field"
      : Object.prototype.hasOwnProperty.call(presetPredicates, code) ? "slot-preset"
        : code === "font_dependency_pending" ? "slot-font-dependencies" : "";
    if (!field) return null;
    const predicate = sourcePredicates[code] || presetPredicates[code] || ((slot) => !Array.isArray(slot.font_dependencies) || !slot.font_dependencies.length);
    const slotIndex = slots.findIndex(predicate);
    if (slotIndex < 0) return null;
    return { ...optionTarget, stage: "rules", kind: "slot", slotIndex, field };
  }

  function scanOwnedOptionIssue(issue, suffix) {
    const code = cleanText(objectOf(issue).code);
    const scanOwnedCodes = new Set([
      "anchor_belongs_to_slot", "tail_belongs_to_slot", "asset_slot_mismatch", "asset_missing",
      "asset_slot_missing", "asset_range_pending", "dimension_tolerance_pending", "dimension_tolerance_invalid",
      "font_dependency_pending", "initial_asset_source_missing", "mixed_slots_preset_invalid",
      "split_by_pipe_slot_preset_invalid", "direct_text_slot_invalid"
    ]);
    if (scanOwnedCodes.has(code)) return true;
    if (/^\.assets(?:\[|$)/.test(suffix)) return true;
    if (/^\.slots\[\*\]\.tails/.test(suffix)) return true;
    if (suffix === ".slots" && ["duplicate_name", "duplicate_path"].includes(code)) return true;
    return /^\.slots\[\d+\]\.(?:key(?:\.|$)|anchor(?:\.|$)|tails(?:\[|\.|$)|asset_key(?:\.|$)|dimension_rule(?:\.|$))/.test(suffix);
  }

  Object.assign(globalThis, { validationTargetForIssue, rescanValidationTarget, optionRescanValidationTarget, editableOptionSlotTarget, scanOwnedOptionIssue });
})();
