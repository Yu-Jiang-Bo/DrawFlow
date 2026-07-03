#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    if (task.type !== "config_grouped_text_sheet") throw new Error("Unsupported task type: " + task.type);
    var config = readJSON(String(task.template_config));
    if (!task.groups || task.groups.length === 0) throw new Error("No order groups");

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}

    var layout = task.layout || {};
    var columns = Math.max(Number(layout.columns || 4), 1);
    var gap = mmToPt(Number(layout.gap_mm || 8));
    var margin = mmToPt(Number(layout.margin_mm || 8));
    var orderLabelHeight = mmToPt(Number(layout.order_label_height_mm || 7));
    var orderLabelFontSize = Number(layout.order_label_font_size_pt || 12);
    var itemGap = mmToPt(Number(layout.item_gap_mm || 4));
    var showStyleBoxes = layout.show_style_boxes !== false;
    var padding = mmToPt(Number(task.fit && task.fit.padding_mm || 1));
    var minFontSize = Number(task.fit && task.fit.min_font_size_pt || 4);
    var maxFontSize = Number(task.fit && task.fit.max_font_size_pt || 300);

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
    writeDebug(task, {
        groups: task.groups.length,
        columns: columns,
        rows: rows,
        maxGroupWidth: maxGroupWidth,
        maxColumnHeight: maxColumnHeight,
        docWidth: docWidth,
        docHeight: docHeight,
        sampleStyle: styleConfig(config, task.groups[0].items[0].style_option)
    });
    var doc = app.documents.add(DocumentColorSpace.RGB, docWidth, docHeight);
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
            var font = fontConfig(config, item.font_option);
            var styleWidth = styleWidthPt(style);
            var styleHeight = styleHeightPt(style);
            var boxLeft = groupLeft + (metric.width - styleWidth) / 2;
            var boxTop = cursorTop;
            var boxRight = boxLeft + styleWidth;
            var boxBottom = boxTop - styleHeight;

            if (showStyleBoxes) drawStyleBox(layer, boxLeft, boxTop, styleWidth, styleHeight, String(item.style_option || ""));

            var tf = layer.textFrames.add();
            tf.contents = String(item.text || "");
            applyFontConfig(tf, font);
            applyColor(tf, String(task.style && task.style.color_name || "black"));
            renderOutlinedTextToRect(tf, [boxLeft + padding, boxTop - padding, boxRight - padding, boxBottom + padding], minFontSize, maxFontSize);
            cursorTop = boxBottom - itemGap;
        }
    }

    if (task.export && task.export.outline_text) outlineAndClean(outlines);

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
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        tf.textRange.characterAttributes.size = fitMaxFontSize(tf, maxW, maxH, minSize, maxSize);
        try { app.redraw(); } catch (e0) {}
        var outline = tf.createOutline();
        cleanupOutline(outline);
        fitPageItemToRect(outline, rect);
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
        for (var i = 0; i < 3; i++) {
            try { app.redraw(); } catch (e0) {}
            var b = item.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) return;
            var scaleX = ((right - left) / w) * 100;
            var scaleY = ((top - bottom) / h) * 100;
            try {
                item.resize(scaleX, scaleY, true, true, true, true, 100, Transformation.CENTER);
            } catch (e1) {
                try { item.resize(scaleX, scaleY); } catch (e2) {}
            }
            centerPageItemInRect(item, rect);
        }
    }

    function centerPageItemInRect(item, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var b = item.visibleBounds;
        var cx = (left + right) / 2;
        var cy = (top + bottom) / 2;
        item.translate(cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2);
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
}());
