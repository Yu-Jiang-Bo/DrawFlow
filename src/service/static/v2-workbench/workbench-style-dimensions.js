(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderStyleDimensionRows() {
    const target = $("styleDimensionRows");
    if (!target) return;
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const header = tableHeader(["输出", "Style", "X 宽 mm", "Y 高 mm", "尺寸验收"]);
    target.replaceChildren(header);
    let rendered = 0;
    (outputs.length ? outputs : [emptyOutput()]).forEach((output, index) => {
      const outputKey = safeOutputKey(
        output.key || output.name,
        index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main",
        index
      );
      styleDimensionKeys(outputKey, model.styles).forEach((key) => {
        const row = tableRow("style-dimension-row");
        const dimensions = existingStyleDimensions(outputKey, key, model.styles);
        row.dataset.output = outputKey;
        row.dataset.styleKey = key;
        row.append(
          inputCell("style-output", outputKey),
          inputCell("style-key", key),
          inputCell("style-width-mm", dimensions.width_mm || ""),
          inputCell("style-height-mm", dimensions.height_mm || ""),
          staticMetaCell("误差上限 0.007mm，禁止超出")
        );
        target.appendChild(row);
        rendered += 1;
      });
    });
    if (!rendered) target.appendChild(emptyNode("未扫描到 Style 尺寸框，当前模板无需填写固定尺寸。"));
  }

  function styleDimensionKeys(output, styles) {
    const mappings = effectiveOptionMappings();
    const scanned = scopedScanItemsFor(output, styles).map((item) => safeOptionKey(item.key || item.name || item.label, "style")).filter(Boolean);
    const keys = unique([...optionKeysFor(output, "style", mappings, styles), ...scanned]);
    return keys.slice(0, 12);
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
    styleDimensionKeys
  });
})();
