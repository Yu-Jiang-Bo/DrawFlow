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


  function validationDisplayReason(value, fallback) {
    const issue = objectOf(value);
    const mapped = validationReasonForCode(cleanText(issue.code));
    if (mapped) return mapped;
    const raw = cleanText(issue.reason || (typeof value === "string" ? value : ""));
    const safeFallback = hasTechnicalValidationDetail(fallback) ? "" : cleanText(fallback);
    if (!raw) return safeFallback || (fallback === undefined ? "\u8bf7\u68c0\u67e5\u6807\u7ea2\u7684\u8bbe\u7f6e\u3002" : "");
    if (!hasTechnicalValidationDetail(raw)) return raw;
    return safeFallback || "\u8bf7\u68c0\u67e5\u6807\u7ea2\u7684\u8bbe\u7f6e\u3002";
  }


  function validationReasonForCode(code) {
    const reasons = {
      duplicate_name: "\u540c\u4e00\u8303\u56f4\u5185\u5b58\u5728\u91cd\u590d\u540d\u79f0\uff0c\u8bf7\u4fee\u6539\u6807\u7ea2\u7684\u9879\u76ee\u540e\u91cd\u8bd5\u3002",
      duplicate_path: "\u540c\u4e00\u8303\u56f4\u5185\u5b58\u5728\u91cd\u590d\u540d\u79f0\uff0c\u8bf7\u4fee\u6539\u6807\u7ea2\u7684\u9879\u76ee\u540e\u91cd\u8bd5\u3002",
      output_key: "\u540c\u4e00\u8303\u56f4\u5185\u5b58\u5728\u91cd\u590d\u540d\u79f0\uff0c\u8bf7\u4fee\u6539\u6807\u7ea2\u7684\u9879\u76ee\u540e\u91cd\u8bd5\u3002",
      anchor_belongs_to_slot: "\u5b9a\u4f4d\u6846\u5fc5\u987b\u4e0e\u5f53\u524d\u69fd\u4f4d\u5bf9\u5e94\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u672c\u69fd\u4f4d\u7684\u5b9a\u4f4d\u6846\u3002",
      tail_belongs_to_slot: "\u5c3e\u5df4\u6837\u672c\u5fc5\u987b\u4e0e\u5f53\u524d\u69fd\u4f4d\u5bf9\u5e94\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u672c\u69fd\u4f4d\u7684\u5c3e\u5df4\u6837\u672c\u3002",
      asset_slot_mismatch: "\u7d20\u6750\u5e93\u4e0e\u5f53\u524d\u7d20\u6750\u69fd\u4f4d\u5fc5\u987b\u76f8\u4e92\u5bf9\u5e94\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u3002",
      asset_missing: "\u5f53\u524d\u7d20\u6750\u69fd\u4f4d\u5f15\u7528\u7684\u7d20\u6750\u5e93\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u3002",
      asset_slot_missing: "\u7d20\u6750\u5e93\u7f3a\u5c11\u5bf9\u5e94\u7684\u7d20\u6750\u69fd\u4f4d\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u3002",
      tail_sample_missing: "\u5c3e\u5df4\u6587\u5b57\u9700\u8981\u63d0\u4f9b\u5c3e\u5df4\u6837\u672c\uff0c\u8bf7\u68c0\u67e5\u6807\u7ea2\u7684\u69fd\u4f4d\u3002",
      tail_glyph_coverage_missing: "\u5c3e\u5df4\u6837\u672c\u9700\u8981\u53ef\u786e\u8ba4\u7684\u9996\u5b57\u6216\u5c3e\u5b57\u8986\u76d6\u8bc1\u636e\u3002",
      option_preset_invalid: "\u7d20\u6750\u66ff\u6362\u4ec5\u7528\u4e8e\u7d20\u6750\u69fd\u4f4d\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u5904\u7406\u65b9\u5f0f\u3002",
      direct_text_slot_preset_invalid: "\u76f4\u63a5\u5355\u69fd\u66ff\u6362\u53ea\u80fd\u4f7f\u7528\u66ff\u6362\u6587\u672c\u69fd\u4f4d\u3002",
      split_by_pipe_slot_preset_invalid: "\u6309 | \u987a\u5e8f\u62c6\u5206\u53ea\u80fd\u4f7f\u7528\u66ff\u6362\u6587\u672c\u69fd\u4f4d\u3002",
      path_text_requires_scanned_slot: "\u8def\u5f84\u6587\u5b57\u4fdd\u7559\u9700\u8981\u5305\u542b\u4e00\u4e2a\u5df2\u8bc6\u522b\u7684\u8def\u5f84\u6587\u5b57\u69fd\u4f4d\u3002"
    };
    return reasons[code] || "";
  }


  function hasTechnicalValidationDetail(value) {
    const text = cleanText(value);
    if (!text) return false;
    if (typeof containsSensitive === "function" && containsSensitive(text)) return true;
    return /(?:\$\.[A-Za-z_][\w.[\]]*|(?:^|[\s\uff1b\uff1a])Template\/|(?:\u56fe\u5c42|\u914d\u7f6e|\u78c1\u76d8|\u6587\u4ef6)\s*\u8def\u5f84|\b(?:layer|json|object|file)[_-]?path\b|\b(?:JSON|J\u0053X|COM|Traceback|stack|schema|contract)\b|\b(?:tail|slot|anchor|asset)_[A-Za-z0-9_]*\b|\b(?:asset_replace|direct_text|split_by_pipe|path_text|tail_text|mixed_slots)\b|\bOutput_(?:main|Side[A-Z])\b)/i.test(text);
  }

  function validationReasonsForCheck(check) {
    const result = [];
    if (Array.isArray(check.reasons)) result.push(...check.reasons.map((reason) => validationDisplayReason(reason, "")));
    if (Array.isArray(check.issues)) {
      check.issues.forEach((issue) => {
        const reason = objectOf(issue).reason;
        if (reason) result.push(validationDisplayReason(issue, ""));
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
    return looksLikeValidationReason(reason) ? "" : validationDisplayReason(reason, "");
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


  function blockedValidationIssues(validation) {
    const issues = Array.isArray(objectOf(validation).issues) ? objectOf(validation).issues : [];
    return issues.map((item) => objectOf(item)).filter((item) => safeStatus(item.status) === "blocked");
  }


  function validationCheckForIssue(issue) {
    const check = cleanText(objectOf(issue).check);
    return CHECK_KEYS.includes(check) ? check : "output";
  }


  function validationConfig() {
    const latest = objectOf(state.lastValidatedConfig);
    if (Array.isArray(latest.outputs)) return latest;
    return objectOf(state.draft && state.draft.config);
  }


  function validationOutputConfig(index) {
    const outputs = Array.isArray(validationConfig().outputs) ? validationConfig().outputs : [];
    return objectOf(outputs[Number(index)]);
  }


  function validationOutputKey(index) {
    const output = validationOutputConfig(index);
    const raw = cleanText(output.key || output.name);
    return raw || (Number(index) ? `Output_Side${String.fromCharCode(65 + Number(index))}` : "Output_main");
  }


  function validationOptionConfig(outputIndex, group, optionIndex) {
    const section = objectOf(validationOutputConfig(outputIndex)[group]);
    const options = Array.isArray(section.options) ? section.options : [];
    return objectOf(options[Number(optionIndex)]);
  }


  function validationOptionTarget(outputIndex, group, optionIndex) {
    const option = validationOptionConfig(outputIndex, group, optionIndex);
    const raw = cleanText(option.key || option.name || option.label);
    return {
      outputIndex: Number(outputIndex),
      outputKey: validationOutputKey(outputIndex),
      group,
      optionIndex: Number(optionIndex),
      optionKey: safeOptionKey(raw, group) || raw
    };
  }


  function validationTargetForIssue(issue) {
    const path = cleanText(objectOf(issue).path);
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
    if (path.startsWith("$.colors")) return { stage: "rules", kind: "area", areaId: "colorRuleRows" };
    if (path.startsWith("$.preview")) return { stage: "preview", kind: "area", areaId: "previewValidationRows" };
    if (path === "$.outputs") return { stage: "structure", kind: "area", areaId: "outputConfigRows" };

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

    const optionMatch = suffix.match(/^\.(style|design|font)\.options\[(\d+)\](.*)$/);
    if (!optionMatch) return { stage: "structure", kind: "output", index: outputIndex, field: "" };
    const group = optionMatch[1];
    const optionIndex = Number(optionMatch[2]);
    const optionSuffix = optionMatch[3] || "";
    const optionTarget = validationOptionTarget(outputIndex, group, optionIndex);

    if (group === "style") {
      const fields = {
        ".dimensions.width_mm": "style-width-mm",
        ".dimensions.height_mm": "style-height-mm"
      };
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
    if (optionSuffix === ".content_preset") return { ...optionTarget, stage: "rules", kind: "option-preset" };
    return { ...optionTarget, stage: "rules", kind: "option" };
  }


  function formRows(containerId, className) {
    return Array.from(document.querySelectorAll(`#${containerId} .${className}`));
  }


  function nodeTarget(row, field) {
    if (!row) return null;
    return { row, control: field ? row.querySelector(`[data-field="${field}"]`) : null };
  }


  function optionIdentityMatches(node, target) {
    return Boolean(node && node.dataset.output === target.outputKey && node.dataset.group === target.group && node.dataset.option === target.optionKey);
  }


  function currentRuleSelectionMatches(target) {
    if (typeof filteredRuleOptions !== "function") return false;
    const item = filteredRuleOptions()[state.optionRules.selectedIndex];
    return Boolean(item && item.output === target.outputKey && item.group === target.group && item.key === target.optionKey);
  }


  function contentOptionGroupFor(target) {
    return formRows("contentOptionRows", "content-option-group").find((row) => optionIdentityMatches(row, target)) || null;
  }


  function locateValidationTarget(target) {
    if (!target) return null;
    if (target.kind === "basic") return { row: null, control: $(target.controlId) };
    if (target.kind === "output") {
      return nodeTarget(formRows("outputConfigRows", "output-row")[target.index] || $("outputConfigRows"), target.field);
    }
    if (target.kind === "binding") {
      const row = formRows("fieldBindingRows", "field-binding-row").find((item) => rowValue(item, "binding-field") === target.fieldKey);
      return nodeTarget(row || $("fieldBindingRows"), "binding-column");
    }
    if (target.kind === "mapping") {
      return nodeTarget(formRows("optionMappingRows", "option-mapping-row")[target.index] || $("optionMappingRows"), target.field);
    }
    if (target.kind === "style") {
      const row = formRows("styleDimensionRows", "style-dimension-row").find((item) => (
        item.dataset.output === target.outputKey && item.dataset.styleKey === target.optionKey
      ));
      return nodeTarget(row || $("styleDimensionRows"), target.field);
    }
    if (target.kind === "slot") {
      const rows = formRows("contentOptionRows", "content-slot-row").filter((row) => optionIdentityMatches(row, target));
      return nodeTarget(rows[target.slotIndex] || contentOptionGroupFor(target) || $("contentOptionRows"), target.field);
    }
    if (target.kind === "option-preset") {
      if (state.stage === "rules" && currentRuleSelectionMatches(target)) return { row: null, control: $("optionContentPreset") };
      return nodeTarget(contentOptionGroupFor(target) || $("contentOptionRows"), "");
    }
    if (target.kind === "option") {
      const button = formRows("optionRuleList", "option-rule-item").find((item) => optionIdentityMatches(item, target));
      if (button) return { row: null, control: button };
      return nodeTarget(contentOptionGroupFor(target) || $("contentOptionRows"), "");
    }
    if (target.kind === "area") return nodeTarget($(target.areaId), "");
    return null;
  }


  function clearValidationHighlights() {
    document.querySelectorAll(".v2-validation-control-error, .v2-validation-row-error").forEach((node) => {
      const hasOriginalTitle = Object.prototype.hasOwnProperty.call(node.dataset, "validationOriginalTitle");
      if (hasOriginalTitle) {
        const originalTitle = node.dataset.validationOriginalTitle;
        if (originalTitle) node.setAttribute("title", originalTitle);
        else node.removeAttribute("title");
        delete node.dataset.validationOriginalTitle;
      }
      node.removeAttribute("aria-invalid");
      node.classList.remove("v2-validation-control-error", "v2-validation-row-error");
    });
  }


  function markValidationTarget(issue) {
    const target = validationTargetForIssue(issue);
    const located = locateValidationTarget(target);
    const node = located && (located.control || located.row);
    if (!node) return target;
    if (!Object.prototype.hasOwnProperty.call(node.dataset, "validationOriginalTitle")) {
      node.dataset.validationOriginalTitle = node.getAttribute("title") || "";
    }
    node.setAttribute("title", validationDisplayReason(issue));
    node.setAttribute("aria-invalid", "true");
    node.classList.add(located.control ? "v2-validation-control-error" : "v2-validation-row-error");
    return target;
  }


  function syncValidationHighlights(validation) {
    clearValidationHighlights();
    blockedValidationIssues(validation).forEach((issue) => markValidationTarget(issue));
  }


  function prepareValidationTarget(target) {
    if (!target || target.stage !== "rules" || !target.optionKey || typeof ruleOptionItems !== "function") return false;
    const items = ruleOptionItems();
    const index = items.findIndex((item) => item.output === target.outputKey && item.group === target.group && item.key === target.optionKey);
    if (index < 0) return false;
    const changed = state.optionRules.pendingOnly || state.optionRules.selectedIndex !== index || Boolean(valueOf("optionRuleSearch"));
    state.optionRules.pendingOnly = false;
    state.optionRules.selectedIndex = index;
    if (valueOf("optionRuleSearch")) setValue("optionRuleSearch", "");
    return changed;
  }


  function focusValidationIssue(issue) {
    const target = validationTargetForIssue(issue);
    if (!target) return;
    const refreshRules = prepareValidationTarget(target);
    if (state.stage !== target.stage && typeof setWorkbenchStage === "function") {
      setWorkbenchStage(target.stage);
    } else if (refreshRules && target.stage === "rules" && typeof setWorkbenchStage === "function") {
      setWorkbenchStage(target.stage);
    }
    const located = locateValidationTarget(target);
    const node = located && (located.control || located.row);
    if (!node) return;

    markValidationTarget(issue);
    if (typeof node.scrollIntoView === "function") node.scrollIntoView({ block: "center", behavior: "smooth" });
    if (typeof node.focus === "function") node.focus({ preventScroll: true });
  }

  function clearValidationFeedback(message) {
    clearValidationHighlights();
    const target = $("blockerList");
    if (target) target.replaceChildren();
    setDisabled("publishVersionBtn", true);
    setText("publishBlockerText", message || "\u8bf7\u5148\u5b8c\u6210\u8349\u7a3f\u914d\u7f6e\u4e0e\u4eba\u5de5\u6838\u9a8c\u3002");
  }


  function blockerEntries(validation, checks) {
    const entries = [];
    const representedChecks = new Set();
    const seen = new Set();
    blockedValidationIssues(validation).forEach((issue) => {
      const check = validationCheckForIssue(issue);
      const reason = validationDisplayReason(issue, checks[check].displayReason || checks[check].reason || "请检查标红的设置。");
      const key = `${check}:${cleanText(issue.path)}:${reason}`;
      representedChecks.add(check);
      if (seen.has(key)) return;
      seen.add(key);
      entries.push({ text: `${CHECK_LABELS[check]}：${reason}`, issue, target: validationTargetForIssue(issue) });
    });
    CHECK_KEYS.forEach((key) => {
      if (checks[key].status === "confirmed" || representedChecks.has(key)) return;
      const text = `${CHECK_LABELS[key]}：${checks[key].displayReason || checks[key].reason || STATUS_LABELS[checks[key].status]}`;
      if (!seen.has(text)) {
        seen.add(text);
        entries.push({ text, issue: null, target: null });
      }
    });
    return entries;
  }


  function updateBlockers(validation) {
    const target = $("blockerList");
    const checks = normalizeChecks(validation && validation.checks ? validation.checks : configChecks());
    syncValidationHighlights(validation);
    const entries = blockerEntries(validation, checks);
    const blockers = entries.map((entry) => entry.text);
    if (target) {
      target.replaceChildren();
      (entries.length ? entries : [{ text: "已完成核验，可进入下一步。", issue: null, target: null }]).forEach((entry) => {
        const item = document.createElement("li");
        const text = document.createElement("span");
        text.textContent = entry.text;
        item.appendChild(text);
        if (entry.issue && entry.target) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "blocker-jump";
          button.textContent = "前往修改";
          button.addEventListener("click", () => focusValidationIssue(entry.issue));
          item.appendChild(button);
        }
        target.appendChild(item);
      });
    }
    const ready = validation && validation.can_publish === true && !entries.length;
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
    validationTargetForIssue,
    syncValidationHighlights,
    focusValidationIssue,
    clearValidationFeedback,
    validationDisplayReason,
    setDraftStatus,
    hasTechnicalValidationDetail,
    showTransientStatus
  });
})();
