(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

  function scanModel(scan, config) {
    const cfg = objectOf(config);
    if (hasStructuredV2Outputs(scan)) return structuredV2ScanModel(scan, cfg);
    const outputs = normalizeItems([...(Array.isArray(cfg.outputs) ? cfg.outputs : []), ...collectDeep(scan, ["outputs", "output"])]);
    return {
      outputs: outputs.length ? outputs : normalizeItems(collectDeep(scan, ["artboards", "pages"])),
      designs: normalizeItems(collectDeep(scan, ["designs", "design_options"])),
      fonts: normalizeItems(collectDeep(scan, ["fonts", "font_options"])),
      styles: normalizeItems(collectDeep(scan, ["styles", "style_options", "dimensions"])),
      assets: normalizeItems(collectDeep(scan, ["assets", "files", "placed_items"])),
      colors: normalizeItems([...(Array.isArray(cfg.colors) ? cfg.colors : []), ...collectDeep(scan, ["colors", "swatches"])]),
      slots: normalizeItems(collectDeep(scan, ["slots", "text_slots", "variables", "items"])),
      anchors: normalizeItems(collectDeep(scan, ["anchors", "anchor"])),
      tails: normalizeItems(collectDeep(scan, ["tails", "tail"])),
      fixedObjects: normalizeItems(collectDeep(scan, ["fixed_objects", "fixedobjects", "static_objects", "unmanaged_objects"]))
    };
  }

  function structuredV2ScanModel(scan, config) {
    const scanOutputs = topLevelArray(scan, "outputs");
    const outputItems = mergeItemsByIdentity([...scanOutputs, ...topLevelArray(config, "outputs")]);
    const styleOptions = mergeItemsByIdentity(outputSectionOptions(scanOutputs, "style"));
    const designOptions = mergeItemsByIdentity(outputSectionOptions(scanOutputs, "design"));
    const fontOptions = mergeItemsByIdentity(outputSectionOptions(scanOutputs, "font"));
    const contentOptions = [...designOptions, ...fontOptions];
    return {
      outputs: normalizeItems(outputItems),
      designs: normalizeItems(designOptions),
      fonts: normalizeItems(fontOptions),
      styles: normalizeItems(styleOptions),
      assets: normalizeItems(mergeItemsByIdentity(optionChildren(designOptions, "assets"))),
      colors: normalizeItems(mergeItemsByIdentity([...topLevelArray(config, "colors"), ...topLevelArray(scan, "colors")])),
      slots: normalizeItems(mergeItemsByIdentity(optionChildren(contentOptions, "slots"))),
      anchors: normalizeItems(mergeItemsByIdentity(optionChildren(contentOptions, "anchors"))),
      tails: normalizeItems(mergeItemsByIdentity(optionChildren(contentOptions, "tails"))),
      fixedObjects: normalizeItems(mergeItemsByIdentity(fixedObjectItems(contentOptions)))
    };
  }

  function hasStructuredV2Outputs(scan) {
    return topLevelArray(scan, "outputs").some((output) => {
      const item = objectOf(output);
      return ["style", "design", "font"].some((group) => Array.isArray(objectOf(item[group]).options))
        || ["styles", "designs", "fonts"].some((key) => Array.isArray(item[key]))
        || isPlainObject(item.summary);
    });
  }

  function topLevelArray(source, key) {
    const value = objectOf(source)[key];
    return Array.isArray(value) ? value : [];
  }

  function outputSectionOptions(outputs, group) {
    return outputs.flatMap((output, outputIndex) => {
      const outputKey = cleanText(output.key || output.name || (outputIndex ? "" : "Output_main"));
      const section = objectOf(output[group]);
      const direct = Array.isArray(section.options) ? section.options : [];
      const alias = Array.isArray(output[`${group}s`]) ? output[`${group}s`] : [];
      const options = direct.length ? direct : alias;
      return options.map((option) => tagScanItem(option, { output: outputKey, group }));
    });
  }

  function optionChildren(options, key) {
    return options.flatMap((option) => {
      const optionKey = cleanText(option.key || option.name || "");
      const children = Array.isArray(option[key]) ? option[key] : [];
      return children.map((child) => tagScanItem(child, {
        output: cleanText(option.output || ""),
        group: cleanText(option.group || ""),
        option: optionKey
      }));
    });
  }

  function fixedObjectItems(options) {
    return options.flatMap((option) => {
      const explicit = Array.isArray(option.fixed_objects) ? option.fixed_objects : [];
      if (explicit.length) {
        return explicit.map((child) => tagScanItem(child, {
          output: cleanText(option.output || ""),
          group: cleanText(option.group || ""),
          option: cleanText(option.key || option.name || "")
        }));
      }
      const count = Number(option.fixed_object_count || 0);
      if (!Number.isFinite(count) || count <= 0) return [];
      return [tagScanItem({
        key: "unnamed_fixed_objects",
        count,
        path: option.path || ""
      }, {
        output: cleanText(option.output || ""),
        group: cleanText(option.group || ""),
        option: cleanText(option.key || option.name || "")
      })];
    });
  }

  function tagScanItem(item, tags) {
    if (item && typeof item === "object") return { ...item, ...tags };
    return { name: String(item || ""), ...tags };
  }

  function mergeItemsByIdentity(items) {
    const seen = new Set();
    const result = [];
    items.forEach((item, index) => {
      const data = item && typeof item === "object" ? item : { name: String(item || "") };
      const identity = itemIdentity(data, index);
      if (seen.has(identity)) return;
      seen.add(identity);
      result.push(item);
    });
    return result;
  }

  function itemIdentity(item, index) {
    return [
      cleanText(item.output || ""),
      cleanText(item.group || ""),
      cleanText(item.option || ""),
      cleanText(item.path || item.key || item.name || item.label || item.field || item.file_name || item.filename || `item-${index}`)
    ].join("\u0000").toLowerCase();
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
