#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    if (task.type !== "config_grouped_text_sheet") throw new Error("Unsupported task type: " + task.type);
    var config = readJSON(String(task.template_config));
    if (!task.groups || task.groups.length === 0) throw new Error("No order groups");
    var exportConfig = task.export || {};
    var colorMode = outputColorMode(exportConfig.color_mode);
    var fontStyles = task.font_styles || {};

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}

    var layout = task.layout || {};
    var columns = Math.max(Number(layout.columns || 4), 1);
    var gap = mmToPt(Number(layout.gap_mm || 8));
    var margin = mmToPt(Number(layout.margin_mm || 8));
    var orderLabelHeight = mmToPt(Number(layout.order_label_height_mm || 7));
    var orderLabelFontSize = Number(layout.order_label_font_size_pt || 12);
    var itemGap = mmToPt(Number(layout.item_gap_mm || 4));
    var showStyleBoxes = layout.show_style_boxes === true;
    var padding = mmToPt(numberOrDefault(task.fit && task.fit.padding_mm, 1));
    var minFontSize = numberOrDefault(task.fit && task.fit.min_font_size_pt, 4);
    var maxFontSize = numberOrDefault(task.fit && task.fit.max_font_size_pt, 300);

    var groupMetrics = [];
    var maxGroupWidth = 0;
    for (var g = 0; g < task.groups.length; g++) {
        var metrics = measureGroup(task.groups[g], config, orderLabelHeight, itemGap);
        groupMetrics.push(metrics);
        maxGroupWidth = Math.max(maxGroupWidth, metrics.width);
    }

    var placements = compactPlacements(groupMetrics, columns, gap);
    var rows = Math.ceil(task.groups.length / columns);
    var maxColumnHeight = 0;
    for (var h = 0; h < placements.columnHeights.length; h++) {
        maxColumnHeight = Math.max(maxColumnHeight, placements.columnHeights[h]);
    }
    if (maxColumnHeight > 0) maxColumnHeight -= gap;
    var docWidth = margin * 2 + columns * maxGroupWidth + (columns - 1) * gap;
    var docHeight = margin * 2 + maxColumnHeight;
    var fitStats = { count: 0, maxDeltaPt: 0 };
    var debugPayload = {
        groups: task.groups.length,
        columns: columns,
        rows: rows,
        maxGroupWidth: maxGroupWidth,
        maxColumnHeight: maxColumnHeight,
        docWidth: docWidth,
        docHeight: docHeight,
        colorMode: colorMode,
        sampleStyle: styleConfig(config, task.groups[0].items[0].style_option)
    };
    var doc = app.documents.add(documentColorSpace(colorMode), docWidth, docHeight);
    var layer = doc.layers[0];
    layer.name = "GROUPED_OUTPUT";

    var outlines = [];
    for (var i = 0; i < task.groups.length; i++) {
        var group = task.groups[i];
        var metric = groupMetrics[i];
        var col = placements.items[i].column;
        var groupLeft = margin + col * (maxGroupWidth + gap);
        var groupTop = docHeight - margin - placements.items[i].y;
        var cursorTop = groupTop;

        var orderLabel = layer.textFrames.add();
        orderLabel.contents = String(group.order_no || "");
        orderLabel.textRange.characterAttributes.size = orderLabelFontSize;
        applyColor(orderLabel, "black");
        fitTextToRect(orderLabel, [groupLeft, cursorTop, groupLeft + metric.width, cursorTop - orderLabelHeight], 6, orderLabelFontSize);
        outlines.push(orderLabel);
        cursorTop -= orderLabelHeight;

        for (var j = 0; j < group.items.length; j++) {
            var item = group.items[j];
            var style = styleConfig(config, item.style_option);
            var styleWidth = styleWidthPt(style);
            var styleHeight = styleHeightPt(style);
            var boxLeft = groupLeft + (metric.width - styleWidth) / 2;
            var boxTop = cursorTop;
            var boxRight = boxLeft + styleWidth;
            var boxBottom = boxTop - styleHeight;

            if (showStyleBoxes) drawStyleBox(layer, boxLeft, boxTop, styleWidth, styleHeight, String(item.style_option || ""));

            if (String(item.render_kind || "text") === "design_asset") {
                var designItem = renderDesignAssetItem(
                    layer,
                    item,
                    [boxLeft + padding, boxTop - padding, boxRight - padding, boxBottom + padding],
                    fontStyles[String(item.font_option || "")]
                );
                try { designItem.name = String(item.order_no || "") + "_" + String(item.quantity_index || j + 1) + "_DESIGN"; } catch (eD0) {}
            } else {
                var font = fontConfig(config, item.font_option);
                var tf = layer.textFrames.add();
                tf.contents = String(item.text || "");
                applyFontConfig(tf, font);
                applyColor(tf, String(task.style && task.style.color_name || "black"));
                applyFontBoldness(tf, fontStyles[String(item.font_option || "")]);
                var outline = renderOutlinedTextToRect(tf, [boxLeft + padding, boxTop - padding, boxRight - padding, boxBottom + padding], minFontSize, maxFontSize);
                try { outline.name = String(item.order_no || "") + "_" + String(item.quantity_index || j + 1) + "_TEXT"; } catch (e0) {}
            }
            cursorTop = boxBottom - itemGap;
        }
    }

    if (exportConfig.outline_text) outlineAndClean(outlines);
    debugPayload.textFit = {
        count: fitStats.count,
        maxDeltaPt: fitStats.maxDeltaPt,
        maxDeltaMm: fitStats.maxDeltaPt * 25.4 / 72
    };
    writeDebug(task, debugPayload);

    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAsAI8(doc, output);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function measureGroup(group, config, labelHeight, itemGapValue) {
        var width = 0;
        var height = labelHeight;
        for (var i = 0; i < group.items.length; i++) {
            var style = styleConfig(config, group.items[i].style_option);
            width = Math.max(width, styleWidthPt(style));
            height += styleHeightPt(style);
            if (i < group.items.length - 1) height += itemGapValue;
        }
        return { width: width, height: height };
    }

    function drawStyleBox(layer, left, top, width, height, name) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.name = name + "_BOX";
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

    function styleConfig(config, name) {
        var style = config.style_options && config.style_options[String(name)];
        if (!style) throw new Error("Style config not found: " + name);
        return style;
    }

    function styleWidthPt(style) {
        var value = Number(style.width_pt);
        if (!isNaN(value) && value > 0) return value;
        var b = style.bounds_pt || [0, 0, 0, 0];
        return Math.abs(Number(b[2]) - Number(b[0]));
    }

    function styleHeightPt(style) {
        var value = Number(style.height_pt);
        if (!isNaN(value) && value > 0) return value;
        var b = style.bounds_pt || [0, 0, 0, 0];
        return Math.abs(Number(b[1]) - Number(b[3]));
    }

    function fontConfig(config, name) {
        var font = config.font_options && config.font_options[String(name)];
        if (!font) throw new Error("Font config not found: " + name);
        if (font.type !== "text") throw new Error("Font config is not text: " + name);
        return font;
    }

    function applyFontConfig(tf, font) {
        var attr = tf.textRange.characterAttributes;
        attr.size = Number(font.font_size_pt || 48);
        try { attr.tracking = Number(font.tracking || 0); } catch (e1) {}
        try { attr.horizontalScale = Number(font.horizontal_scale || 100); } catch (e2) {}
        try { attr.verticalScale = Number(font.vertical_scale || 100); } catch (e3) {}
        applyFont(tf, String(font.font_name || font.font_family || ""));
    }

    function renderDesignAssetItem(layer, item, rect, fontStyle) {
        var assetPath = String(item.design_asset || "");
        if (!assetPath) throw new Error("Design asset missing for: " + item.font_option);
        var assetFile = File(assetPath);
        if (!assetFile.exists) throw new Error("Design asset not found: " + assetPath);
        var designDoc = app.open(assetFile);
        var groupName = String(item.design_group || item.font_option || "");
        var sourceGroup = findPageItemByName(designDoc, groupName);
        if (!sourceGroup) {
            designDoc.close(SaveOptions.DONOTSAVECHANGES);
            throw new Error("Design group not found: " + groupName);
        }
        var instances = normalizeDesignInstances(item);
        var copy = null;
        if (instances.length > 1) {
            copy = layer.groupItems.add();
            try { copy.name = groupName + "_instances"; } catch (eN0) {}
            var children = [];
            for (var i = 0; i < instances.length; i++) {
                children.push(duplicateDesignInstance(sourceGroup, layer, copy, instances[i], fontStyle, item.font_option));
            }
            arrangeDesignInstances(children);
        } else {
            copy = duplicateDesignInstance(sourceGroup, layer, null, instances[0], fontStyle, item.font_option);
        }
        designDoc.close(SaveOptions.DONOTSAVECHANGES);
        fitPageItemToRect(copy, rect);
        outlineTextFrames(copy);
        cleanupOutline(copy);
        recordFitDelta(fitPageItemToRect(copy, rect));
        return copy;
    }

    function normalizeDesignInstances(item) {
        var instances = item.design_instances || [];
        if (instances.length) return instances;
        var parts = item.text_parts || [];
        if (!parts.length && item.text) parts = String(item.text).split("|");
        return [parts];
    }

    function duplicateDesignInstance(sourceGroup, layer, container, parts, fontStyle, fontOption) {
        var copy = sourceGroup.duplicate(layer, ElementPlacement.PLACEATEND);
        if (container) {
            try { copy.move(container, ElementPlacement.PLACEATEND); } catch (eM0) {}
        }
        removeDiagnosticFrames(copy);
        replaceDesignTexts(copy, parts || []);
        applyDesignTextAlignment(copy, fontOption);
        applyFontBoldnessToTextFrames(copy, fontStyle);
        return copy;
    }

    function arrangeDesignInstances(items) {
        if (!items || items.length <= 1) return;
        var maxWidth = 0;
        var maxHeight = 0;
        var minLeft = null;
        var top = null;
        for (var i = 0; i < items.length; i++) {
            var b = safeGeometricBounds(items[i]);
            if (!b) continue;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            maxWidth = Math.max(maxWidth, w);
            maxHeight = Math.max(maxHeight, h);
            minLeft = minLeft === null ? b[0] : Math.min(minLeft, b[0]);
            top = top === null ? b[1] : Math.max(top, b[1]);
        }
        if (minLeft === null || top === null) return;
        var gap = Math.max(maxHeight * 0.18, mmToPt(3));
        var centerX = minLeft + maxWidth / 2;
        var cursorTop = top;
        for (var j = 0; j < items.length; j++) {
            var bounds = safeGeometricBounds(items[j]);
            if (!bounds) continue;
            var height = Math.abs(bounds[1] - bounds[3]);
            var itemCenterX = (bounds[0] + bounds[2]) / 2;
            items[j].translate(centerX - itemCenterX, cursorTop - bounds[1]);
            cursorTop -= height + gap;
        }
    }

    function applyDesignTextAlignment(root, fontOption) {
        var option = String(fontOption || "").toUpperCase();
        if (option !== "F11" && option !== "F12") return;
        var frames = [];
        collectTextFrames(root, frames);
        var primary = findTextFrameByName(frames, "Text1");
        var secondary = findTextFrameByName(frames, "Text2");
        if (!primary || !secondary) return;
        try { app.redraw(); } catch (e0) {}
        var pb = safeVisibleBounds(primary);
        var sb = safeVisibleBounds(secondary);
        if (!pb || !sb) return;
        var primaryWidth = Math.abs(pb[2] - pb[0]);
        if (primaryWidth <= 0) return;
        var desiredGap = Math.max(mmToPt(1), Math.min(primaryWidth * 0.18, mmToPt(6)));
        var shiftX = 0;
        var currentGap = sb[0] - pb[2];
        if (currentGap > desiredGap) shiftX = (pb[2] + desiredGap) - sb[0];
        var primaryCenter = (pb[0] + pb[2]) / 2;
        var secondaryCenter = (sb[0] + sb[2]) / 2;
        if (option === "F11") {
            var targetCenter = primaryCenter + Math.min(primaryWidth * 0.12, mmToPt(8));
            secondary.translate(targetCenter - secondaryCenter, 0);
            return;
        }
        var maxCenterDelta = Math.max(primaryWidth * 0.35, mmToPt(4));
        if (secondaryCenter - primaryCenter > maxCenterDelta) {
            var centerShift = (primaryCenter + maxCenterDelta) - secondaryCenter;
            shiftX = shiftX === 0 ? centerShift : Math.min(shiftX, centerShift);
        }
        if (shiftX !== 0) secondary.translate(shiftX, 0);
    }

    function safeVisibleBounds(item) {
        try {
            var b = item.visibleBounds;
            return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
        } catch (e0) {
            return null;
        }
    }

    function removeDiagnosticFrames(root) {
        var rootBounds = safeGeometricBounds(root);
        removeDiagnosticFramesInContainer(root, rootBounds);
    }

    function removeDiagnosticFramesInContainer(item, rootBounds) {
        if (!item || !item.pageItems) return;
        for (var i = item.pageItems.length - 1; i >= 0; i--) {
            var child = item.pageItems[i];
            removeDiagnosticFramesInContainer(child, rootBounds);
            if (isDiagnosticFrame(child, rootBounds)) {
                try { child.remove(); } catch (e0) {}
            }
        }
    }

    function isDiagnosticFrame(item, rootBounds) {
        var type = String(item && item.typename || "");
        if (type !== "PathItem" && type !== "CompoundPathItem") return false;
        var name = String(item.name || "").toLowerCase();
        var namedFrame = name.indexOf("_box") >= 0 || name.indexOf("box") >= 0 || name.indexOf("frame") >= 0 || name.indexOf("bounds") >= 0;
        if (namedFrame) return true;
        if (!isUnfilledStrokedRed(item)) return false;
        return isLargeFrame(item, rootBounds);
    }

    function isUnfilledStrokedRed(item) {
        try {
            if (item.filled === true) return false;
            if (item.stroked !== true) return false;
            return isRedLikeColor(item.strokeColor);
        } catch (e0) {
            return false;
        }
    }

    function isRedLikeColor(color) {
        if (!color) return false;
        var type = String(color.typename || "");
        if (type === "RGBColor") {
            return Number(color.red) >= 180 && Number(color.green) <= 140 && Number(color.blue) <= 170;
        }
        if (type === "CMYKColor") {
            return Number(color.magenta) >= 70 && Number(color.yellow) >= 50 && Number(color.cyan) <= 30 && Number(color.black) <= 30;
        }
        if (type === "SpotColor") {
            return isRedLikeColor(color.spot && color.spot.color);
        }
        return false;
    }

    function isLargeFrame(item, rootBounds) {
        if (!rootBounds) return true;
        var b = safeGeometricBounds(item);
        if (!b) return false;
        var itemWidth = Math.abs(b[2] - b[0]);
        var itemHeight = Math.abs(b[1] - b[3]);
        var rootWidth = Math.abs(rootBounds[2] - rootBounds[0]);
        var rootHeight = Math.abs(rootBounds[1] - rootBounds[3]);
        if (rootWidth <= 0 || rootHeight <= 0) return false;
        return itemWidth >= rootWidth * 0.65 && itemHeight >= rootHeight * 0.65;
    }

    function safeGeometricBounds(item) {
        try {
            var b = item.geometricBounds;
            return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
        } catch (e0) {
            return null;
        }
    }

    function replaceDesignTexts(root, parts) {
        var frames = [];
        collectTextFrames(root, frames);
        for (var i = 0; i < parts.length; i++) {
            var slotName = "Text" + (i + 1);
            var frame = findTextFrameByName(frames, slotName);
            if (!frame && i < frames.length) frame = frames[i];
            if (frame) frame.contents = String(parts[i] || "");
        }
    }

    function applyFontBoldnessToTextFrames(root, style) {
        var frames = [];
        collectTextFrames(root, frames);
        for (var i = 0; i < frames.length; i++) applyFontBoldness(frames[i], style);
    }

    function findTextFrameByName(frames, name) {
        var target = String(name || "").toLowerCase();
        for (var i = 0; i < frames.length; i++) {
            if (String(frames[i].name || "").toLowerCase() === target) return frames[i];
        }
        return null;
    }

    function collectTextFrames(item, out) {
        if (!item) return;
        if (item.typename === "TextFrame") {
            out.push(item);
            return;
        }
        if (!item.pageItems) return;
        for (var i = 0; i < item.pageItems.length; i++) collectTextFrames(item.pageItems[i], out);
    }

    function outlineTextFrames(item) {
        var frames = [];
        collectTextFrames(item, frames);
        for (var i = frames.length - 1; i >= 0; i--) {
            try {
                var outlined = frames[i].createOutline();
                cleanupOutline(outlined);
            } catch (e) {}
        }
    }

    function findPageItemByName(doc, name) {
        for (var l = 0; l < doc.layers.length; l++) {
            var found = findInContainer(doc.layers[l], name);
            if (found) return found;
        }
        return null;
    }

    function findInContainer(container, name) {
        if (!container.pageItems) return null;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.name === name) return item;
            if (item.pageItems) {
                var found = findInContainer(item, name);
                if (found) return found;
            }
        }
        return null;
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

    function applyColor(tf, name) {
        var rgb = colorMap(String(name || "black"));
        var color = new RGBColor();
        color.red = rgb[0];
        color.green = rgb[1];
        color.blue = rgb[2];
        tf.textRange.characterAttributes.fillColor = color;
    }

    function applyFontBoldness(tf, style) {
        var boldness = Number(style && style.boldness);
        if (isNaN(boldness) || boldness <= 0) return;
        var attributes = tf.textRange.characterAttributes;
        try { attributes.strokeColor = attributes.fillColor; } catch (e1) {}
        try { attributes.strokeWeight = boldness; } catch (e2) {
            try { attributes.strokeWidth = boldness; } catch (e3) {}
        }
    }

    function colorMap(name) {
        var key = name.toLowerCase();
        var map = {
            "black": [0, 0, 0],
            "white": [255, 255, 255],
            "red": [255, 0, 0],
            "blue": [0, 102, 204],
            "gold": [212, 175, 55]
        };
        return map[key] || map.black;
    }

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        var bestSize = fitMaxFontSize(tf, maxW, maxH, minSize, maxSize);
        tf.textRange.characterAttributes.size = bestSize;
        try { app.redraw(); } catch (e0) {}

        var bounds = tf.visibleBounds;
        var cx = (left + right) / 2;
        var cy = (top + bottom) / 2;
        var tx = cx - (bounds[0] + bounds[2]) / 2;
        var ty = cy - (bounds[1] + bounds[3]) / 2;
        tf.translate(tx, ty);
    }

    function renderOutlinedTextToRect(tf, rect, minSize, maxSize) {
        var size = Math.min(Math.max(tf.textRange.characterAttributes.size, minSize), maxSize);
        tf.textRange.characterAttributes.size = size;
        try { app.redraw(); } catch (e0) {}
        var outline = tf.createOutline();
        fitPageItemToRect(outline, rect);
        cleanupOutline(outline);
        recordFitDelta(fitPageItemToRect(outline, rect));
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

    function fitPageItemToRect(item, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var targetW = right - left;
        var targetH = top - bottom;
        for (var i = 0; i < 6; i++) {
            try { app.redraw(); } catch (e0) {}
            var b = item.geometricBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) return;
            var scaleX = (targetW / w) * 100;
            var scaleY = (targetH / h) * 100;
            try {
                item.resize(scaleX, scaleY, true, true, true, true, 100, Transformation.CENTER);
            } catch (e1) {
                try { item.resize(scaleX, scaleY); } catch (e2) {}
            }
            alignPageItemToRect(item, rect);
        }
        return boundsDelta(item, rect);
    }

    function recordFitDelta(delta) {
        fitStats.count += 1;
        if (!isNaN(delta)) fitStats.maxDeltaPt = Math.max(fitStats.maxDeltaPt, delta);
    }

    function boundsDelta(item, rect) {
        var b = item.geometricBounds;
        return Math.max(
            Math.abs(b[0] - rect[0]),
            Math.abs(b[1] - rect[1]),
            Math.abs(b[2] - rect[2]),
            Math.abs(b[3] - rect[3])
        );
    }

    function alignPageItemToRect(item, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var b = item.geometricBounds;
        item.translate(left - b[0], top - b[1]);
    }

    function outlineAndClean(items) {
        for (var i = 0; i < items.length; i++) {
            try {
                var outline = items[i].createOutline();
                cleanupOutline(outline);
            } catch (e) {}
        }
    }

    function cleanupOutline(item) {
        if (!item) return;
        try { app.executeMenuCommand("deselectall"); } catch (e0) {}
        try {
            item.selected = true;
            app.executeMenuCommand("Live Pathfinder Add");
            app.executeMenuCommand("expandStyle");
        } catch (e1) {
            try { item.selected = false; } catch (e2) {}
        }
    }

    function saveAsAI8(doc, file) {
        var opts = new IllustratorSaveOptions();
        opts.compatibility = Compatibility.ILLUSTRATOR8;
        opts.pdfCompatible = false;
        opts.compressed = false;
        doc.saveAs(file, opts);
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

    function numberOrDefault(value, fallback) {
        var number = Number(value);
        return isNaN(number) ? fallback : number;
    }
}());
