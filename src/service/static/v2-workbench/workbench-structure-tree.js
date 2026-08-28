(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state } = ctx;

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
    if (hasStructuredTreeScan(scan)) {
      renderStructuredTree(target, scan, model, search);
      updateToggleButtons();
      return;
    }
    renderFlatStructureSections(target, model, search);
    updateToggleButtons();
  }


  function renderFlatStructureSections(target, model, search) {
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
  }


  function hasStructuredTreeScan(scan) {
    const outputs = Array.isArray(scan && scan.outputs) ? scan.outputs : [];
    return outputs.some((output) => {
      const item = objectOf(output);
      return ["style", "design", "font"].some((group) => Array.isArray(objectOf(item[group]).options))
        || ["styles", "designs", "fonts"].some((key) => Array.isArray(item[key]))
        || isPlainObject(item.summary);
    });
  }


  function renderStructuredTree(target, scan, model, search) {
    const root = document.createElement("section");
    root.className = "structure-tree-root";
    const totalVariables = (model.designs.length + model.fonts.length + model.styles.length + model.colors.length + model.slots.length + model.assets.length);
    const rootId = "Template";
    root.appendChild(treeRow("Template", `${totalVariables} 个变量`, 0, "template", "Template 根组", "", { nodeId: rootId, expandable: true, defaultExpanded: true }));
    const outputs = Array.isArray(scan.outputs) ? scan.outputs : [];
    if (search || treeExpanded(rootId, true)) {
      outputs.forEach((output, index) => appendOutputTree(root, output, index, model, search, rootId));
      appendColorsTree(root, model.colors, search, rootId);
    }
    target.appendChild(root);
    appendFixedObjectSummary(target, scan, model);
    if (!target.textContent.trim()) target.appendChild(emptyNode("没有匹配的结构项"));
  }


  function appendOutputTree(root, output, index, model, search, parentId) {
    const key = outputKeyForTree(output, index);
    const displayName = outputDisplayName(key);
    const outputId = `${parentId}/${key}`;
    const row = treeRow(key, displayName, 1, "output", nodeSummary("outputs", { key, name: key, display_name: displayName }), "", { nodeId: outputId, expandable: true, defaultExpanded: true });
    if (index === 0) row.classList.add("active");
    root.appendChild(row);
    if (!(search || treeExpanded(outputId, true))) return;
    appendTreeGroup(root, "Style", scopedTreeItems(key, model.styles), 2, search, "styles", outputId);
    appendTreeGroup(root, "Design", scopedTreeItems(key, model.designs), 2, search, "designs", outputId);
    appendTreeGroup(root, "Font", scopedTreeItems(key, model.fonts), 2, search, "fonts", outputId);
    appendOutputAssets(root, key, scopedTreeItems(key, model.assets), search);
  }


  function appendTreeGroup(root, label, items, depth, search, kind, parentId) {
    if (!items.length) return;
    const visible = filterItems(items, search);
    if (search && !visible.length) return;
    const groupId = `${parentId}/${kind}`;
    root.appendChild(treeRow(label, `${items.length} 项`, depth, "group", `${label}：${items.length} 项`, "", { nodeId: groupId, expandable: true, defaultExpanded: true }));
    const groupExpanded = search || treeExpanded(groupId, true);
    if (!groupExpanded) return;
    const expanded = search || !["designs", "fonts"].includes(kind) || state.expanded[kind === "designs" ? "designs" : "fonts"];
    const shown = expanded ? visible : visible.slice(0, 3);
    shown.forEach((item) => {
      const title = item.key || item.name || label;
      const slotSummary = optionSlotSummary(item);
      const optionId = `${groupId}/${title}`;
      const children = optionTreeChildren(item);
      root.appendChild(treeRow(title, slotSummary, depth + 1, kind, nodeSummary(kind, item), optionBadge(item), { nodeId: optionId, expandable: children.length > 0, defaultExpanded: Boolean(search) }));
      if (children.length && (search || treeExpanded(optionId, false))) {
        children.forEach((child) => root.appendChild(treeRow(child.title, child.meta, depth + 2, child.kind, child.summary)));
      }
    });
  }


  function appendOutputAssets(root, outputKey, assets, search) {
    const visible = filterItems(assets, search);
    if (search && !visible.length) return;
    visible.forEach((asset) => root.appendChild(treeRow(`Assets / ${asset.asset_key || asset.key || asset.name}`, supportedValuesText(asset), 2, "assets", nodeSummary("assets", asset))));
  }


  function appendColorsTree(root, colors, search, parentId) {
    const visible = filterItems(colors, search);
    if (!colors.length || (search && !visible.length)) return;
    const colorsId = `${parentId}/colors`;
    root.appendChild(treeRow("Colors", `${colors.length} 项`, 1, "colors", "Colors 色块", "", { nodeId: colorsId, expandable: true, defaultExpanded: true }));
    if (!(search || treeExpanded(colorsId, true))) return;
    (search ? visible : visible.slice(0, 4)).forEach((color) => root.appendChild(treeRow(color.key || color.name || "Color", color.space || "", 2, "colors", nodeSummary("colors", color))));
  }


  function appendFixedObjectSummary(target, scan, model) {
    const total = fixedObjectTotal(scan, model);
    if (!total) return;
    const summary = document.createElement("section");
    summary.className = "structure-fixed-summary";
    summary.append(lineNode("未命名固定对象", String(total)), metaNode("固定图案只计数，不展开显示"));
    target.appendChild(summary);
  }


  function treeRow(title, meta, depth, kind, summary, badge, options) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `structure-tree-row depth-${Math.min(depth, 4)}`;
    row.dataset.nodeKind = kind || "";
    const config = objectOf(options);
    if (config.nodeId) row.dataset.treeNodeId = config.nodeId;
    if (config.expandable) {
      row.classList.add("expandable");
      row.setAttribute("aria-expanded", String(treeExpanded(config.nodeId, config.defaultExpanded !== false)));
    }
    row.appendChild(lineNode(title, meta));
    if (badge) row.appendChild(treeBadge(badge));
    row.addEventListener("click", () => {
      setText("selectedNodeSummary", summary || `${title}${meta ? `；${meta}` : ""}`);
      if (config.expandable && config.nodeId) toggleTreeNode(config.nodeId, config.defaultExpanded !== false);
    });
    return row;
  }


  function treeExpanded(nodeId, defaultExpanded) {
    const tree = objectOf(state.expanded && state.expanded.tree);
    if (!nodeId || tree[nodeId] === undefined) return Boolean(defaultExpanded);
    return Boolean(tree[nodeId]);
  }


  function toggleTreeNode(nodeId, defaultExpanded) {
    state.expanded.tree = objectOf(state.expanded.tree);
    state.expanded.tree[nodeId] = !treeExpanded(nodeId, defaultExpanded);
    renderStructureTree();
  }


  function treeBadge(text) {
    const badge = document.createElement("span");
    badge.className = "tree-badge";
    badge.textContent = text;
    return badge;
  }


  function optionBadge(item) {
    if (Array.isArray(item.assets) && item.assets.length > 1) return "多素材库";
    if (Array.isArray(item.assets) && item.assets.length === 1) return "素材";
    if (Array.isArray(item.tails) && item.tails.length) return "尾巴";
    return "";
  }


  function optionSlotSummary(item) {
    const slots = Array.isArray(item.slots) ? item.slots : [];
    if (!slots.length) return "";
    return slots.slice(0, 3).map((slot) => slot.key || slot.name).filter(Boolean).join(" · ");
  }


  function optionTreeChildren(item) {
    const rows = [];
    optionChildRows(item, "slots", "slots", "槽位").forEach((row) => rows.push(row));
    optionChildRows(item, "anchors", "anchors", "定位").forEach((row) => rows.push(row));
    optionChildRows(item, "tails", "tails", "尾巴").forEach((row) => rows.push(row));
    optionChildRows(item, "fixed_annotations", "fixed", "固定图案").forEach((row) => rows.push(row));
    optionChildRows(item, "assets", "assets", "Assets").forEach((row) => rows.push(row));
    return rows;
  }


  function optionChildRows(item, key, kind, label) {
    const children = Array.isArray(item[key]) ? item[key] : [];
    const visibleChildren = key === "fixed_annotations" ? children : children.slice(0, 8);
    return visibleChildren.map((child) => {
      const name = child.key || child.name || child.asset_key || label;
      return {
        title: key === "assets" ? `Assets / ${name}` : name,
        meta: key === "assets" ? supportedValuesText(child) : key === "fixed_annotations" ? "固定图案 · 自动保护" : label,
        kind,
        summary: nodeSummary(kind, child)
      };
    });
  }


  function supportedValuesText(asset) {
    const values = asset && (asset.supported_values || asset.values);
    return Array.isArray(values) && values.length ? `${values.length} 项` : "";
  }


  function scopedTreeItems(outputKey, items) {
    const scoped = items.filter((item) => treeOutputScope(item) === outputKey);
    if (scoped.length) return scoped;
    return (scanOutputCount() > 1) ? [] : items;
  }


  function treeOutputScope(item) {
    const data = objectOf(item);
    const nested = objectOf(data.output);
    return cleanText(nested.key || nested.name || data.output_key || data.outputKey || data.parent_output || data.parentOutput || data.output);
  }


  function scanOutputCount() {
    return scanModel(state.scan || {}, state.draft && state.draft.config).outputs.length || 1;
  }


  function outputKeyForTree(output, index) {
    return safeOutputKey(output.key || output.name, index ? `Output_Side${String.fromCharCode(65 + index)}` : "Output_main", index);
  }


  function outputDisplayName(outputKey) {
    const configured = (configOutputs().length ? configOutputs() : inferredOutputs()).find((item) => safeOutputKey(item.key || item.name, "Output_main", 0) === outputKey);
    return cleanText(configured && configured.display_name) || (outputKey === "Output_main" ? "主效果图" : "");
  }


  function fixedObjectTotal(scan, model) {
    const outputs = Array.isArray(scan && scan.outputs) ? scan.outputs : [];
    const fromSummary = outputs.reduce((total, output) => total + Number(objectOf(output.summary).fixed_objects || 0), 0);
    if (fromSummary) return fromSummary;
    return model.fixedObjects.reduce((total, item) => total + Number(item.count || item.fixed_object_count || 1), 0);
  }


  Object.assign(globalThis, {
    renderStructureTree
  });
})();
