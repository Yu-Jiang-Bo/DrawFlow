(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;

  function tableHeader(labels) {
    const row = tableRow("table-head");
    labels.forEach((label) => {
      const cell = document.createElement("div");
      cell.textContent = label;
      row.appendChild(cell);
    });
    return row;
  }

  function tableRow(className) {
    const row = document.createElement("div");
    row.className = `structured-row ${className}`;
    return row;
  }

  function inputCell(name, value) {
    const wrap = document.createElement("label");
    const input = document.createElement("input");
    input.dataset.field = name;
    input.value = value || "";
    input.addEventListener("input", () => {
      if (typeof globalThis.invalidateTrialResult === "function") globalThis.invalidateTrialResult("配置已修改，请重新试渲染。");
      globalThis.validateCurrentConfig(false);
    });
    wrap.appendChild(input);
    return wrap;
  }

  function selectCell(name, options, value) {
    const wrap = document.createElement("label");
    const select = document.createElement("select");
    select.dataset.field = name;
    options.forEach(([optionValue, label]) => {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = label;
      select.appendChild(option);
    });
    const selected = options.some(([optionValue]) => optionValue === value) ? value : options[0][0];
    select.value = selected;
    select.addEventListener("change", () => {
      if (typeof globalThis.invalidateTrialResult === "function") globalThis.invalidateTrialResult("配置已修改，请重新试渲染。");
      globalThis.validateCurrentConfig(false);
    });
    wrap.appendChild(select);
    return wrap;
  }

  function addRowButton(text, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-subtle row-add-button";
    button.textContent = text;
    button.addEventListener("click", (event) => {
      if (typeof globalThis.invalidateTrialResult === "function") globalThis.invalidateTrialResult("配置已修改，请重新试渲染。");
      handler(event);
    });
    return button;
  }

  function rowValue(row, name) {
    const el = row.querySelector(`[data-field="${name}"]`);
    return el ? el.value : "";
  }

  function lineNode(title, subtitle) {
    const wrap = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = title || "-";
    wrap.appendChild(strong);
    if (subtitle) wrap.appendChild(metaNode(subtitle));
    return wrap;
  }

  function metaNode(text) {
    const el = document.createElement("span");
    el.className = "muted";
    el.textContent = text || "";
    return el;
  }

  function emptyNode(text) {
    const el = document.createElement("div");
    el.className = "empty-state";
    el.textContent = text;
    return el;
  }


  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text == null ? "" : String(text);
  }


  function setValue(id, value) {
    const el = $(id);
    if (el) el.value = value == null ? "" : String(value);
  }


  function setHidden(id, hidden) {
    const el = $(id);
    if (el) el.hidden = Boolean(hidden);
  }


  function setDisabled(id, disabled) {
    const el = $(id);
    if (el) el.disabled = Boolean(disabled);
  }


  function valueOf(id) {
    const el = $(id);
    return el ? String(el.value || "") : "";
  }


  function fileOf(id) {
    const el = $(id);
    return el && el.files && el.files[0] ? el.files[0] : null;
  }


  function templateIdOf(item) {
    return String(item.template_id || objectOf(item.template).template_id || "");
  }


  function templateNameOf(item) {
    return String(item.name || objectOf(item.template).name || "");
  }


  function shopNameOf(item) {
    return String(item.shop_name || objectOf(item.template).shop_name || "");
  }


  function draftLabel(item) {
    return item.draft ? "有草稿" : "无草稿";
  }


  function publicationLabel(item) {
    const pub = objectOf(item.publication);
    return pub.current_version ? `已发布 ${pub.current_version}` : "未发布";
  }


  function upsertStateSummary(list, item) {
    const id = templateIdOf(item);
    const rest = list.filter((entry) => templateIdOf(entry) !== id);
    return [item, ...rest];
  }


  function safeOutputKey(value, fallback, index) {
    const text = cleanText(value);
    if (text === "Output_main" || /^Output_Side[A-Z]$/.test(text)) return text;
    return index ? fallback : "Output_main";
  }


  function safeOptionKey(value, group) {
    const text = cleanText(value);
    if (group === "style") {
      const match = text.match(/(?:style|Style)?\s*0*([1-9]\d*)$/);
      return match ? `style${Number(match[1])}` : "";
    }
    if (group === "design") {
      const match = text.match(/(?:Design)?\s*0*([1-9]\d*)$/i);
      return match ? `Design${String(Number(match[1])).padStart(2, "0")}` : "";
    }
    if (group === "font") {
      const match = text.match(/^F\s*([1-9]\d*)$/i);
      return match ? `F${Number(match[1])}` : "";
    }
    return safeIdentifier(text, "");
  }


  function displayOptionSource(target, group) {
    if (group === "design") return target.replace(/^Design0*/, "");
    return target;
  }


  function safeField(value) {
    const text = safeIdentifier(value, "");
    return /^[A-Za-z][A-Za-z0-9_]*$/.test(text) ? text : "";
  }


  function safeIdentifier(value, fallback) {
    const text = cleanText(value).replace(/[^A-Za-z0-9_ -]/g, "").replace(/[\s-]+/g, "_").replace(/^_+|_+$/g, "");
    return text || fallback || "";
  }


  function cleanText(value) {
    return String(value == null ? "" : value).trim();
  }


  function safeStatus(value) {
    if (value === "passed") return "confirmed";
    return ["confirmed", "pending", "blocked"].includes(value) ? value : "pending";
  }

  function objectOf(value) {
    return isPlainObject(value) ? value : {};
  }


  function isPlainObject(value) {
    return Boolean(value && typeof value === "object" && !Array.isArray(value));
  }


  function parseJson(text) {
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (_) {
      return {};
    }
  }


  function unique(items) {
    return Array.from(new Set(items.filter((item) => item !== "" && item !== null && item !== undefined)));
  }


  function isFiniteNumber(value) {
    return Number.isFinite(Number(value));
  }


  function isAiFile(file) {
    return Boolean(file && /\.ai$/i.test(file.name || ""));
  }


  function safeFileName(name) {
    return cleanText(name).replace(/[\\/]/g, "");
  }


  function isAbort(error) {
    return Boolean(error && (error.name === "AbortError" || /abort/i.test(error.message || "")));
  }


  Object.assign(globalThis, {
    tableHeader,
    tableRow,
    inputCell,
    selectCell,
    addRowButton,
    rowValue,
    lineNode,
    metaNode,
    emptyNode,
    setText,
    setValue,
    setHidden,
    setDisabled,
    valueOf,
    fileOf,
    templateIdOf,
    templateNameOf,
    shopNameOf,
    draftLabel,
    publicationLabel,
    upsertStateSummary,
    safeOutputKey,
    safeOptionKey,
    displayOptionSource,
    safeField,
    safeIdentifier,
    cleanText,
    safeStatus,
    objectOf,
    isPlainObject,
    parseJson,
    unique,
    isFiniteNumber,
    isAiFile,
    safeFileName,
    isAbort
  });
})();
