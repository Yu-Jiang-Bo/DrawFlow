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
    return {
      template_id: cleanText(valueOf("templateId")),
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
    if (model.colors.length) fields.push("color");
    model.slots.forEach((item) => {
      const field = safeField(item.source_field || item.field || slotFieldName(item.key || item.name));
      if (field) fields.push(field);
    });
    configuredSlotSourceFields().forEach((field) => {
      if (field) fields.push(field);
    });
    return unique(fields);
  }


  function configuredSlotSourceFields() {
    const fields = [];
    configOutputs().forEach((output) => {
      ["design", "font"].forEach((group) => {
        const section = objectOf(output[group]);
        const options = Array.isArray(section.options) ? section.options : [];
        options.forEach((option) => {
          const optionData = objectOf(option);
          const slots = Array.isArray(optionData.slots) ? optionData.slots : [];
          slots.forEach((slot) => {
            const field = safeField(objectOf(slot).source_field);
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
    optionOutputKey,
    emptyOutput
  });
})();
