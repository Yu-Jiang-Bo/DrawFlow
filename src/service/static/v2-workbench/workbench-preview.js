(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function renderPreviewStage() {
    state.previewSampleValues = { ...objectOf(state.previewSampleValues), ...collectPreviewSampleRow() };
    renderPreviewSampleRows();
    renderPreviewOutputs();
    renderPreviewValidationRows();
    renderVersionSummary();
    updatePreviewActionButtons();
  }

  function renderPreviewSampleRows() {
    const target = $("previewSampleRows");
    if (!target) return;
    const fields = previewFieldDescriptors();
    if (!fields.length) {
      target.replaceChildren(emptyNode("当前模板还没有可用于试渲染的订单字段，请先完成字段绑定。"));
      return;
    }
    target.replaceChildren(...fields.map((field) => {
      const node = document.createElement("label");
      node.className = "preview-sample-cell";
      const span = document.createElement("span");
      const input = document.createElement("input");
      span.textContent = field.header;
      input.type = "text";
      input.value = previewValueFor(field);
      input.dataset.sampleHeader = field.header;
      input.setAttribute("autocomplete", "off");
      input.addEventListener("input", () => {
        state.previewSampleValues[field.header] = input.value;
        invalidateTrialResult("样例数据已修改，请使用当前数据重新试渲染。");
      });
      node.append(span, input);
      return node;
    }));
  }

  function previewFieldDescriptors() {
    const config = objectOf(state.draft && state.draft.config);
    const bindings = objectOf(config.field_bindings);
    const fields = [];
    const byHeader = {};
    const add = (logicalField) => {
      const logical = cleanText(logicalField);
      const header = cleanText(bindings[logical]);
      if (!logical || !header) return;
      const identity = header.toLocaleLowerCase();
      if (!byHeader[identity]) {
        byHeader[identity] = { header, logicalFields: [] };
        fields.push(byHeader[identity]);
      }
      if (!byHeader[identity].logicalFields.includes(logical)) byHeader[identity].logicalFields.push(logical);
    };
    (Array.isArray(config.outputs) ? config.outputs : []).forEach((outputValue) => {
      const output = objectOf(outputValue);
      ["style", "design", "font"].forEach((groupName) => {
        const group = objectOf(output[groupName]);
        const options = Array.isArray(group.options) ? group.options : [];
        if (options.length) add(group.field);
        options.forEach((optionValue) => {
          const option = objectOf(optionValue);
          (Array.isArray(option.slots) ? option.slots : []).forEach((slotValue) => {
            const slot = objectOf(slotValue);
            add(slot.source_field);
            if (Object.prototype.hasOwnProperty.call(bindings, cleanText(slot.color_binding))) add(slot.color_binding);
          });
        });
      });
    });
    (Array.isArray(config.option_mappings) ? config.option_mappings : []).forEach((mappingValue) => {
      const mapping = objectOf(mappingValue);
      if (cleanText(mapping.group) === "color") add(mapping.field);
    });
    return fields;
  }

  function previewValueFor(field) {
    const current = objectOf(state.previewSampleValues);
    if (Object.prototype.hasOwnProperty.call(current, field.header)) return String(current[field.header] == null ? "" : current[field.header]);
    const config = objectOf(state.draft && state.draft.config);
    const preview = objectOf(config.preview);
    const stored = Array.isArray(preview.sample_rows) ? objectOf(preview.sample_rows[0]) : {};
    if (Object.prototype.hasOwnProperty.call(stored, field.header)) return String(stored[field.header] == null ? "" : stored[field.header]);
    const mappings = Array.isArray(config.option_mappings) ? config.option_mappings : [];
    const suggested = mappings.find((mappingValue) => {
      const mapping = objectOf(mappingValue);
      return field.logicalFields.includes(cleanText(mapping.field)) && cleanText(mapping.source_value);
    });
    return suggested ? cleanText(suggested.source_value) : "";
  }

  function collectPreviewSampleRow() {
    const target = $("previewSampleRows");
    if (!target) return {};
    const row = {};
    const inputs = target.querySelectorAll
      ? Array.from(target.querySelectorAll("[data-sample-header]"))
      : previewSampleInputs(target);
    inputs.forEach((input) => {
      const header = cleanText(input.dataset.sampleHeader);
      if (header) row[header] = String(input.value == null ? "" : input.value);
    });
    return row;
  }

  function previewSampleInputs(root) {
    const result = [];
    (root.children || []).forEach((child) => {
      if (child.dataset && child.dataset.sampleHeader) result.push(child);
      result.push(...previewSampleInputs(child));
    });
    return result;
  }

  function renderPreviewOutputs() {
    const tabs = $("previewSideTabs");
    const pane = $("previewArtworkPane");
    if (!tabs || !pane) return;
    const outputs = trialOutputs();
    tabs.replaceChildren();
    tabs.hidden = outputs.length <= 1;
    pane.replaceChildren();
    if (!trialSucceeded()) {
      pane.appendChild(emptyNode(state.previewMessage || "尚未执行样例试渲染。"));
      renderPreviewWarnings([]);
      return;
    }
    if (!outputs.length) {
      pane.appendChild(emptyNode("试渲染已完成，但没有返回可展示的效果图。"));
      renderPreviewWarnings(trialWarnings());
      return;
    }
    const selectedIndex = Math.min(Math.max(Number(state.previewOutputIndex || 0), 0), outputs.length - 1);
    state.previewOutputIndex = selectedIndex;
    if (outputs.length > 1) {
      outputs.forEach((output, index) => tabs.appendChild(outputTab(output, index, selectedIndex)));
    }
    const output = outputs[selectedIndex];
    const previewUrl = cleanText(output.preview_url || output.image_url || output.url);
    if (outputs.length > 1) {
      const caption = document.createElement("strong");
      caption.className = "preview-output-caption";
      caption.textContent = outputLabel(output, selectedIndex);
      pane.appendChild(caption);
    }
    if (previewUrl) {
      const image = document.createElement("img");
      image.src = previewUrl;
      image.alt = outputs.length > 1 ? `${outputLabel(output, selectedIndex)}试渲染效果图` : "试渲染效果图";
      pane.appendChild(image);
    } else {
      pane.appendChild(emptyNode("本效果图没有返回可展示的预览，请重新试渲染。"));
    }
    renderPreviewWarnings([...trialWarnings(), ...warningMessages(output.warnings)]);
  }

  function outputTab(output, index, selectedIndex) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = index === selectedIndex ? "primary" : "";
    button.textContent = outputLabel(output, index);
    button.addEventListener("click", () => {
      state.previewOutputIndex = index;
      renderPreviewOutputs();
    });
    return button;
  }

  function trialOutputs() {
    const trial = objectOf(state.trial);
    return Array.isArray(trial.outputs) ? trial.outputs.map(objectOf) : [];
  }

  function trialSucceeded() {
    const status = cleanText(objectOf(state.trial).status).toLowerCase();
    return ["success", "succeeded", "completed", "passed"].includes(status);
  }

  function outputLabel(output, index) {
    return cleanText(output.display_name || output.label) || `效果图 ${Number(index) + 1}`;
  }

  function trialWarnings() {
    return warningMessages(objectOf(state.trial).warnings);
  }

  function warningMessages(value) {
    const items = Array.isArray(value) ? value : (value ? [value] : []);
    return items.map((item) => {
      const data = objectOf(item);
      const text = typeof item === "string" ? item : (data.message || data.reason || data.title);
      return sanitizeMessage(text, "试渲染返回一项需要检查的提示。");
    }).filter(Boolean);
  }

  function renderPreviewWarnings(messages) {
    const target = $("previewWarningList");
    if (!target) return;
    target.replaceChildren(...unique(messages || []).map((message) => {
      const node = document.createElement("div");
      node.className = "v2-warning-note";
      node.textContent = message;
      return node;
    }));
  }

  function renderPreviewValidationRows() {
    const target = $("previewValidationRows");
    if (!target) return;
    const checks = objectOf(objectOf(state.validation).checks);
    if (!state.trial) {
      target.replaceChildren(emptyNode("尚无真实试渲染核验结果。"));
      setStatusPill("previewValidationStatus", "未试渲染", "warn");
      return;
    }
    const keys = ctx.CHECK_KEYS.filter((key) => checks[key]);
    if (!keys.length) {
      target.replaceChildren(emptyNode("试渲染接口没有返回核验结果，请重新试渲染。"));
      setStatusPill("previewValidationStatus", "等待核验", "warn");
      return;
    }
    target.replaceChildren(...keys.map((key) => validationRow(key, checks[key])));
    const previewStatus = safeStatus(objectOf(checks.preview).status);
    setStatusPill("previewValidationStatus", ctx.STATUS_LABELS[previewStatus] || "待校验", ctx.STATUS_CLASS[previewStatus] || "warn");
  }

  function validationRow(key, value) {
    const check = objectOf(value);
    const status = safeStatus(check.status);
    const detail = status === "confirmed" ? "已通过" : sanitizeMessage(check.reason || "", "");
    const row = document.createElement("div");
    row.className = "preview-validation-row";
    row.append(
      lineNode(ctx.CHECK_LABELS[key] || "核验项", detail),
      statusPill(ctx.STATUS_LABELS[status] || "待校验", ctx.STATUS_CLASS[status] || "warn")
    );
    return row;
  }

  function setStatusPill(id, text, status) {
    const node = $(id);
    if (!node) return;
    node.className = `stage-status-pill ${status || ""}`.trim();
    node.textContent = text;
  }

  function updatePreviewActionButtons() {
    const busy = Boolean(state.isSavingDraft || state.isTrialRendering || state.isPublicationChecking || state.isPublishing);
    setDisabled("trialRenderBtn", !state.draft || busy);
    setDisabled("rerunTrialRenderBtn", !state.draft || busy);
    setText("trialRenderBtn", state.isTrialRendering ? "正在试渲染" : "使用当前样例试渲染");
    setText("rerunTrialRenderBtn", state.isTrialRendering ? "正在试渲染" : (state.trial ? "重新试渲染" : "使用当前数据试渲染"));
  }

  Object.assign(globalThis, {
    renderPreviewStage,
    collectPreviewSampleRow,
    renderPreviewOutputs,
    renderPreviewValidationRows,
    updatePreviewActionButtons,
    trialSucceeded
  });
})();
