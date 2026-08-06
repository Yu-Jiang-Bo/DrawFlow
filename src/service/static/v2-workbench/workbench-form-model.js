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
      result[key] = { status: "pending", reason: "等待人工核验" };
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
        style: { field: inferredGroupField("style") },
        design: { field: inferredGroupField("design") },
        font: { field: inferredGroupField("font") }
      }));
    }
    return [emptyOutput()];
  }



  function inferredFields() {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const fields = ["name"];
    ["styles", "designs", "fonts", "colors", "slots"].forEach((key) => {
      model[key].forEach((item) => {
        const field = safeField(item.field || item.source_field || item.name);
        if (field) fields.push(field);
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
      items.slice(0, 12).forEach((item) => {
        const target = safeOptionKey(item.key || item.name, group);
        if (!target) return;
        rows.push({ field: inferredGroupField(group), source_value: displayOptionSource(target, group), target, output: "Output_main", group });
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
    inferredMappings,
    inferredGroupField,
    emptyOutput
  });
})();
