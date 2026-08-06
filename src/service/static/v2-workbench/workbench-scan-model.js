(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function scanModel(scan, config) {
    const cfg = objectOf(config);
    const outputs = normalizeItems([...(Array.isArray(cfg.outputs) ? cfg.outputs : []), ...collectDeep(scan, ["outputs", "output"])]);
    return {
      outputs: outputs.length ? outputs : normalizeItems(collectDeep(scan, ["artboards", "pages"])),
      designs: normalizeItems([...collectDeep(scan, ["designs", "design_options"]), ...groupOptions(cfg, "design")]),
      fonts: normalizeItems([...collectDeep(scan, ["fonts", "font_options"]), ...groupOptions(cfg, "font")]),
      styles: normalizeItems([...collectDeep(scan, ["styles", "style_options", "dimensions"]), ...groupOptions(cfg, "style")]),
      assets: normalizeItems(collectDeep(scan, ["assets", "files", "placed_items"])),
      colors: normalizeItems([...(Array.isArray(cfg.colors) ? cfg.colors : []), ...collectDeep(scan, ["colors", "swatches"])]),
      slots: normalizeItems(collectDeep(scan, ["slots", "text_slots", "variables", "items"])),
      anchors: normalizeItems(collectDeep(scan, ["anchors", "anchor"])),
      tails: normalizeItems(collectDeep(scan, ["tails", "tail"])),
      fixedObjects: normalizeItems(collectDeep(scan, ["fixed_objects", "fixedobjects", "static_objects", "unmanaged_objects"]))
    };
  }



  function groupOptions(config, group) {
    return (Array.isArray(config.outputs) ? config.outputs : []).flatMap((output) => {
      const section = objectOf(output[group]);
      const outputKey = cleanText(output.key || output.name || "");
      return Array.isArray(section.options) ? section.options.map((option) => {
        if (option && typeof option === "object") return { ...option, output: outputKey };
        return { name: String(option || ""), output: outputKey };
      }) : [];
    });
  }



  function collectDeep(source, keys) {
    const found = [];
    const seen = new Set();
    walk(source, (value, key) => {
      const normalized = String(key || "").toLowerCase();
      if (!keys.includes(normalized)) return;
      if (Array.isArray(value)) found.push(...value);
      else if (isPlainObject(value)) {
        Object.keys(value).forEach((name) => found.push({ key: name, ...objectOf(value[name]) }));
      }
    }, seen);
    return found;
  }



  function walk(value, visit, seen) {
    if (!value || typeof value !== "object" || seen.has(value)) return;
    seen.add(value);
    Object.keys(value).forEach((key) => {
      const child = value[key];
      visit(child, key);
      if (typeof child === "object") walk(child, visit, seen);
    });
  }



  function normalizeItems(items) {
    return items.filter((item) => item !== null && item !== undefined).map((item, index) => {
      if (typeof item === "string" || typeof item === "number") return { name: String(item), count: 0 };
      const data = objectOf(item);
      const name = cleanText(data.key || data.name || data.label || data.display_name || data.field || data.file_name || data.filename || `项目 ${index + 1}`);
      return { ...data, name, count: summaryCount(data) };
    });
  }



  function filterItems(items, search) {
    if (!search) return items;
    return items.filter((item) => JSON.stringify(item).toLowerCase().includes(search));
  }



  function visibleSectionItems(key, items, searching) {
    if (searching) return items;
    if (key === "designs" && !state.expanded.designs) return items.slice(0, 3);
    if (key === "fonts" && !state.expanded.fonts) return items.slice(0, 3);
    return items;
  }



  function modelHasItems(model) {
    return Object.keys(model).some((key) => model[key].length);
  }



  function sectionTitle(key, count) {
    const labels = {
      outputs: "输出",
      designs: "设计",
      fonts: "字体",
      styles: "样式",
      assets: "资产",
      colors: "颜色",
      slots: "槽位",
      anchors: "定位框",
      tails: "尾巴样本",
      fixedObjects: "固定对象汇总"
    };
    return `${labels[key] || key}（${count}）`;
  }



  function nodeTitle(item) {
    return `${item.name || item.key || "未命名"}${item.count ? ` · ${item.count} 项` : ""}`;
  }



  function nodeSummary(kind, item) {
    const parts = [`类型：${sectionTitle(kind, 1).replace(/（1）$/, "")}`, `名称：${item.name || item.key || "未命名"}`];
    if (item.count) parts.push(`包含：${item.count} 项`);
    ["field", "source_field", "preset", "content_preset", "file_name", "filename", "space"].forEach((key) => {
      if (item[key]) parts.push(`${key}：${cleanText(item[key])}`);
    });
    return parts.join("；");
  }



  function scanSummary(scan) {
    const model = scanModel(scan, state.draft && state.draft.config);
    return Object.keys(model).reduce((result, key) => {
      result[key] = model[key].length;
      result.total += model[key].length;
      return result;
    }, { total: 0 });
  }



  function summaryText(summary) {
    return `已识别输出 ${summary.outputs || 0}、设计 ${summary.designs || 0}、字体 ${summary.fonts || 0}、样式 ${summary.styles || 0}、槽位 ${summary.slots || 0}、定位框 ${summary.anchors || 0}、尾巴样本 ${summary.tails || 0}、资产 ${summary.assets || 0}、固定对象 ${summary.fixedObjects || 0}。`;
  }



  function draftSummaryText(summary) {
    const basics = formBasics();
    return basics.template_id ? `${basics.template_id} · ${basics.name || "未命名"} · ${summaryText(summary)}` : "尚未选择模板。";
  }



  function summaryCount(value) {
    if (Array.isArray(value)) return value.length;
    if (!isPlainObject(value)) return 0;
    return Object.keys(value).reduce((total, key) => {
      const child = value[key];
      if (Array.isArray(child)) return total + child.length;
      if (isPlainObject(child)) return total + Object.keys(child).length;
      return total;
    }, 0);
  }





  Object.assign(globalThis, {
    scanModel,
    groupOptions,
    collectDeep,
    walk,
    normalizeItems,
    filterItems,
    visibleSectionItems,
    modelHasItems,
    sectionTitle,
    nodeTitle,
    nodeSummary,
    scanSummary,
    summaryText,
    draftSummaryText,
    summaryCount
  });
})();
