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
      const key = output.key || (index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main");
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


  function updateCheckRail(checks) {
    const normalized = normalizeChecks(checks);
    CHECK_KEYS.forEach((key) => {
      const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
      const check = normalized[key] || { status: "pending", reason: "" };
      if (!item) return;
      const hasExplicitReason = checkHasExplicitReason(checks, key);
      const preservedReason = hasExplicitReason ? "" : manualReasonForCheck(item.dataset.reason || "");
      const reason = check.reason || preservedReason;
      item.dataset.status = check.status;
      item.dataset.reason = reason;
      item.classList.remove("passed", "pending", "warn", "blocked", "confirmed", "success");
      item.classList.add(STATUS_CLASS[check.status] || "pending");
      const label = item.querySelector(".check-label, span");
      const status = item.querySelector(".check-status, strong");
      if (label) label.textContent = CHECK_LABELS[key] || key;
      if (status) status.textContent = STATUS_LABELS[check.status] || "待校验";
      if (!label && !status) item.textContent = `${CHECK_LABELS[key] || key}：${STATUS_LABELS[check.status] || "待校验"}`;
      item.title = check.displayReason || reason || STATUS_LABELS[check.status] || "";
    });
  }


  function checkHasExplicitReason(checks, key) {
    const raw = objectOf(checks)[key];
    return Boolean(raw && typeof raw === "object" && !Array.isArray(raw) && Object.prototype.hasOwnProperty.call(raw, "reason"));
  }


  function normalizeChecks(checks) {
    const result = defaultChecks();
    Object.keys(objectOf(checks)).forEach((key) => {
      if (!CHECK_KEYS.includes(key)) return;
      const raw = checks[key];
      const rawObject = objectOf(raw);
      const status = typeof raw === "string" ? raw : objectOf(raw).status;
      const manualReason = typeof raw === "string" ? "" : manualReasonForCheck(rawObject.reason || "");
      const validationReasons = typeof raw === "string" ? [] : validationReasonsForCheck(rawObject);
      const displayReasons = unique([manualReason, ...validationReasons].map((item) => cleanText(item))).filter(Boolean);
      result[key] = {
        status: safeStatus(status),
        reason: manualReason,
        reasons: displayReasons,
        displayReason: compactReasons(displayReasons)
      };
    });
    return result;
  }


  function validationReasonsForCheck(check) {
    const result = [];
    if (Array.isArray(check.reasons)) result.push(...check.reasons);
    if (Array.isArray(check.issues)) {
      check.issues.forEach((issue) => {
        const reason = objectOf(issue).reason;
        if (reason) result.push(reason);
      });
    }
    return result;
  }


  function manualReasonForCheck(value) {
    let reason = cleanText(value);
    const emptySentences = ["人工核验项还没有确认", "人工核验项还没有确认。", "人工核验项被标记为阻断", "人工核验项被标记为阻断。"];
    const prefixes = ["人工核验项还没有确认：", "人工核验项还没有确认:", "人工核验项被标记为阻断：", "人工核验项被标记为阻断:"];
    let changed = true;
    while (changed) {
      if (emptySentences.includes(reason)) return "";
      changed = false;
      prefixes.forEach((prefix) => {
        if (reason.indexOf(prefix) === 0) {
          reason = cleanText(reason.slice(prefix.length));
          changed = true;
        }
      });
    }
    if (emptySentences.includes(reason)) return "";
    return looksLikeValidationReason(reason) ? "" : reason;
  }


  function looksLikeValidationReason(reason) {
    if (!reason) return false;
    const markers = ["还没有绑定到真实表头", "还没有映射到订单原值", "发布前预览缺少", "缺少代表性测试数据"];
    if (markers.some((marker) => reason.includes(marker))) return true;
    const pairs = [
      ["槽位内容来源", "真实表头"],
      ["订单字段", "真实表头"],
      ["颜色扫描值", "还没有"],
      ["素材范围", "还没有"],
      ["最终边界", "还没有"],
      ["最终边界", "不允许"],
      ["同一作用域", "重复"],
      ["同一作用域", "不允许"]
    ];
    return pairs.some(([left, right]) => reason.includes(left) && reason.includes(right));
  }


  function compactReasons(reasons) {
    const items = unique((Array.isArray(reasons) ? reasons : []).map((item) => cleanText(item))).filter(Boolean);
    if (!items.length) return "";
    const visible = items.slice(0, 3);
    const suffix = items.length > visible.length ? `；另有 ${items.length - visible.length} 项` : "";
    return trimLongReason(visible.join("；") + suffix);
  }


  function trimLongReason(text) {
    const value = cleanText(text);
    return value.length > 180 ? `${value.slice(0, 177)}…` : value;
  }


  function updateBlockers(validation) {
    const target = $("blockerList");
    const checks = normalizeChecks(validation && validation.checks ? validation.checks : configChecks());
    const blockers = [];
    CHECK_KEYS.forEach((key) => {
      if (checks[key].status !== "confirmed") blockers.push(`${CHECK_LABELS[key]}：${checks[key].displayReason || checks[key].reason || STATUS_LABELS[checks[key].status]}`);
    });
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
    setText("publishBlockerText", ready ? "核验已完成，发布接口未接入。" : blockerSummary(blockers));
  }


  function blockerSummary(blockers) {
    const items = unique(Array.isArray(blockers) ? blockers : []);
    if (!items.length) return "请先完成草稿配置与人工核验。";
    const labels = items.map((item) => cleanText(item).split("：")[0]).filter(Boolean);
    const visible = labels.slice(0, 4).join("、");
    const suffix = labels.length > 4 ? "等" : "";
    return `还有 ${labels.length} 项发布核验未完成：${visible}${suffix}。`;
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
    renderTables,
    renderOutputRows,
    renderFieldBindingRows,
    renderOptionMappingRows,
    optionMappingRow,
    updateToggleButtons,
    updateCheckRail,
    normalizeChecks,
    compactReasons,
    updateBlockers,
    setDraftStatus,
    showTransientStatus
  });
})();
