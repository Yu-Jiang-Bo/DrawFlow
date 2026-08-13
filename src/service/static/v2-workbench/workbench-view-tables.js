(function () {
  "use strict";
  const { state } = globalThis.DrawFlowV2WorkbenchContext;

  function renderTemplateList() {
    const target = $("templateList");
    if (!target) return;
    const keyword = valueOf("templateSearch").trim().toLowerCase();
    const items = state.templates.filter((item) => {
      const text = [templateIdOf(item), templateNameOf(item), shopNameOf(item)].join(" ").toLowerCase();
      return !keyword || text.includes(keyword);
    });
    target.replaceChildren();
    globalThis.renderTemplateStats(items);
    if (!items.length) {
      target.appendChild(emptyNode(state.templates.length ? "没有匹配的模板" : "暂无模板草稿"));
      return;
    }
    items.forEach((item) => {
      const id = templateIdOf(item);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "template-list-item" + (id === state.selectedTemplateId ? " active" : "");
      button.dataset.templateId = id;
      button.appendChild(lineNode(templateNameOf(item) || id, id));
      button.appendChild(metaNode([shopNameOf(item), draftLabel(item), publicationLabel(item)].filter(Boolean).join(" · ")));
      button.addEventListener("click", () => selectTemplate(id));
      target.appendChild(button);
    });
  }

  function fillDraftFields(draft, fallbackId) {
    const template = objectOf(draft && (draft.metadata || draft.template || objectOf(draft.manifest).template));
    setValue("templateId", template.template_id || fallbackId || "");
    setValue("templateName", template.name || "");
    setValue("shopName", template.shop_name || "");
    const manifest = objectOf(draft && draft.manifest);
    setText("draftVersion", manifest.draft_revision || manifest.version || "-");
    setText("currentTemplateContext", templateContextText(template, fallbackId));
    setDraftStatus(draft ? "草稿已读取" : "等待创建草稿", draft ? "confirmed" : "pending");
  }

  function templateContextText(template, fallbackId) {
    const id = cleanText(template.template_id || fallbackId || "");
    const name = cleanText(template.name || "");
    if (!id) return "未选择模板";
    return name ? `${id} · ${name}` : `${id} · 等待创建草稿`;
  }

  function renderScanSummary(message) {
    const scan = state.scan || {};
    const summary = scanSummary(scan);
    const hasScan = summary.total > 0 || Object.keys(scan).length > 0;
    globalThis.renderScanMetrics(summary);
    setText("scanSummary", message || (hasScan ? summaryText(summary) : "等待扫描结果"));
    setText("scanSummaryWarning", globalThis.scanWarningText(summary, hasScan));
    setText("uploadScanBadge", hasScan ? "扫描已完成" : (state.uploadFile ? "待上传" : "等待文件"));
    if (globalThis.renderScanProgress) {
      globalThis.renderScanProgress(message || (hasScan ? "等待人工核验" : "等待选择 .ai 文件"), "idle");
    }
    setText("scanEmptyState", hasScan ? "" : "等待扫描结果，扫描接口未就绪时可先保存文件。");
    setHidden("scanEmptyState", hasScan);
    setDisabled("enterStructureBtn", !hasScan);
    setText("draftSummary", draftSummaryText(summary));
  }

  function renderTables() {
    renderOutputRows();
    renderFieldBindingRows();
    renderOptionMappingRows();
    renderStyleDimensionRows();
    renderContentOptionRows();
    updateBlockers();
  }

  function renderOutputRows() {
    const target = $("outputConfigRows");
    if (!target) return;
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    const header = tableHeader(["输出", "名称", "用途"]);
    target.replaceChildren(header);
    (outputs.length ? outputs : [emptyOutput()]).forEach((output, index) => {
      const outputData = objectOf(output);
      const hasConfiguredKey = Object.prototype.hasOwnProperty.call(outputData, "key") || Object.prototype.hasOwnProperty.call(outputData, "name");
      const fallbackKey = index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main";
      const key = hasConfiguredKey
        ? cleanText(Object.prototype.hasOwnProperty.call(outputData, "key") ? outputData.key : outputData.name)
        : fallbackKey;
      const singleMain = outputs.length === 1 && key === "Output_main";
      const row = tableRow("output-row");
      row.append(
        inputCell("output-key", key),
        inputCell("output-name", output.display_name || (singleMain ? "主效果图" : "")),
        inputCell("output-component", output.component_key || (singleMain ? "main" : ""))
      );
      target.appendChild(row);
    });
  }

  function renderFieldBindingRows() {
    const target = $("fieldBindingRows");
    if (!target) return;
    const bindings = objectOf(state.draft && state.draft.config && state.draft.config.field_bindings);
    const allowed = inferredFields();
    const fields = unique([...allowed, ...Object.keys(bindings).filter((field) => fieldBindingAllowed(field, allowed))]);
    target.replaceChildren(tableHeader(["模板对象", "订单字段", "适用范围", "状态"]));
    (fields.length ? fields : ["name"]).forEach((field) => {
      const row = tableRow("field-binding-row");
      row.append(
        inputCell("binding-field", field),
        inputCell("binding-column", bindings[field] || ""),
        scopeCell(bindingScopeText(field)),
        bindingStatusCell(Boolean(bindings[field]))
      );
      target.appendChild(row);
    });
    target.appendChild(addRowButton("添加字段", () => {
      const row = tableRow("field-binding-row");
      row.append(inputCell("binding-field", ""), inputCell("binding-column", ""), scopeCell("全部 Output"), bindingStatusCell(false));
      target.insertBefore(row, target.lastElementChild);
    }));
  }

  function scopeCell(text) {
    const cell = document.createElement("div");
    cell.className = "binding-scope-cell";
    cell.textContent = text || "全部 Output";
    return cell;
  }

  function bindingScopeText(field) {
    if (field === "color") return "全部文字";
    if (["design", "font", "style"].includes(field)) return groupScopeText(field);
    return "全部 Output";
  }

  function groupScopeText(group) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const source = group === "design" ? model.designs : group === "font" ? model.fonts : model.styles;
    const scopes = unique(source.map((item) => cleanText(item.output || item.output_key || ""))).filter(Boolean);
    if (!scopes.length) return "全部 Output";
    if (scopes.length === 1) return scopes[0].replace(/^Output_/, "") || scopes[0];
    return "多个 Output";
  }

  function bindingStatusCell(bound) {
    const cell = document.createElement("div");
    cell.className = `binding-status-cell ${bound ? "success" : "warn"}`;
    cell.textContent = bound ? "已绑定" : "待确认";
    return cell;
  }

  function renderOptionMappingRows() {
    const target = $("optionMappingRows");
    if (!target) return;
    const mappings = effectiveOptionMappings();
    const multiOutput = (configOutputs().length ? configOutputs() : inferredOutputs()).length > 1;
    const header = tableHeader(multiOutput ? ["字段", "订单原值", "目标选项", "输出", "类型"] : ["字段", "订单原值", "目标选项", "类型"]);
    header.classList.add("option-mapping-layout");
    if (!multiOutput) header.classList.add("single-output");
    target.replaceChildren(header);
    (mappings.length ? mappings : [{ field: "", source_value: "", target: "", output: "Output_main", group: "design" }]).forEach((mapping) => {
      target.appendChild(optionMappingRow(mapping));
    });
    target.appendChild(addRowButton("添加映射", () => {
      target.insertBefore(optionMappingRow({ field: "", source_value: "", target: "", output: "Output_main", group: "design" }), target.lastElementChild);
    }));
  }

  function optionMappingRow(mapping) {
    const group = mapping.group || "design";
    const row = tableRow("option-mapping-row");
    const cells = [
      inputCell("mapping-field", mapping.field || ""),
      inputCell("mapping-source", mapping.source_value || ""),
      selectCell("mapping-target", mappingTargetOptions(group, mapping.target), mapping.target || "")
    ];
    if ((configOutputs().length ? configOutputs() : inferredOutputs()).length > 1) cells.push(selectCell("mapping-output", outputOptions(mapping.output), mapping.output || "Output_main"));
    else row.classList.add("single-output");
    cells.push(selectCell("mapping-group", [["style", "样式"], ["design", "设计"], ["font", "字体"], ["color", "颜色"]], group));
    row.append(...cells);
    return row;
  }

  function mappingTargetOptions(group, selected) {
    const model = scanModel(state.scan, state.draft && state.draft.config);
    const source = group === "style" ? model.styles : group === "font" ? model.fonts : group === "color" ? model.colors : model.designs;
    const values = unique([selected, ...source.map((item) => item.key || item.name || item.label)]).map((item) => safeOptionKey(item, group)).filter(Boolean);
    return [["", "选择目标"], ...values.map((value) => [value, value])];
  }

  function outputOptions(selected) {
    const options = [];
    (configOutputs().length ? configOutputs() : inferredOutputs()).forEach((output) => {
      const key = safeOutputKey(output.key || output.name, "Output_main", options.length - 1);
      const label = cleanText(output.display_name) || (key === "Output_main" ? "主效果图" : key);
      if (key && !options.some(([value]) => value === key)) options.push([key, label]);
    });
    if (selected && !options.some(([value]) => value === selected)) options.push([selected, selected]);
    return options.length ? options : [["Output_main", "主效果图"]];
  }

  function updateToggleButtons() {
    setText("toggleDesignsBtn", state.expanded.designs ? "收起设计" : "展开全部设计");
    setText("toggleFontsBtn", state.expanded.fonts ? "收起字体" : "展开全部字体");
  }

  Object.assign(globalThis, {
    renderTemplateList,
    fillDraftFields,
    templateContextText,
    renderScanSummary,
    renderTables,
    renderOutputRows,
    renderFieldBindingRows,
    renderOptionMappingRows,
    optionMappingRow,
    updateToggleButtons
  });
})();
