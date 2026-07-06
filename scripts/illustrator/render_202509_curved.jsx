#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(File(taskPath));
    if (task.type !== "jjmb_202509_curved") throw new Error("Unsupported task type: " + task.type);

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var layout = task.layout || {};
    var fit = task.fit || {};
    var columns = Math.max(Number(layout.columns || 5), 1);
    var margin = mmToPt(Number(layout.margin_mm || 8));
    var gap = mmToPt(Number(layout.gap_mm || 18));
    var itemGap = mmToPt(Number(layout.item_gap_mm || 7));
    var orderLabelHeight = mmToPt(Number(layout.order_label_height_mm || 7));
    var orderLabelFontSize = Number(layout.order_label_font_size_pt || 13);
    var nameWidth = mmToPt(Number(layout.name_width_mm || 16));
    var nameHeight = mmToPt(Number(layout.name_height_mm || 5));
    var titleWidth = mmToPt(Number(layout.title_width_mm || 40));
    var titleHeight = mmToPt(Number(layout.title_height_mm || 7));
    var keepTitleFrames = layout.keep_title_frames === true;
    var minFontSize = Number(fit.min_font_size_pt || 4);
    var maxFontSize = Number(fit.max_font_size_pt || 80);
    var padding = mmToPt(Number(fit.padding_mm || 0.2));

    var groups = task.groups || [];
    if (groups.length === 0) throw new Error("No groups");
    var groupMetrics = [];
    var columnWidth = Math.max(titleWidth, nameWidth, mmToPt(35));
    for (var g = 0; g < groups.length; g++) {
        var height = orderLabelHeight;
        var items = groups[g].items || [];
        for (var i = 0; i < items.length; i++) {
            height += itemHeight(items[i]) + itemGap;
        }
        if (items.length > 0) height -= itemGap;
        groupMetrics.push({ width: columnWidth, height: height });
    }

    var placements = compactPlacements(groupMetrics, columns, gap);
    var maxColumnHeight = 0;
    for (var h = 0; h < placements.columnHeights.length; h++) {
        maxColumnHeight = Math.max(maxColumnHeight, placements.columnHeights[h]);
    }
    if (maxColumnHeight > 0) maxColumnHeight -= gap;
    var docWidth = margin * 2 + columns * columnWidth + (columns - 1) * gap;
    var docHeight = margin * 2 + maxColumnHeight;

    var doc = app.documents.add(DocumentColorSpace.RGB, docWidth, docHeight);
    var layer = doc.layers[0];
    layer.name = "JJMB202509231236046265_OUTPUT";
    var textItems = [];
    var pathItems = [];
    var titleFrameItems = [];

    for (var gi = 0; gi < groups.length; gi++) {
        var group = groups[gi];
        var col = placements.items[gi].column;
        var left = margin + col * (columnWidth + gap);
        var top = docHeight - margin - placements.items[gi].y;
        var cursorTop = top;
        drawOrderLabel(layer, String(group.order_no || ""), left, cursorTop, left + columnWidth, cursorTop - orderLabelHeight, orderLabelFontSize, textItems);
        cursorTop -= orderLabelHeight;

        var groupItems = group.items || [];
        for (var ii = 0; ii < groupItems.length; ii++) {
            var item = groupItems[ii];
            var font = fontConfig(task.font_map, item.font_option);
            var width = item.text_type === "title" ? titleWidth : nameWidth;
            var heightForItem = itemHeight(item);
            var itemLeft = left + (columnWidth - width) / 2;
            var itemTop = cursorTop;
            var itemBottom = itemTop - heightForItem;
            if (item.text_type === "title") {
                drawCurvedTitle(layer, String(item.text || ""), font, itemLeft, itemTop, width, heightForItem, textItems, pathItems, titleFrameItems);
            } else {
                drawName(layer, String(item.text || ""), font, itemLeft, itemTop, width, heightForItem, textItems);
            }
            cursorTop = itemBottom - itemGap;
        }
    }

    writeDebug(task, {
        groups: groups.length,
        columns: columns,
        docWidth: docWidth,
        docHeight: docHeight,
        columnWidth: columnWidth,
        nameWidth: nameWidth,
        nameHeight: nameHeight,
        titleWidth: titleWidth,
        titleHeight: titleHeight
    });

    if (task.output && task.output.outline_text) {
        outlineText(textItems);
        removeItems(pathItems);
    }
    if (!keepTitleFrames) removeItems(titleFrameItems);

    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAsAI8(doc, output);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function itemHeight(item) {
        return item.text_type === "title" ? titleHeight : nameHeight;
    }

    function drawOrderLabel(layer, text, left, top, right, bottom, size, textItems) {
        var tf = layer.textFrames.add();
        tf.contents = text;
        tf.textRange.characterAttributes.size = size;
        applyBlack(tf);
        fitTextToRect(tf, [left, top, right, bottom], 5, size);
        textItems.push(tf);
    }

    function drawName(layer, text, font, left, top, width, height, textItems) {
        var tf = layer.textFrames.add();
        tf.contents = text;
        applyFont(tf, font.font_name);
        applyBlack(tf);
        tf.textRange.characterAttributes.size = 18;
        fitTextToRect(tf, [left + padding, top - padding, left + width - padding, top - height + padding], minFontSize, maxFontSize);
        textItems.push(tf);
    }

    function drawCurvedTitle(layer, text, font, left, top, width, height, textItems, pathItems, titleFrameItems) {
        var fitRect = [left + padding, top - padding, left + width - padding, top - height + padding];
        var titleSize = measurePointTextSize(layer, text, font, fitRect, 16) * 0.82;
        var titleFrame = drawTitleFrame(layer, font.bounds_shape_ratio, left, top, width, height);
        if (titleFrame) titleFrameItems.push(titleFrame);
        var curve = scaledCurve(font.baseline_ratio, left, top, width, height);
        var path = layer.pathItems.add();
        path.name = "TITLE_RENDER_PATH";
        path.setEntirePath([curve.left, curve.right]);
        path.closed = false;
        path.filled = false;
        path.stroked = false;
        path.pathPoints[0].leftDirection = path.pathPoints[0].anchor;
        path.pathPoints[0].rightDirection = curve.leftHandle;
        path.pathPoints[0].pointType = PointType.SMOOTH;
        path.pathPoints[1].leftDirection = curve.rightHandle;
        path.pathPoints[1].rightDirection = path.pathPoints[1].anchor;
        path.pathPoints[1].pointType = PointType.SMOOTH;
        pathItems.push(path);

        var tf = null;
        try {
            tf = layer.textFrames.pathText(path);
        } catch (e1) {
            try { tf = app.activeDocument.textFrames.pathText(path); } catch (e2) {}
        }
        if (!tf) {
            tf = layer.textFrames.add();
            tf.translate(left, top - height / 2);
        }
        tf.contents = text;
        applyFont(tf, font.font_name);
        applyBlack(tf);
        tf.textRange.characterAttributes.size = Math.max(minFontSize, Math.min(maxFontSize, titleSize));
        centerTextToRect(tf, fitRect);
        textItems.push(tf);
    }

    function drawTitleFrame(layer, shape, left, top, width, height) {
        if (!shape || !shape.points || shape.points.length < 2) {
            return drawFallbackTitleFrame(layer, left, top, width, height);
        }
        var path = layer.pathItems.add();
        path.name = "TITLE_DEBUG_BOUNDS";
        var anchors = [];
        for (var i = 0; i < shape.points.length; i++) {
            anchors.push(ratioPoint(shape.points[i].anchor, left, top, width, height));
        }
        path.setEntirePath(anchors);
        path.closed = shape.closed === true;
        path.filled = false;
        path.stroked = true;
        path.strokeWidth = 0.25;
        path.strokeColor = redColor();
        for (var p = 0; p < path.pathPoints.length && p < shape.points.length; p++) {
            path.pathPoints[p].leftDirection = ratioPoint(shape.points[p].left, left, top, width, height);
            path.pathPoints[p].rightDirection = ratioPoint(shape.points[p].right, left, top, width, height);
            path.pathPoints[p].pointType = PointType.SMOOTH;
        }
        return path;
    }

    function drawFallbackTitleFrame(layer, left, top, width, height) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.name = "TITLE_DEBUG_BOUNDS";
        rect.filled = false;
        rect.stroked = true;
        rect.strokeWidth = 0.25;
        rect.strokeColor = redColor();
        return rect;
    }

    function measurePointTextSize(layer, text, font, rect, initialSize) {
        var tf = layer.textFrames.add();
        tf.contents = text;
        applyFont(tf, font.font_name);
        applyBlack(tf);
        tf.textRange.characterAttributes.size = initialSize;
        fitTextToRect(tf, rect, minFontSize, maxFontSize);
        var size = Number(tf.textRange.characterAttributes.size || initialSize);
        try { tf.remove(); } catch (e0) {}
        return size;
    }

    function scaledCurve(ratio, left, top, width, height) {
        if (!ratio || !ratio.left || !ratio.right || !ratio.leftHandle || !ratio.rightHandle) {
            var cy = top - height * 0.45;
            var sag = height * 0.33;
            return {
                left: [left, cy],
                right: [left + width, cy],
                leftHandle: [left + width / 3, cy - sag],
                rightHandle: [left + width * 2 / 3, cy - sag]
            };
        }
        return {
            left: ratioPoint(ratio.left, left, top, width, height),
            right: ratioPoint(ratio.right, left, top, width, height),
            leftHandle: ratioPoint(ratio.leftHandle, left, top, width, height),
            rightHandle: ratioPoint(ratio.rightHandle, left, top, width, height)
        };
    }

    function ratioPoint(point, left, top, width, height) {
        return [
            left + Number(point[0]) * width,
            top - Number(point[1]) * height
        ];
    }

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        var currentSize = Math.min(Number(tf.textRange.characterAttributes.size || 12), maxSize);
        tf.textRange.characterAttributes.size = currentSize;

        for (var grow = 0; grow < 60; grow++) {
            var gb = tf.visibleBounds;
            var gw = Math.abs(gb[2] - gb[0]);
            var gh = Math.abs(gb[1] - gb[3]);
            currentSize = Number(tf.textRange.characterAttributes.size);
            if (gw >= maxW * 0.94 || gh >= maxH * 0.94 || currentSize >= maxSize) break;
            tf.textRange.characterAttributes.size = Math.min(maxSize, currentSize * 1.08);
        }

        for (var shrink = 0; shrink < 120; shrink++) {
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            currentSize = Number(tf.textRange.characterAttributes.size);
            if ((w <= maxW && h <= maxH) || currentSize <= minSize) break;
            tf.textRange.characterAttributes.size = Math.max(minSize, currentSize * Math.min(maxW / w, maxH / h) * 0.96);
        }

        centerTextToRect(tf, rect);
    }

    function centerTextToRect(tf, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var bounds = tf.visibleBounds;
        var cx = (left + right) / 2;
        var cy = (top + bottom) / 2;
        var tx = cx - (bounds[0] + bounds[2]) / 2;
        var ty = cy - (bounds[1] + bounds[3]) / 2;
        try { tf.translate(tx, ty); } catch (e0) {}
    }

    function fontConfig(fontMap, name) {
        var font = fontMap && fontMap[String(name)];
        if (!font) throw new Error("Font missing: " + name);
        return font;
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
        } catch (e0) {}
    }

    function applyBlack(tf) {
        var color = new RGBColor();
        color.red = 0;
        color.green = 0;
        color.blue = 0;
        tf.textRange.characterAttributes.fillColor = color;
    }

    function redColor() {
        var color = new RGBColor();
        color.red = 255;
        color.green = 102;
        color.blue = 102;
        return color;
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

    function outlineText(items) {
        for (var i = 0; i < items.length; i++) {
            try { items[i].createOutline(); } catch (e0) {}
        }
    }

    function removeItems(items) {
        for (var i = 0; i < items.length; i++) {
            try { items[i].remove(); } catch (e0) {}
        }
    }

    function readJSON(file) {
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open JSON: " + file.fsName);
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
        } catch (e0) {}
    }

    function toJson(value) {
        if (value === null) return "null";
        var type = typeof value;
        if (type === "number" || type === "boolean") return String(value);
        if (type === "string") return "\"" + String(value).replace(/\\/g, "\\\\").replace(/"/g, "\\\"").replace(/\r/g, "\\r").replace(/\n/g, "\\n") + "\"";
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
