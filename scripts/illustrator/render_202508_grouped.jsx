#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "jjmb_202508_grouped") throw new Error("Unsupported task type: " + task.type);
    var config = readJSON(String(task.template_config));
    if (!task.groups || task.groups.length === 0) throw new Error("No order groups");
    var outputConfig = task.output || {};
    var colorMode = outputColorMode(outputConfig.color_mode);
    var outlineText = outputConfig.outline_text !== false;
    var pathfinderMerge = outputConfig.pathfinder_merge !== false;
    var cleanupStats = { attempted: 0, failed: 0 };
    var fontStyles = task.font_styles || {};

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var layout = task.layout || {};
    var showBoxes = layout.show_style_boxes === true;
    var compactOutput = !showBoxes;
    var suppressLabels = layout.suppress_labels === true;
    var packOrderBlocks = layout.pack_order_blocks === true;
    var forceSubitemOrderLabels = packOrderBlocks && (!layout.master_packing || layout.master_packing.force_subitem_order_labels !== false);
    var columns = Math.max(Number(layout.columns || 4), 1);
    var gap = mmToPt(Number(compactOutput ? (layout.compact_gap_mm || 4) : (layout.gap_mm || 8)));
    var margin = mmToPt(Number(compactOutput ? (layout.compact_margin_mm || 4) : (layout.margin_mm || 8)));
    var orderLabelHeight = mmToPt(Number(compactOutput ? (layout.compact_order_label_height_mm || 5) : (layout.order_label_height_mm || 7)));
    var groupLabelHeight = compactOutput ? 0 : orderLabelHeight;
    var itemLabelHeight = mmToPt(Number(compactOutput ? (layout.compact_item_label_height_mm || 5) : (layout.item_label_height_mm || 6)));
    var labelFontSize = Number(compactOutput ? (layout.compact_label_font_size_pt || 10) : (layout.label_font_size_pt || 12));
    var itemGap = mmToPt(Number(compactOutput ? (layout.compact_item_gap_mm || 2) : (layout.item_gap_mm || 5)));
    var compactLabelWidth = mmToPt(Number(layout.compact_label_width_mm || 90));
    var padding = mmToPt(Number(task.fit && task.fit.padding_mm || 0));
    var minFontSize = Number(task.fit && task.fit.min_font_size_pt || 4);
    var maxFontSize = Number(task.fit && task.fit.max_font_size_pt || 300);
    var renderedItems = 0;

    var productSize = maxProductSize(config);
    var contentSize = compactOutput ? maxAnchorSize(config) : productSize;
    var columnWidth = compactOutput ? Math.max(contentSize.width, compactLabelWidth) : contentSize.width;
    var renderGroups = compactOutput ? buildCompactGroups(task.groups) : task.groups;
    var groupMetrics = [];
    var maxGroupWidth = columnWidth;
    for (var g = 0; g < renderGroups.length; g++) {
        var itemCount = renderGroups[g].items.length;
        var compactHeight = (suppressLabels ? 0 : itemLabelHeight + itemGap) + itemCount * (contentSize.height + itemGap);
        var metric = {
            width: columnWidth,
            height: compactOutput ? compactHeight : groupLabelHeight + itemCount * (itemLabelHeight + contentSize.height + itemGap)
        };
        groupMetrics.push(metric);
        maxGroupWidth = Math.max(maxGroupWidth, metric.width);
    }

    var placements = compactPlacements(groupMetrics, columns, gap);
    var maxColumnHeight = placementHeight(placements);
    var docWidth = margin * 2 + columns * maxGroupWidth + (columns - 1) * gap;
    var docHeight = margin * 2 + maxColumnHeight;
    var fixedCanvas = outputConfig.fixed_canvas_mm || {};
    var fixedWidthMm = Number(fixedCanvas.width_mm || 0);
    var fixedHeightMm = Number(fixedCanvas.height_mm || 0);
    if (fixedWidthMm > 0 && fixedHeightMm > 0) {
        var fixedWidth = mmToPt(fixedWidthMm);
        var fixedHeight = mmToPt(fixedHeightMm);
        var maxColumns = Math.floor((fixedWidth - margin * 2 + gap) / (maxGroupWidth + gap));
        if (maxColumns < 1) throw new Error("固定画布宽度不足，无法放入一个完整订单组");
        var fitting = null;
        for (var candidateColumns = 1; candidateColumns <= maxColumns; candidateColumns++) {
            var candidatePlacements = compactPlacements(groupMetrics, candidateColumns, gap);
            if (placementHeight(candidatePlacements) <= fixedHeight - margin * 2) {
                fitting = candidatePlacements;
                columns = candidateColumns;
                break;
            }
        }
        if (!fitting) throw new Error("固定画布高度不足，无法完整放入全部订单；请减少订单或分批出图");
        placements = fitting;
        maxColumnHeight = placementHeight(placements);
        docWidth = fixedWidth;
        docHeight = fixedHeight;
    }
    var debugPayload = {
        groups: renderGroups.length,
        sourceGroups: task.groups.length,
        columns: columns,
        compactOutput: compactOutput,
        suppressLabels: suppressLabels,
        packOrderBlocks: packOrderBlocks,
        docWidth: docWidth,
        docHeight: docHeight,
        productWidthPt: productSize.width,
        productHeightPt: productSize.height,
        contentWidthPt: contentSize.width,
        contentHeightPt: contentSize.height,
        compactLabelWidthPt: compactLabelWidth,
        groupLabelHeightPt: groupLabelHeight,
        colorMode: colorMode,
        pathfinderMerge: pathfinderMerge,
        cleanupStats: cleanupStats
    };

    var doc = app.documents.add(documentColorSpace(colorMode), docWidth, docHeight);
    var layer = doc.layers[0];
    layer.name = "JJMB202508261001394920_OUTPUT";
    writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在渲染条目");

    for (var i = 0; i < renderGroups.length; i++) {
        var group = renderGroups[i];
        var beforeGroupItems = packOrderBlocks ? directLayerItems(layer) : null;
        var col = placements.items[i].column;
        var groupLeft = margin + col * (maxGroupWidth + gap);
        var groupTop = docHeight - margin - placements.items[i].y;
        var cursorTop = groupTop;

        if (groupLabelHeight > 0) {
            drawLabel(layer, String(group.order_no || ""), groupLeft, cursorTop, groupLeft + maxGroupWidth, cursorTop - groupLabelHeight, labelFontSize);
            cursorTop -= groupLabelHeight;
        }

        for (var j = 0; j < group.items.length; j++) {
            var item = group.items[j];
            var beforeItemItems = packOrderBlocks ? directLayerItems(layer) : null;
            var design = designConfig(config, item.design_option);
            var font = fontConfig(config, item.font_option);
            var productLeft = groupLeft + (maxGroupWidth - productSize.width) / 2;
            var productTop = cursorTop - itemLabelHeight;
            var productRight = productLeft + productSize.width;
            var productBottom = productTop - productSize.height;
            var itemLabel = item.production_label || (item.show_color_label ? item.order_no + "  " + item.font_option + "  " + item.color_option : item.order_no);
            var drawFrame = !compactOutput && showBoxes;

            if (compactOutput) {
                if (forceSubitemOrderLabels || (!suppressLabels && j === 0)) {
                    var labelLinesForGroup = forceSubitemOrderLabels ? [String(item.order_no || item.production_label || "ORDER")] : (group.production_label_lines || labelLines(item, itemLabel));
                    var labelLeftForGroup = groupLeft + (maxGroupWidth - compactLabelWidth) / 2;
                    var labelRightForGroup = labelLeftForGroup + compactLabelWidth;
                    var compactLabelFrames = drawLabelLines(layer, labelLinesForGroup, labelLeftForGroup, cursorTop, labelRightForGroup, cursorTop - itemLabelHeight, labelFontSize);
                    // AI8 may flatten a group when its child label is outlined later.  Convert the
                    // label before creating ORDER_PACK_ITEM so the item keeps one stable child group.
                    if (packOrderBlocks && outlineText) outlineTextFrames(compactLabelFrames, pathfinderMerge);
                    cursorTop -= itemLabelHeight + itemGap;
                }
                var contentLeft = groupLeft + (maxGroupWidth - contentSize.width) / 2;
                var contentTop = cursorTop;
                var contentRight = contentLeft + contentSize.width;
                var contentBottom = contentTop - contentSize.height;

                drawPersonalizedText(layer, item, font, design, [contentLeft + padding, contentTop - padding, contentRight - padding, contentBottom + padding], minFontSize, maxFontSize, item.text_actions || []);
                if (packOrderBlocks) {
                    groupNewLayerItems(layer, beforeItemItems, "ORDER_PACK_ITEM_" + i + "_" + j);
                }
                cursorTop = contentBottom - itemGap;
                renderedItems += 1;
                writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在渲染条目");
                continue;
            }

            drawLabel(layer, itemLabel, productLeft, cursorTop, productRight, cursorTop - itemLabelHeight, labelFontSize);
            if (drawFrame) drawBox(layer, productLeft, productTop, productSize.width, productSize.height, "PRODUCT_BOX");
            var anchor = mapAnchor(design, productLeft, productTop, productSize.width, productSize.height);
            if (drawFrame) drawBox(layer, anchor[0], anchor[1], anchor[2] - anchor[0], anchor[1] - anchor[3], item.design_option + "_BOX");

            drawPersonalizedText(layer, item, font, design, [anchor[0] + padding, anchor[1] - padding, anchor[2] - padding, anchor[3] + padding], minFontSize, maxFontSize, item.text_actions || []);
            cursorTop = productBottom - itemGap;
            renderedItems += 1;
            writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在渲染条目");
        }
        if (packOrderBlocks) {
            groupNewLayerItems(layer, beforeGroupItems, "ORDER_PACK_BLOCK_" + i);
        }
    }

    if (outlineText) {
        writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在转曲标注文字");
        outlineAllTextFrames(doc, pathfinderMerge);
    }
    writeDebug(task, debugPayload);
    var output;
    if (String(outputConfig.format || "ai").toLowerCase() === "png") {
        output = File(String(outputConfig.png_path || ""));
        if (!output.fsName) throw new Error("PNG 输出路径缺失");
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在导出 PNG 文件");
        exportPNG(doc, output, Number(outputConfig.dpi || 300));
    } else {
        output = File(String(task.output_ai));
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在保存 AI 文件");
        saveAsAI(doc, output, String(outputConfig.compatibility || "Illustrator 8"));
    }
    writeProgress(task, renderedItems, taskItemCount(renderGroups), "正在关闭 Illustrator 文档");
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function placementHeight(plan) {
        var height = 0;
        for (var index = 0; index < plan.columnHeights.length; index++) {
            height = Math.max(height, plan.columnHeights[index]);
        }
        return height > 0 ? height - gap : 0;
    }

    function maxProductSize(config) {
        var width = 0;
        var height = 0;
        for (var key in config.design_options) {
            if (!config.design_options.hasOwnProperty(key)) continue;
            var b = config.design_options[key].product_bounds_pt;
            width = Math.max(width, Math.abs(Number(b[2]) - Number(b[0])));
            height = Math.max(height, Math.abs(Number(b[1]) - Number(b[3])));
        }
        if (width <= 0 || height <= 0) {
            width = mmToPt(100);
            height = mmToPt(100);
        }
        return { width: width, height: height };
    }

    function maxAnchorSize(config) {
        var width = 0;
        var height = 0;
        for (var key in config.design_options) {
            if (!config.design_options.hasOwnProperty(key)) continue;
            var b = config.design_options[key].anchor_bounds_pt;
            width = Math.max(width, Math.abs(Number(b[2]) - Number(b[0])));
            height = Math.max(height, Math.abs(Number(b[1]) - Number(b[3])));
        }
        if (width <= 0 || height <= 0) {
            width = mmToPt(55);
            height = mmToPt(40);
        }
        return { width: width, height: height };
    }

    function buildCompactGroups(groups) {
        var result = [];
        for (var i = 0; i < groups.length; i++) {
            var source = groups[i];
            var buckets = {};
            var keys = [];
            var items = source.items || [];
            for (var j = 0; j < items.length; j++) {
                var item = items[j];
                var lines = labelLines(item, item.production_label || item.order_no || source.order_no || "");
                var key = String(source.order_no || item.order_no || "") + "\u001f" + String(item.color_option || "") + "\u001f" + lines.join("\u001e");
                if (!buckets[key]) {
                    buckets[key] = {
                        order_no: source.order_no || item.order_no || "",
                        production_label: lines.join("  "),
                        production_label_lines: lines,
                        items: []
                    };
                    keys.push(key);
                }
                buckets[key].items.push(item);
            }
            for (var k = 0; k < keys.length; k++) {
                result.push(buckets[keys[k]]);
            }
        }
        return result;
    }

    function taskItemCount(groups) {
        var total = 0;
        for (var i = 0; i < groups.length; i++) {
            total += (groups[i].items || []).length;
        }
        return total;
    }

    function mapAnchor(design, productLeft, productTop, productWidth, productHeight) {
        var product = design.product_bounds_pt;
        var anchor = design.anchor_bounds_pt;
        var sourceWidth = Math.abs(Number(product[2]) - Number(product[0]));
        var sourceHeight = Math.abs(Number(product[1]) - Number(product[3]));
        var sx = productWidth / sourceWidth;
        var sy = productHeight / sourceHeight;
        var left = productLeft + (Number(anchor[0]) - Number(product[0])) * sx;
        var top = productTop - (Number(product[1]) - Number(anchor[1])) * sy;
        var right = productLeft + (Number(anchor[2]) - Number(product[0])) * sx;
        var bottom = productTop - (Number(product[1]) - Number(anchor[3])) * sy;
        return [left, top, right, bottom];
    }

    function drawLabel(layer, text, left, top, right, bottom, size) {
        var tf = layer.textFrames.add();
        tf.contents = String(text || "");
        tf.textRange.characterAttributes.size = size;
        applyColor(tf, [0, 0, 0]);
        fitTextToRect(tf, [left, top, right, bottom], 5, size);
        return tf;
    }

    function drawLabelLines(layer, lines, left, top, right, bottom, size) {
        var clean = [];
        for (var i = 0; i < lines.length; i++) {
            var text = String(lines[i] || "");
            if (text) clean.push(text);
        }
        if (clean.length === 0) clean.push("");
        var lineHeight = (top - bottom) / clean.length;
        var frames = [];
        for (var l = 0; l < clean.length; l++) {
            var lineTop = top - l * lineHeight;
            var lineBottom = lineTop - lineHeight;
            frames.push(drawLabel(layer, clean[l], left, lineTop, right, lineBottom, size));
        }
        return frames;
    }

    function labelLines(item, fallback) {
        if (item.production_label_lines && item.production_label_lines instanceof Array && item.production_label_lines.length > 0) {
            return item.production_label_lines;
        }
        return [fallback];
    }

    function drawBox(layer, left, top, width, height, name) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.name = name;
        rect.filled = false;
        rect.stroked = true;
        rect.strokeWidth = 0.35;
        var color = new RGBColor();
        color.red = 255;
        color.green = 102;
        color.blue = 153;
        rect.strokeColor = color;
        return rect;
    }

    function drawPersonalizedText(layer, item, font, design, rect, minSize, maxSize, actions) {
        var tf = layer.textFrames.add();
        tf.contents = String(item.text || "");
        applyFontConfig(tf, font);
        applyColor(tf, item.apply_color_to_artwork ? colorConfig(config, item.color_option) : [0, 0, 0]);
        applyTextActions(tf, actions || []);
        applyFontBoldness(tf, fontStyles[String(item.font_option || "")]);
        return renderOutlinedTextToRect(tf, rect, minSize, maxSize, Number(design.rotation_deg || 0), shouldPreserveTextAspect(String(item.text || "")));
    }

    function shouldPreserveTextAspect(text) {
        return /\s/.test(text) || text.length > 10;
    }

    function designConfig(config, name) {
        var key = String(name || (config.defaults && config.defaults.design_option) || "Design2").replace(/\s+/g, "");
        var design = config.design_options && config.design_options[key];
        if (!design) throw new Error("Design config not found: " + key);
        return design;
    }

    function fontConfig(config, name) {
        var font = config.font_options && config.font_options[String(name || "")];
        if (!font) throw new Error("Font config not found: " + name);
        return font;
    }

    function colorConfig(config, name) {
        var color = config.color_options && config.color_options[String(name || "")];
        if (!color) color = config.color_options && config.color_options["Gold"];
        return color && color.rgb ? color.rgb : [0, 0, 0];
    }

    function applyFontConfig(tf, font) {
        var attr = tf.textRange.characterAttributes;
        attr.size = Number(font.font_size_pt || 48);
        try { attr.tracking = Number(font.tracking || 0); } catch (e1) {}
        try { attr.horizontalScale = Number(font.horizontal_scale || 100); } catch (e2) {}
        try { attr.verticalScale = Number(font.vertical_scale || 100); } catch (e3) {}
        applyFont(tf, String(font.font_name || font.font_family || ""));
    }

    function applyFont(tf, fontName) {
        if (!fontName) return;
        try {
            for (var i = 0; i < app.textFonts.length; i++) {
                var font = app.textFonts[i];
                if (font.name === fontName || font.family === fontName) {
                    tf.textRange.characterAttributes.textFont = font;
                    return;
                }
            }
        } catch (e) {}
    }

    function applyColor(tf, rgb) {
        var color = new RGBColor();
        color.red = Number(rgb[0] || 0);
        color.green = Number(rgb[1] || 0);
        color.blue = Number(rgb[2] || 0);
        tf.textRange.characterAttributes.fillColor = color;
    }

    function applyTextActions(tf, actions) {
        for (var actionIndex = 0; actionIndex < actions.length; actionIndex++) {
            var action = actions[actionIndex] || {};
            if (String(action.type || "") === "fill_color") {
                applyFillColorAction(tf, action);
            } else {
                throw new Error("Unsupported compiled rule action: " + action.type);
            }
        }
    }

    function applyFillColorAction(tf, action) {
        var values = action.values || [];
        if (!values.length) return;
        var selector = action.selector || {};
        if (String(selector.type || "whole") !== "segments") {
            var wholeRgb = hexColor(values[0]);
            if (wholeRgb) applyColor(tf, wholeRgb);
            return;
        }
        var delimiter = String(selector.delimiter || "");
        var parts = String(tf.contents || "").split(delimiter);
        if (!delimiter || parts.length < 2) return;
        var cursor = 0;
        for (var partIndex = 0; partIndex < parts.length; partIndex++) {
            var rgb = hexColor(values[partIndex % values.length]);
            if (rgb) {
                var color = new RGBColor();
                color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
                for (var charIndex = 0; charIndex < parts[partIndex].length; charIndex++) {
                    tf.characters[cursor + charIndex].characterAttributes.fillColor = color;
                }
            }
            cursor += parts[partIndex].length + (partIndex < parts.length - 1 ? delimiter.length : 0);
        }
    }

    function applyFontBoldness(tf, style) {
        var boldness = Number(style && style.boldness);
        if (isNaN(boldness) || boldness <= 0) return;
        try {
            var characters = tf.characters;
            var appliedToAll = characters.length > 0;
            for (var index = 0; index < characters.length; index++) {
                if (!applyBoldnessToAttributes(characters[index].characterAttributes, boldness)) appliedToAll = false;
            }
            if (appliedToAll) return;
        } catch (e1) {}
        applyBoldnessToAttributes(tf.textRange.characterAttributes, boldness);
    }

    function applyBoldnessToAttributes(attributes, boldness) {
        if (!attributes) return false;
        try { attributes.strokeColor = attributes.fillColor; } catch (e1) {}
        try { attributes.strokeWeight = boldness; return true; } catch (e2) {}
        try { attributes.strokeWidth = boldness; return true; } catch (e3) {}
        return false;
    }

    function hexColor(value) {
        var match = String(value || "").match(/^#([0-9a-f]{6})$/i);
        if (!match) return null;
        var hex = match[1];
        return [
            parseInt(hex.substring(0, 2), 16),
            parseInt(hex.substring(2, 4), 16),
            parseInt(hex.substring(4, 6), 16)
        ];
    }

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        tf.textRange.characterAttributes.size = fitMaxFontSize(tf, maxW, maxH, minSize, maxSize);
        try { app.redraw(); } catch (e0) {}
        var b = tf.visibleBounds;
        tf.translate((left + right) / 2 - (b[0] + b[2]) / 2, (top + bottom) / 2 - (b[1] + b[3]) / 2);
    }

    function renderOutlinedTextToRect(tf, rect, minSize, maxSize, rotationDeg, preserveAspect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        tf.textRange.characterAttributes.size = fitMaxFontSize(tf, maxW, maxH, minSize, maxSize);
        try { app.redraw(); } catch (e0) {}
        if (!outlineText) {
            fitTextToRect(tf, rect, minSize, maxSize);
            if (rotationDeg) {
                try { tf.rotate(rotationDeg, true, true, true, true, Transformation.CENTER); } catch (eTextRotate) {}
            }
            return tf;
        }
        var outline = tf.createOutline();
        if (rotationDeg) {
            try { outline.rotate(rotationDeg, true, true, true, true, Transformation.CENTER); } catch (e1) {}
        }
        fitPageItemToRect(outline, rect, preserveAspect);
        if (pathfinderMerge) {
            cleanupOutline(outline);
            fitPageItemToRect(outline, rect, preserveAspect);
        }
        return outline;
    }

    function fitMaxFontSize(tf, maxW, maxH, minSize, maxSize) {
        var size = Math.min(Math.max(tf.textRange.characterAttributes.size, minSize), maxSize);
        tf.textRange.characterAttributes.size = size;
        for (var i = 0; i < 8; i++) {
            try { app.redraw(); } catch (e0) {}
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) break;
            var scale = Math.min(maxW / w, maxH / h) * 0.98;
            var nextSize = Math.min(Math.max(size * scale, minSize), maxSize);
            if (Math.abs(nextSize - size) < 0.05) break;
            size = nextSize;
            tf.textRange.characterAttributes.size = size;
        }
        return size;
    }

    function fitPageItemToRect(item, rect, preserveAspect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        for (var i = 0; i < 4; i++) {
            try { app.redraw(); } catch (e0) {}
            var b = item.geometricBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) return;
            var scaleX = ((right - left) / w) * 100;
            var scaleY = ((top - bottom) / h) * 100;
            if (preserveAspect) {
                var scale = Math.min(scaleX, scaleY);
                scaleX = scale;
                scaleY = scale;
            }
            try {
                item.resize(scaleX, scaleY, true, true, true, true, 100, Transformation.CENTER);
            } catch (e1) {
                try { item.resize(scaleX, scaleY); } catch (e2) {}
            }
            if (preserveAspect) {
                centerPageItemInRect(item, rect);
            } else {
                alignPageItemToRect(item, rect);
            }
        }
    }

    function alignPageItemToRect(item, rect) {
        var b = item.geometricBounds;
        item.translate(rect[0] - b[0], rect[1] - b[1]);
    }

    function centerPageItemInRect(item, rect) {
        var b = item.geometricBounds;
        item.translate((rect[0] + rect[2]) / 2 - (b[0] + b[2]) / 2, (rect[1] + rect[3]) / 2 - (b[1] + b[3]) / 2);
    }

    function cleanupOutline(item) {
        if (!item) return;
        cleanupStats.attempted += 1;
        try { app.executeMenuCommand("deselectall"); } catch (e0) {}
        try {
            item.selected = true;
            app.executeMenuCommand("Live Pathfinder Add");
            app.executeMenuCommand("expandStyle");
            item.selected = false;
        } catch (e1) {
            cleanupStats.failed += 1;
            try { item.selected = false; } catch (e2) {}
        }
    }

    function outlineAllTextFrames(doc, shouldCleanup) {
        var frames = [];
        for (var l = 0; l < doc.layers.length; l++) collectTextFrames(doc.layers[l], frames);
        outlineTextFrames(frames, shouldCleanup);
    }

    function outlineTextFrames(frames, shouldCleanup) {
        for (var i = frames.length - 1; i >= 0; i--) {
            try {
                var outline = frames[i].createOutline();
                if (shouldCleanup) cleanupOutline(outline);
            } catch (e1) {
                cleanupStats.failed += 1;
            }
        }
    }

    function collectTextFrames(container, result) {
        if (!container || !container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.typename === "TextFrame") result.push(item);
            if (item.typename === "GroupItem" || item.typename === "Layer") {
                collectTextFrames(item, result);
            }
        }
    }

    function directLayerItems(layer) {
        var result = [];
        for (var i = 0; i < layer.pageItems.length; i++) {
            if (layer.pageItems[i].parent === layer) result.push(layer.pageItems[i]);
        }
        return result;
    }
    function groupNewLayerItems(layer, previousItems, name) {
        var additions = [];
        var currentItems = directLayerItems(layer);
        for (var i = 0; i < currentItems.length; i++) {
            var known = false;
            for (var j = 0; j < previousItems.length; j++) {
                if (currentItems[i] === previousItems[j]) { known = true; break; }
            }
            if (!known) additions.push(currentItems[i]);
        }
        if (!additions.length) throw new Error("Order pack block has no artwork");
        var doc = app.activeDocument;
        doc.selection = null;
        for (var selectionIndex = 0; selectionIndex < additions.length; selectionIndex++) {
            additions[selectionIndex].selected = true;
        }
        app.executeMenuCommand("group");
        var block = doc.selection.length ? doc.selection[0] : null;
        if (!block || block.typename !== "GroupItem") throw new Error("Cannot create order pack block");
        block.name = name;
        doc.selection = null;
        return block;
    }

    function compactPlacements(metrics, columnCount, gapValue) {
        var heights = [];
        var items = [];
        for (var c = 0; c < columnCount; c++) heights.push(0);
        for (var i = 0; i < metrics.length; i++) {
            var column = 0;
            for (var h = 1; h < heights.length; h++) {
                if (heights[h] < heights[column]) column = h;
            }
            items.push({ column: column, y: heights[column] });
            heights[column] += metrics[i].height + gapValue;
        }
        return { items: items, columnHeights: heights };
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("JSON file not found: " + path);
        file.encoding = "UTF-8";
        file.open("r");
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }

    function writeDebug(task, payload) {
        try {
            if (!task.debug || !task.debug.report_path) return;
            var file = File(String(task.debug.report_path));
            ensureFolder(file.parent);
            file.encoding = "UTF-8";
            if (!file.open("w")) return;
            file.write(toJson(payload));
            file.close();
        } catch (e) {}
    }

    function writeProgress(task, current, total, stage) {
        var progress = task.progress || {};
        if (!progress.file) return;
        var offset = Number(progress.offset || 0);
        var grandTotal = Number(progress.total || total || 0);
        var payload = {
            current: Math.min(offset + current, grandTotal),
            total: grandTotal,
            stage: String(stage || progress.stage || "")
        };
        var file = File(String(progress.file));
        ensureFolder(file.parent);
        if (file.open("w")) {
            file.encoding = "UTF-8";
            file.write(toJson(payload));
            file.close();
        }
    }

    function toJson(value) {
        if (value === null) return "null";
        var type = typeof value;
        if (type === "number" || type === "boolean") return String(value);
        if (type === "string") return "\"" + String(value).replace(/\\/g, "\\\\").replace(/"/g, "\\\"").replace(/\n/g, "\\n") + "\"";
        if (value instanceof Array) {
            var arr = [];
            for (var i = 0; i < value.length; i++) arr.push(toJson(value[i]));
            return "[" + arr.join(",") + "]";
        }
        var props = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) props.push(toJson(key) + ":" + toJson(value[key]));
        }
        return "{" + props.join(",") + "}";
    }

    function saveAsAI(doc, file, compatibility) {
        var opts = new IllustratorSaveOptions();
        opts.compatibility = String(compatibility).toLowerCase() === "cs5" ? Compatibility.ILLUSTRATOR15 : Compatibility.ILLUSTRATOR8;
        opts.pdfCompatible = false;
        opts.compressed = false;
        doc.saveAs(file, opts);
    }

    function exportPNG(doc, file, dpi) {
        var opts = new ExportOptionsPNG24();
        // Illustrator floors some large artboard exports one pixel below their
        // mathematical size. A tiny positive guard preserves the requested
        // 580 x 2000mm / 300PPI raster without crossing the next width pixel.
        var scale = Math.max(1, Number(dpi || 300) / 72 * 100 + 0.02);
        opts.antiAliasing = true;
        opts.artBoardClipping = true;
        opts.transparency = false;
        opts.horizontalScale = scale;
        opts.verticalScale = scale;
        doc.exportFile(file, ExportType.PNG24, opts);
    }

    function ensureFolder(folder) {
        if (!folder.exists) {
            ensureFolder(folder.parent);
            folder.create();
        }
    }

    function mmToPt(mm) {
        return mm * 72 / 25.4;
    }

    function outputColorMode(value) {
        var mode = String(value || "CMYK").toUpperCase();
        return mode === "RGB" ? "RGB" : "CMYK";
    }

    function documentColorSpace(mode) {
        return mode === "CMYK" ? DocumentColorSpace.CMYK : DocumentColorSpace.RGB;
    }
}());
