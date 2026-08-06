(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, PRESETS, CHECK_KEYS } = ctx;

  function buildControlledConfig() {
    const basics = formBasics();
    const outputs = collectOutputRows();
    const mappings = collectOptionMappingRows();
    const checks = collectChecks();
    return {
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
      colors: collectControlledColors(),
      field_bindings: collectFieldBindings(),
      option_mappings: mappings,
      checks,
      preview: { sample_rows: [], evidence: {} },
      audit: nextAudit()
    };
  }



  function collectOutputRows() {
    const rows = Array.from(document.querySelectorAll("#outputConfigRows .output-row"));
    const result = rows.map((row, index) => {
      const fallback = index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main";
      return {
        key: safeOutputKey(rowValue(row, "output-key"), fallback, index),
        display_name: cleanText(rowValue(row, "output-name")),
        component_key: "",
        scope: "local",
        style: { field: safeField(rowValue(row, "output-style-field")), options: [] },
        design: { field: safeField(rowValue(row, "output-design-field")), options: [] },
        font: { field: safeField(rowValue(row, "output-font-field")), options: [] }
      };
    }).filter((item) => item.key);
    return result.length ? result : [emptyOutput()];
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
    const result = {};
    Array.from(document.querySelectorAll("#fieldBindingRows .field-binding-row")).forEach((row) => {
      const key = safeField(rowValue(row, "binding-field"));
      const value = cleanText(rowValue(row, "binding-column"));
      if (key && value) result[key] = value;
    });
    return result;
  }



  function collectOptionMappingRows() {
    return Array.from(document.querySelectorAll("#optionMappingRows .option-mapping-row")).map((row) => {
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
  }



  function collectChecks() {
    const result = defaultChecks();
    CHECK_KEYS.forEach((key) => {
      const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
      const status = item ? String(item.dataset.status || "") : "";
      if (["confirmed", "pending", "blocked"].includes(status)) result[key] = { status, reason: cleanText(item.dataset.reason || "") };
    });
    return result;
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
    return optionKeysFor(output, "style", mappings, styles).map((key) => ({
      key: safeOptionKey(key, "style"),
      label: key,
      dimensions: {},
      component_key: "",
      scope: "local"
    })).filter((item) => item.key);
  }



  function designOptionsFor(output, mappings, designs, slots) {
    return optionKeysFor(output, "design", mappings, designs).map((key) => ({
      key: safeOptionKey(key, "design"),
      label: key,
      content_preset: "direct_text",
      component_key: "",
      scope: "local",
      font_dependencies: [],
      slots: controlledSlots(slots),
      assets: []
    })).filter((item) => item.key);
  }



  function fontOptionsFor(output, mappings, fonts, slots) {
    return optionKeysFor(output, "font", mappings, fonts).map((key) => ({
      key: safeOptionKey(key, "font"),
      label: key,
      content_preset: "direct_text",
      component_key: "",
      scope: "local",
      font_dependencies: [cleanText(key)].filter(Boolean),
      slots: controlledSlots(slots),
      assets: []
    })).filter((item) => item.key);
  }



  function optionKeysFor(output, group, mappings, scanItems) {
    const mapped = mappings.filter((item) => item.output === output && item.group === group).map((item) => item.target);
    const scanned = scanItems.map((item) => item.key || item.name || item.label).filter(Boolean);
    return unique([...mapped, ...scanned]).slice(0, 30);
  }



  function controlledSlots(slots) {
    const source = slots.length ? slots : [{ name: "name" }];
    return source.slice(0, 12).map((item) => {
      const raw = cleanText(item.key || item.name || item.label || "name");
      const suffix = safeIdentifier(raw.replace(/^slot_/, ""), "name").toLowerCase();
      const field = safeField(item.source_field || item.field || suffix) || "name";
      const preset = PRESETS.includes(item.preset) ? item.preset : "direct_text";
      return {
        key: `slot_${suffix}`,
        source_field: field,
        required: item.required === false ? false : true,
        preset,
        anchor: "",
        tails: [],
        asset_key: "",
        dimension_rule: {},
        font_dependencies: [],
        color_binding: ""
      };
    });
  }




  Object.assign(globalThis, {
    buildControlledConfig,
    collectOutputRows,
    withControlledGroups,
    collectFieldBindings,
    collectOptionMappingRows,
    collectChecks,
    collectControlledColors,
    nextAudit,
    styleOptionsFor,
    designOptionsFor,
    fontOptionsFor,
    optionKeysFor,
    controlledSlots
  });
})();
