(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, CHECK_KEYS, CHECK_LABELS, STATUS_LABELS, STATUS_CLASS } = ctx;

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


  function renderStructureTree() {
    const target = $("structureTree");
    if (!target) return;
    target.replaceChildren();
    const scan = state.scan || {};
    const model = scanModel(scan, state.draft && state.draft.config);
    const search = valueOf("structureSearch").trim().toLowerCase();
    if (!modelHasItems(model)) {
      target.appendChild(emptyNode("等待扫描结果"));
      setText("selectedNodeSummary", "扫描接口未就绪或尚未返回结构。");
      updateToggleButtons();
      return;
    }
    Object.keys(model).forEach((key) => {
      const items = filterItems(model[key], search);
      if (!items.length) return;
      const section = document.createElement("section");
      section.className = "structure-section";
      section.appendChild(metaNode(sectionTitle(key, items.length)));
      visibleSectionItems(key, items, Boolean(search)).forEach((item) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "structure-node";
        row.dataset.nodeKind = key;
        row.textContent = nodeTitle(item);
        row.addEventListener("click", () => setText("selectedNodeSummary", nodeSummary(key, item)));
        section.appendChild(row);
      });
      target.appendChild(section);
    });
    if (!target.children.length) target.appendChild(emptyNode("没有匹配的结构项"));
    updateToggleButtons();
  }


  function renderTables() {
    renderOutputRows();
    renderFieldBindingRows();
    renderOptionMappingRows();
    renderContentOptionRows();
    updateBlockers();
  }


  function renderOutputRows() {
    const target = $("outputConfigRows");
    if (!target) return;
    const outputs = configOutputs().length ? configOutputs() : inferredOutputs();
    target.replaceChildren(tableHeader(["输出", "名称", "用途", "样式字段", "设计字段", "字体字段"]));
    (outputs.length ? outputs : [emptyOutput()]).forEach((output, index) => {
      const row = tableRow("output-row");
      row.append(
        inputCell("output-key", output.key || (index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main")),
        inputCell("output-name", output.display_name || ""),
        inputCell("output-component", output.component_key || ""),
        inputCell("output-style-field", objectOf(output.style).field || ""),
        inputCell("output-design-field", objectOf(output.design).field || ""),
        inputCell("output-font-field", objectOf(output.font).field || "")
      );
      target.appendChild(row);
    });
    target.appendChild(addRowButton("添加输出", () => {
      target.insertBefore(outputRowElement(emptyOutput()), target.lastElementChild);
    }));
  }


  function outputRowElement(output) {
    const row = tableRow("output-row");
    row.append(
      inputCell("output-key", output.key || "Output_main"),
      inputCell("output-name", output.display_name || ""),
      inputCell("output-component", output.component_key || ""),
      inputCell("output-style-field", ""),
      inputCell("output-design-field", ""),
      inputCell("output-font-field", "")
    );
    return row;
  }


  function renderFieldBindingRows() {
    const target = $("fieldBindingRows");
    if (!target) return;
    const bindings = objectOf(state.draft && state.draft.config && state.draft.config.field_bindings);
    const fields = Object.keys(bindings).length ? Object.keys(bindings) : inferredFields();
    target.replaceChildren(tableHeader(["内部字段", "订单表头", "状态"]));
    (fields.length ? fields : ["name"]).forEach((field) => {
      const row = tableRow("field-binding-row");
      row.append(inputCell("binding-field", field), inputCell("binding-column", bindings[field] || ""), selectCell("binding-required", [["required", "必填"], ["optional", "可选"]], "required"));
      target.appendChild(row);
    });
    target.appendChild(addRowButton("添加字段", () => {
      const row = tableRow("field-binding-row");
      row.append(inputCell("binding-field", ""), inputCell("binding-column", ""), selectCell("binding-required", [["required", "必填"], ["optional", "可选"]], "required"));
      target.insertBefore(row, target.lastElementChild);
    }));
  }


  function renderOptionMappingRows() {
    const target = $("optionMappingRows");
    if (!target) return;
    const mappings = configOptionMappings().length ? configOptionMappings() : inferredMappings();
    target.replaceChildren(tableHeader(["字段", "订单原值", "目标选项", "输出", "类型"]));
    (mappings.length ? mappings : [{ field: "", source_value: "", target: "", output: "Output_main", group: "design" }]).forEach((mapping) => {
      target.appendChild(optionMappingRow(mapping));
    });
    target.appendChild(addRowButton("添加映射", () => {
      target.insertBefore(optionMappingRow({ field: "", source_value: "", target: "", output: "Output_main", group: "design" }), target.lastElementChild);
    }));
  }


  function optionMappingRow(mapping) {
    const row = tableRow("option-mapping-row");
    row.append(
      inputCell("mapping-field", mapping.field || ""),
      inputCell("mapping-source", mapping.source_value || ""),
      inputCell("mapping-target", mapping.target || ""),
      selectCell("mapping-output", outputOptions(mapping.output), mapping.output || "Output_main"),
      selectCell("mapping-group", [["style", "样式"], ["design", "设计"], ["font", "字体"], ["color", "颜色"]], mapping.group || "design")
    );
    return row;
  }

  function outputOptions(selected) {
    const options = [["Output_main", "Output_main"]];
    (configOutputs().length ? configOutputs() : inferredOutputs()).forEach((output) => {
      const key = safeOutputKey(output.key || output.name, "Output_main", options.length - 1);
      if (key && !options.some(([value]) => value === key)) options.push([key, key]);
    });
    if (selected && !options.some(([value]) => value === selected)) options.push([selected, selected]);
    return options;
  }


  function updateToggleButtons() {
    setText("toggleDesignsBtn", state.expanded.designs ? "收起设计" : "展开全部设计");
    setText("toggleFontsBtn", state.expanded.fonts ? "收起字体" : "展开全部字体");
  }


  function updateCheckRail(checks) {
    const normalized = normalizeChecks(checks);
    CHECK_KEYS.forEach((key) => {
      const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
      const check = normalized[key] || { status: "pending", reason: "" };
      if (!item) return;
      item.dataset.status = check.status;
      item.dataset.reason = check.reason || "";
      item.classList.remove("passed", "pending", "warn", "blocked", "confirmed", "success");
      item.classList.add(STATUS_CLASS[check.status] || "pending");
      const label = item.querySelector(".check-label, span");
      const status = item.querySelector(".check-status, strong");
      if (label) label.textContent = CHECK_LABELS[key] || key;
      if (status) status.textContent = STATUS_LABELS[check.status] || "待校验";
      if (!label && !status) item.textContent = `${CHECK_LABELS[key] || key}：${STATUS_LABELS[check.status] || "待校验"}`;
      item.title = check.reason || STATUS_LABELS[check.status] || "";
    });
  }


  function normalizeChecks(checks) {
    const result = defaultChecks();
    Object.keys(objectOf(checks)).forEach((key) => {
      if (!CHECK_KEYS.includes(key)) return;
      const raw = checks[key];
      const status = typeof raw === "string" ? raw : objectOf(raw).status;
      const reason = typeof raw === "string" ? "" : objectOf(raw).reason || objectOf(raw).reasons;
      result[key] = { status: safeStatus(status), reason: Array.isArray(reason) ? reason.join("；") : cleanText(reason || "") };
    });
    return result;
  }


  function updateBlockers(validation) {
    const target = $("blockerList");
    const checks = normalizeChecks(validation && validation.checks ? validation.checks : configChecks());
    const issues = Array.isArray(validation && validation.issues) ? validation.issues : [];
    const blockers = [];
    CHECK_KEYS.forEach((key) => {
      if (checks[key].status !== "confirmed") blockers.push(`${CHECK_LABELS[key]}：${checks[key].reason || STATUS_LABELS[checks[key].status]}`);
    });
    issues.slice(0, 8).forEach((issue) => blockers.push(cleanText(issue.reason || issue.message || "有未完成核验项")));
    if (target) {
      target.replaceChildren();
      (blockers.length ? unique(blockers) : ["已完成核验，可进入下一步。"]).forEach((text) => {
        const item = document.createElement("li");
        item.textContent = text;
        target.appendChild(item);
      });
    }
    const ready = validation && validation.can_publish === true && !blockers.length;
    setDisabled("publishVersionBtn", !ready);
    setDisabled("trialRenderBtn", !state.draft);
    setText("publishBlockerText", ready ? "核验已完成，发布接口未接入。" : (blockers[0] || "请先完成草稿配置与人工核验。"));
  }


  function setDraftStatus(text, status) {
    const el = $("draftStatusBadge");
    if (!el) return;
    el.textContent = text;
    el.dataset.status = status || "pending";
  }


  function showTransientStatus(text) {
    setText("publishBlockerText", text);
  }

  Object.assign(globalThis, {
    renderTemplateList,
    fillDraftFields,
    templateContextText,
    renderScanSummary,
    renderStructureTree,
    renderTables,
    renderOutputRows,
    outputRowElement,
    renderFieldBindingRows,
    renderOptionMappingRows,
    optionMappingRow,
    updateToggleButtons,
    updateCheckRail,
    normalizeChecks,
    updateBlockers,
    setDraftStatus,
    showTransientStatus
  });
})();
