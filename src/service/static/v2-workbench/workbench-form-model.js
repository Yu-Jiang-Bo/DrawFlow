(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, CHECK_KEYS } = ctx;

  function configChecks() {
    const config = objectOf(state.draft && state.draft.config);
    return normalizeChecks(config.checks || defaultChecks());
  }



  function defaultChecks() {
    return CHECK_KEYS.reduce((result, key) => {
      result[key] = { status: "pending", reason: "" };
      return result;
    }, {});
  }



  function formBasics() {
    // A selected template already owns persisted AI assets, scan evidence and
    // version history.  Its ID is therefore the save identity, not an editable
    // display value from the form.
    const selectedTemplateId = cleanText(state.selectedTemplateId);
    return {
      template_id: selectedTemplateId || cleanText(valueOf("templateId")),
      name: cleanText(valueOf("templateName")),
      shop_name: cleanText(valueOf("shopName"))
    };
  }



  function normalizeScanFromDraft(draft) {
    const data = objectOf(draft);
    return objectOf(data.scan || data.scan_result || objectOf(data.metadata).scan || {});
  }



  function configOutputs() {
    const outputs = state.draft && state.draft.config && state.draft.config.outputs;
    return Array.isArray(outputs) ? outputs : [];
  }



  function configOptionMappings() {
    const mappings = state.draft && state.draft.config && state.draft.config.option_mappings;
    return Array.isArray(mappings) ? mappings : [];
  }



  function inferredOutputs() {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    if (model.outputs.length) {
      return model.outputs.slice(0, 12).map((item, index) => ({
        key: safeOutputKey(item.key || item.name, index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main", index),
        display_name: cleanText(item.display_name || item.name || ""),
        style: { field: model.styles.length ? inferredGroupField("style") : "" },
        design: { field: model.designs.length ? inferredGroupField("design") : "" },
        font: { field: model.fonts.length ? inferredGroupField("font") : "" }
      }));
    }
    return [emptyOutput()];
  }



  function inferredFields() {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const fields = ["name"];
    if (model.designs.length) fields.push("design");
    if (model.fonts.length) fields.push("font");
    if (model.styles.length) fields.push("style");
    fields.push("color");
    const configuredSources = configuredSlotSourceFields();
    model.slots.forEach((item) => {
      const field = inferredScannedSlotField(item);
      if (field) fields.push(field);
    });
    configuredSources.forEach((field) => {
      if (field) fields.push(field);
    });
    return unique(fields);
  }


  function inferredScannedSlotField(slot) {
    const data = objectOf(slot);
    const slotField = safeField(slotFieldName(data.key || data.name || data.label));
    if (!slotField) return safeField(data.source_field || data.field);
    const group = cleanText(data.group);
    const optionKey = safeOptionKey(data.option || data.option_key || data.optionKey, group);
    const outputKey = safeOutputKey(data.output || data.output_key || data.outputKey, "Output_main", 0);
    const output = configOutputs().find((item, index) => (
      safeOutputKey(objectOf(item).key || objectOf(item).name, index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main", index) === outputKey
    ));
    const options = Array.isArray(objectOf(objectOf(output)[group]).options) ? objectOf(objectOf(output)[group]).options : [];
    const option = objectOf(options.find((item) => safeOptionKey(item.key || item.name || item.label, group) === optionKey));
    const configuredSlots = Array.isArray(option.slots) ? option.slots : [];
    const configuredSlot = configuredSlots.find((item) => (
      safeField(slotFieldName(objectOf(item).key || objectOf(item).name || objectOf(item).label)) === slotField
    ));
    if (!configuredSlot) return slotField;
    return canonicalSlotSourceField(configuredSlot, option, data);
  }


  function configuredSlotSourceFields() {
    const fields = [];
    const model = scanModel(state.scan, state.draft && state.draft.config);
    configOutputs().forEach((output, outputIndex) => {
      const fallback = outputIndex ? `Output_Side${String.fromCharCode(65 + outputIndex)}` : "Output_main";
      const outputKey = safeOutputKey(output.key || output.name, fallback, outputIndex);
      ["design", "font"].forEach((group) => {
        const section = objectOf(output[group]);
        const options = Array.isArray(section.options) ? section.options : [];
        const scanItems = group === "design" ? model.designs : model.fonts;
        const scopedItems = typeof scopedScanItemsFor === "function" ? scopedScanItemsFor(outputKey, scanItems) : scanItems;
        options.forEach((option) => {
          const optionData = objectOf(option);
          const optionKey = safeOptionKey(optionData.key || optionData.name || optionData.label, group);
          const scannedOption = objectOf(scopedItems.find((item) => (
            safeOptionKey(item.key || item.name || item.label, group) === optionKey
          )));
          const slots = Array.isArray(optionData.slots) ? optionData.slots : [];
          slots.forEach((slot) => {
            const slotKey = safeField(slotFieldName(objectOf(slot).key || objectOf(slot).name || objectOf(slot).label));
            const scannedSlot = objectOf((Array.isArray(scannedOption.slots) ? scannedOption.slots : []).find((item) => (
              safeField(slotFieldName(objectOf(item).key || objectOf(item).name || objectOf(item).label)) === slotKey
            )));
            const field = canonicalSlotSourceField(slot, optionData, scannedSlot);
            if (field) fields.push(field);
          });
        });
      });
    });
    return unique(fields);
  }



  function inferredMappings() {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const rows = [];
    [
      ["style", model.styles],
      ["design", model.designs],
      ["font", model.fonts]
    ].forEach(([group, items]) => {
      items.forEach((item) => {
        const target = safeOptionKey(item.key || item.name, group);
        if (!target) return;
        const output = optionOutputKey(item);
        if (!output) return;
        rows.push({ field: inferredGroupField(group), source_value: displayOptionSource(target, group), target, output, group });
      });
    });
    return rows;
  }



  function inferredGroupField(group) {
    if (group === "style") return "style";
    if (group === "design") return "design";
    if (group === "font") return "font";
    return "";
  }


  function slotFieldName(value) {
    return cleanText(value || "").replace(/^slot_/, "");
  }


  function canonicalSlotSourceField(slot, option, scannedSlot) {
    const data = objectOf(slot);
    const optionData = objectOf(option);
    const scanData = objectOf(scannedSlot);
    const slotField = safeField(slotFieldName(data.key || data.name || data.label));
    const configured = safeField(data.source_field || data.field || slotField) || "name";
    if (!slotField || configured === slotField) return configured;
    const scannedField = safeField(slotFieldName(scanData.key || scanData.name || scanData.label));
    if (!scannedField || scannedField !== slotField) return configured;
    const slots = Array.isArray(optionData.slots) ? optionData.slots : [];
    const mixed = cleanText(optionData.content_preset) === "mixed_slots"
      || (slots.length > 1 && slots.some((item) => Array.isArray(objectOf(item).tails) && objectOf(item).tails.length));
    if (!mixed) return configured;
    const bindings = objectOf(state.draft && state.draft.config && state.draft.config.field_bindings);
    const configuredColumn = cleanText(bindings[configured]);
    const slotColumn = cleanText(bindings[slotField]);
    return slotColumn && configuredColumn === slotColumn ? slotField : configured;
  }


  function optionOutputKey(item) {
    const data = objectOf(item);
    const nested = objectOf(data.output);
    const raw = cleanText(nested.key || nested.name || data.output_key || data.outputKey || data.parent_output || data.parentOutput || data.output);
    if (raw) return safeOutputKey(raw, "Output_main", 0);
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    if (outputs.length === 1) return safeOutputKey(outputs[0].key || outputs[0].name, "Output_main", 0);
    return "";
  }



  function emptyOutput() {
    return { key: "Output_main", display_name: "", component_key: "", scope: "local", style: { field: "" }, design: { field: "" }, font: { field: "" } };
  }


  function hasScanEvidence(scan) {
    const outputs = objectOf(scan).outputs;
    return Array.isArray(outputs) && outputs.some((output) => {
      const item = objectOf(output);
      return Boolean(String(item.key || "").trim() || String(item.path || "").trim());
    });
  }


  function sameTemplateIdentity(left, right) {
    const first = cleanText(left);
    const second = cleanText(right);
    return Boolean(first && second && first.toLowerCase() === second.toLowerCase());
  }


  function canRetainPreviousScan(scan, targetTemplateId) {
    const targetId = String(targetTemplateId || "").trim();
    if (!targetId || !sameTemplateIdentity(state.selectedTemplateId, targetId)) return false;
    const draftMetadata = objectOf(objectOf(state.draft).metadata);
    return sameTemplateIdentity(draftMetadata.template_id, targetId) && hasScanEvidence(scan);
  }


  function prepareSaveTarget(templateId) {
    const targetId = String(templateId || "").trim();
    const selectedId = String(state.selectedTemplateId || "").trim();
    if (!selectedId || selectedId === targetId) return;
    state.draftLoadRequestId += 1;
    state.selectedTemplateId = targetId;
    state.draft = null;
    state.scan = {};
  }


  function isCurrentTemplateResponse(draft, targetTemplateId) {
    const targetId = String(targetTemplateId || "").trim();
    const responseId = String(objectOf(objectOf(draft).metadata).template_id || "").trim();
    return Boolean(targetId && sameTemplateIdentity(responseId, targetId) && sameTemplateIdentity(state.selectedTemplateId, targetId));
  }




  Object.assign(globalThis, {
    configChecks,
    defaultChecks,
    formBasics,
    normalizeScanFromDraft,
    configOutputs,
    configOptionMappings,
    inferredOutputs,
    inferredFields,
    configuredSlotSourceFields,
    inferredMappings,
    inferredGroupField,
    slotFieldName,
    canonicalSlotSourceField,
    optionOutputKey,
    emptyOutput,
    hasScanEvidence,
    sameTemplateIdentity,
    canRetainPreviousScan,
    prepareSaveTarget,
    isCurrentTemplateResponse
  });
})();
