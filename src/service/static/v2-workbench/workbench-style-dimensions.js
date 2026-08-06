(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderStyleDimensionRows() {
    const target = $("styleDimensionRows");
    if (!target) return;
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    target.replaceChildren(tableHeader(["输出", "Style", "X 宽 mm", "Y 高 mm", "最终适配"]));
    (outputs.length ? outputs : [emptyOutput()]).forEach((output, index) => {
      const outputKey = safeOutputKey(
        output.key || output.name,
        index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main",
        index
      );
      const allowFixed = outputs.length === 1 && !model.styles.length && !optionKeysFromConfig(outputKey, "style").length;
      styleDimensionKeys(outputKey, model.styles, allowFixed).forEach((key) => {
        const row = tableRow("style-dimension-row");
        const dimensions = existingStyleDimensions(outputKey, key, model.styles);
        row.dataset.output = outputKey;
        row.dataset.styleKey = key;
        row.append(
          inputCell("style-output", outputKey),
          inputCell("style-key", key),
          inputCell("style-width-mm", dimensions.width_mm || ""),
          inputCell("style-height-mm", dimensions.height_mm || ""),
          staticMetaCell("X/Y 独立适配 · 0.007mm")
        );
        target.appendChild(row);
      });
    });
  }

  function styleDimensionKeys(output, styles, allowFixed) {
    const mappings = configOptionMappings().length ? configOptionMappings() : inferredMappings();
    const configured = optionKeysFromConfig(output, "style");
    const scanned = scopedScanItemsFor(output, styles).map((item) => safeOptionKey(item.key || item.name || item.label, "style")).filter(Boolean);
    const keys = unique([...optionKeysFor(output, "style", mappings, styles), ...configured, ...scanned]);
    return (keys.length ? keys : (allowFixed ? ["style1"] : [])).slice(0, 12);
  }

  function optionKeysFromConfig(output, group) {
    const found = configOutputs().find((item) => safeOutputKey(item.key, "Output_main", 0) === output);
    const options = objectOf(objectOf(found)[group]).options;
    return (Array.isArray(options) ? options : [])
      .map((item) => safeOptionKey(item.key || item.name || item.label, group))
      .filter(Boolean);
  }

  function existingStyleDimensions(output, key, styles) {
    const configured = findConfigOption(output, "style", key);
    const scanned = objectOf(scopedScanItemsFor(output, styles).find((item) => safeOptionKey(item.key || item.name || item.label, "style") === key));
    return objectOf(configured.dimensions || scanned.dimensions || scanned);
  }

  function staticMetaCell(text) {
    const cell = document.createElement("div");
    cell.className = "content-meta-cell";
    cell.textContent = text || "";
    return cell;
  }

  Object.assign(globalThis, {
    renderStyleDimensionRows,
    styleDimensionKeys,
    optionKeysFromConfig
  });
})();
