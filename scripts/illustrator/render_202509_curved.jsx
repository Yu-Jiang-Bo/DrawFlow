#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(File(taskPath));
    if (task.type !== "jjmb_202509_curved") throw new Error("Unsupported task type: " + task.type);

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var layout = task.layout || {};
    var fit = task.fit || {};
    var outputConfig = task.output || {};
    var colorMode = outputColorMode(outputConfig.color_mode);
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
    var keepNameFrames = layout.keep_name_frames === true;
    var pathfinderMerge = outputConfig.pathfinder_merge !== false;
    var cleanupStats = { attempted: 0, failed: 0 };
    var OUTLINE_BATCH_SIZE = 25;
    var FIT_ITERATIONS = 2;
    var renderProgress = { stage: "layout", totalTextItems: 0, processedTextItems: 0 };
    var minFontSize = Number(fit.min_font_size_pt || 4);
    var maxFontSize = Number(fit.max_font_size_pt || 80);
    var padding = mmToPt(Number(fit.padding_mm || 0.2));

    var groups = task.groups || [];
    if (groups.length === 0) throw new Error("No groups");
    var renderedItems = 0;
    var totalItems = totalTaskItems(groups);
    writeProgress(task, renderedItems, totalItems, "正在渲染条目");
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

    var doc = app.documents.add(documentColorSpace(colorMode), docWidth, docHeight);
    var layer = doc.layers[0];
    layer.name = "JJMB202509231236046265_OUTPUT";
    var textItems = [];
    var pathItems = [];
    var nameFrameItems = [];
    var titleFrameItems = [];
    var titleTemplateInfo = loadTitleTemplate(task.title_template || {});
    var titleTemplateStats = { loaded: titleTemplateInfo ? true : false, used: 0, fallback: 0 };
    try { app.activeDocument = doc; } catch (e0) {}

    try {
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
                    if (!drawCurvedTitleFromTemplate(layer, String(item.text || ""), String(item.font_option || ""), itemLeft, itemTop, width, heightForItem, textItems, titleFrameItems)) {
                        titleTemplateStats.fallback += 1;
                        drawCurvedTitle(layer, String(item.text || ""), font, itemLeft, itemTop, width, heightForItem, textItems, pathItems, titleFrameItems);
                    }
                } else {
                    drawName(layer, String(item.text || ""), font, itemLeft, itemTop, width, heightForItem, textItems, nameFrameItems);
                }
                cursorTop = itemBottom - itemGap;
                renderedItems += 1;
                writeProgress(task, renderedItems, totalItems, "正在渲染条目");
            }
        }
    } catch (eLayout) {
        abortRenderUnexpected(eLayout);
    }

    renderProgress.totalTextItems = textItems.length;
    if (outputConfig.outline_text) {
        renderProgress.stage = "outlining";
        writeProgress(task, renderedItems, totalItems, "正在转曲文字 0/" + textItems.length);
        writeRenderDebug("outlining", "", 0);
        outlineText(textItems);
        writeProgress(task, renderedItems, totalItems, "正在清理辅助对象");
        removeItems(pathItems);
    }
    if (!keepNameFrames) {
        writeProgress(task, renderedItems, totalItems, "正在清理姓名辅助框");
        removeItems(nameFrameItems);
    }
    if (!keepTitleFrames) {
        writeProgress(task, renderedItems, totalItems, "正在清理标题辅助框");
        removeItems(titleFrameItems);
    }

    var output = File(String(task.output_ai));
    try {
        renderProgress.stage = "saving";
        writeProgress(task, renderedItems, totalItems, "正在保存 AI 文件");
        writeRenderDebug("saving", "", 0);
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        saveAsAI8(doc, output);
        writeProgress(task, renderedItems, totalItems, "正在关闭 Illustrator 文档");
        doc.close(SaveOptions.DONOTSAVECHANGES);
        doc = null;
        closeTitleTemplate();

        var previewPath = String(outputConfig.preview_png_path || "");
        if (previewPath) {
            var preview = File(previewPath);
            ensureFolder(preview.parent);
            if (preview.exists) preview.remove();
            // Illustrator appends .png for ExportType.PNG24. Supply an
            // extension-free target so the report path remains candidate.png.
            var previewExport = File(previewPath.replace(/\.png$/i, ""));
            var savedDoc = null;
            try {
                writeProgress(task, renderedItems, totalItems, "正在导出预览 PNG");
                savedDoc = app.open(output);
                exportPreviewPNG(savedDoc, previewExport, Number(outputConfig.preview_dpi || 300));
            } finally {
                if (savedDoc) {
                    writeProgress(task, renderedItems, totalItems, "正在关闭预览文档");
                    try { savedDoc.close(SaveOptions.DONOTSAVECHANGES); } catch (e0) {}
                }
            }
            if (!preview.exists) throw new Error("Preview PNG was not generated.");
        }
        renderProgress.stage = "completed";
        writeProgress(task, renderedItems, totalItems, "正在完成收尾");
        writeRenderDebug("completed", "", 0);
        closeTitleTemplate();
    } catch (e1) {
        failRender("Failed to save AI or export preview: " + String(e1), 0);
    }
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
        textItems.push({ item: tf });
    }

    function drawName(layer, text, font, left, top, width, height, textItems, nameFrameItems) {
        var rect = [left, top, left + width, top - height];
        var frame = drawDebugRect(layer, "NAME_DEBUG_BOUNDS", left, top, width, height);
        nameFrameItems.push(frame);
        var tf = layer.textFrames.add();
        tf.contents = text;
        applyFont(tf, font.font_name);
        applyBlack(tf);
        tf.textRange.characterAttributes.size = 18;
        fitTextToRect(tf, [left + padding, top - padding, left + width - padding, top - height + padding], minFontSize, maxFontSize);
        textItems.push({ item: tf, rect: rect, exactFit: true });
    }

    function drawCurvedTitleFromTemplate(layer, text, fontOption, left, top, width, height, textItems, titleFrameItems) {
        if (!titleTemplateInfo) return false;
        var option = String(fontOption || "").toUpperCase();
        if (!option) return false;
        var sourceText = findNamedPageItem(titleTemplateInfo.doc, patternName(titleTemplateInfo.textPattern, option));
        if (!sourceText) return false;

        var frameRect = [left, top, left + width, top - height];
        var fitRect = [left + padding, top - padding, left + width - padding, top - height + padding];
        var sourceBounds = findNamedPageItem(titleTemplateInfo.doc, patternName(titleTemplateInfo.boundsPattern, option));
        if (sourceBounds) {
            try {
                var frame = sourceBounds.duplicate(layer, ElementPlacement.PLACEATEND);
                frame.name = "TITLE_DEBUG_BOUNDS";
                fitPageItemToRect(frame, frameRect);
                titleFrameItems.push(frame);
            } catch (e1) {}
        } else {
            var fallbackFrame = drawFallbackTitleFrame(layer, left, top, width, height);
            titleFrameItems.push(fallbackFrame);
        }

        try {
            var clonedText = sourceText.duplicate(layer, ElementPlacement.PLACEATEND);
            clonedText.name = "TITLE_RENDER_TEMPLATE_" + option;
            if (!setTextContents(clonedText, text)) {
                try { clonedText.remove(); } catch (e2) {}
                return false;
            }
            applyBlackToPageItem(clonedText);
            fitPageItemWithinRect(clonedText, fitRect);
            textItems.push({ item: clonedText, rect: frameRect, fitMode: "contain" });
            titleTemplateStats.used += 1;
            return true;
        } catch (e3) {
            return false;
        }
    }

    function loadTitleTemplate(config) {
        var aiPath = String(config.ai_path || "");
        if (!aiPath) return null;
        var file = File(aiPath);
        if (!file.exists) return null;
        try {
            var sourceDoc = app.open(file);
            return {
                doc: sourceDoc,
                textPattern: String(config.text_name_pattern || "TITLE_{font}_TEXT"),
                boundsPattern: String(config.bounds_name_pattern || "TITLE_{font}_BOUNDS")
            };
        } catch (e0) {
            return null;
        }
    }

    function closeTitleTemplate() {
        if (!titleTemplateInfo || !titleTemplateInfo.doc) return;
        try { titleTemplateInfo.doc.close(SaveOptions.DONOTSAVECHANGES); } catch (e0) {}
        titleTemplateInfo = null;
    }

    function patternName(pattern, fontOption) {
        return String(pattern || "").replace(/\{font\}/g, fontOption);
    }

    function findNamedPageItem(container, name) {
        if (!container || !name) return null;
        try {
            if (container.name === name) return container;
        } catch (e0) {}
        var directCollections = ["pageItems", "textFrames", "pathItems", "compoundPathItems"];
        for (var d = 0; d < directCollections.length; d++) {
            try {
                var direct = container[directCollections[d]].getByName(name);
                if (direct) return direct;
            } catch (e1) {}
        }
        var collections = ["layers", "groupItems"];
        for (var c = 0; c < collections.length; c++) {
            var items = null;
            try { items = container[collections[c]]; } catch (e2) {}
            if (!items) continue;
            for (var i = 0; i < items.length; i++) {
                var found = findNamedPageItem(items[i], name);
                if (found) return found;
            }
        }
        return null;
    }

    function setTextContents(item, text) {
        if (!item) return false;
        try {
            if (item.typename === "TextFrame") {
                item.contents = text;
                return true;
            }
        } catch (e0) {}
        var changed = false;
        try {
            for (var i = 0; i < item.textFrames.length; i++) {
                item.textFrames[i].contents = text;
                changed = true;
            }
        } catch (e1) {}
        try {
            for (var g = 0; g < item.groupItems.length; g++) {
                changed = setTextContents(item.groupItems[g], text) || changed;
            }
        } catch (e2) {}
        return changed;
    }

    function applyBlackToPageItem(item) {
        if (!item) return;
        try {
            if (item.typename === "TextFrame") {
                applyBlack(item);
                return;
            }
        } catch (e0) {}
        try {
            for (var i = 0; i < item.textFrames.length; i++) applyBlack(item.textFrames[i]);
        } catch (e1) {}
        try {
            for (var g = 0; g < item.groupItems.length; g++) applyBlackToPageItem(item.groupItems[g]);
        } catch (e2) {}
    }

    function drawCurvedTitle(layer, text, font, left, top, width, height, textItems, pathItems, titleFrameItems) {
        var frameRect = [left, top, left + width, top - height];
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
        applyCenterParagraph(tf);
        tf.textRange.characterAttributes.size = Math.max(minFontSize, Math.min(maxFontSize, titleSize));
        fitTitleTextToRect(tf, fitRect, minFontSize, Math.max(minFontSize, Math.min(maxFontSize, titleSize)));
        textItems.push({ item: tf, rect: frameRect, fitMode: "contain" });
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
        return drawDebugRect(layer, "TITLE_DEBUG_BOUNDS", left, top, width, height);
    }

    function drawDebugRect(layer, name, left, top, width, height) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.name = name;
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

    function fitTitleTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        var currentSize = Math.min(Number(tf.textRange.characterAttributes.size || maxSize), maxSize);
        tf.textRange.characterAttributes.size = currentSize;

        for (var shrink = 0; shrink < 140; shrink++) {
            centerTextHorizontally(tf, rect);
            clampTextToRect(tf, rect);
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            currentSize = Number(tf.textRange.characterAttributes.size);
            var inside = b[0] >= left - 0.01 && b[2] <= right + 0.01 && b[1] <= top + 0.01 && b[3] >= bottom - 0.01;
            if ((inside && w <= maxW && h <= maxH) || currentSize <= minSize + 0.01) break;

            var ratio = 1;
            if (w > 0) ratio = Math.min(ratio, maxW / w);
            if (h > 0) ratio = Math.min(ratio, maxH / h);
            if (ratio > 0.98) ratio = 0.96;
            tf.textRange.characterAttributes.size = Math.max(minSize, currentSize * ratio * 0.94);
        }

        centerTextHorizontally(tf, rect);
        clampTextToRect(tf, rect);
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

    function centerTextHorizontally(tf, rect) {
        var left = rect[0], right = rect[2];
        var bounds = tf.visibleBounds;
        var cx = (left + right) / 2;
        var tx = cx - (bounds[0] + bounds[2]) / 2;
        try { tf.translate(tx, 0); } catch (e0) {}
    }

    function clampTextToRect(tf, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var bounds = tf.visibleBounds;
        var tx = 0;
        var ty = 0;
        if (bounds[0] < left) tx = left - bounds[0];
        if (bounds[2] > right) tx = right - bounds[2];
        if (bounds[1] > top) ty = top - bounds[1];
        if (bounds[3] < bottom) ty = bottom - bounds[3];
        if (tx !== 0 || ty !== 0) {
            try { tf.translate(tx, ty); } catch (e0) {}
        }
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

    function applyCenterParagraph(tf) {
        try {
            tf.textRange.paragraphAttributes.justification = Justification.CENTER;
        } catch (e0) {}
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

    function totalTaskItems(groups) {
        var total = 0;
        for (var i = 0; i < groups.length; i++) {
            total += (groups[i].items || []).length;
        }
        return total;
    }

    function outlineText(items) {
        renderProgress.stage = "outlining";
        renderProgress.totalTextItems = items.length;
        for (var i = 0; i < items.length; i++) {
            var entry = items[i];
            var source = entry.item || entry;
            if (!source) failRender("Text outline failed: missing item " + (i + 1), i + 1);
            try {
                var outline = source.createOutline();
                if (!outline) throw new Error("createOutline returned nothing");
                if (entry.exactFit && entry.rect) {
                    fitPageItemToRect(outline, entry.rect);
                } else if (entry.fitMode === "contain" && entry.rect) {
                    fitPageItemWithinRect(outline, entry.rect);
                }
                if (pathfinderMerge) cleanupOutline(outline);
                renderProgress.processedTextItems = i + 1;
                if (shouldSettleOutlineBatch(i + 1, items.length)) {
                    settleIllustrator();
                    writeProgress(task, renderedItems, totalItems, "正在转曲文字 " + (i + 1) + "/" + items.length);
                    writeRenderDebug("outlining", "", 0);
                }
            } catch (e0) {
                failRender("Text outline failed at item " + (i + 1) + ": " + String(e0), i + 1);
            }
        }
    }

    function shouldSettleOutlineBatch(processed, total) {
        return processed === total || processed % OUTLINE_BATCH_SIZE === 0;
    }

    function failRender(message, itemIndex) {
        writeRenderDebug("failed", message, itemIndex);
        closeTitleTemplate();
        try { if (doc) doc.close(SaveOptions.DONOTSAVECHANGES); } catch (e0) {}
        throw new Error(message);
    }

    function abortRenderUnexpected(error) {
        closeTitleTemplate();
        try { if (doc) doc.close(SaveOptions.DONOTSAVECHANGES); } catch (e0) {}
        throw error;
    }

    function writeRenderDebug(status, errorMessage, failedItemIndex) {
        writeDebug(task, {
            groups: groups.length,
            columns: columns,
            docWidth: docWidth,
            docHeight: docHeight,
            columnWidth: columnWidth,
            nameWidth: nameWidth,
            nameHeight: nameHeight,
            titleWidth: titleWidth,
            titleHeight: titleHeight,
            colorMode: colorMode,
            keepNameFrames: keepNameFrames,
            keepTitleFrames: keepTitleFrames,
            titleTemplate: titleTemplateStats,
            pathfinderMerge: pathfinderMerge,
            cleanupStats: cleanupStats,
            stage: renderProgress.stage,
            totalTextItems: renderProgress.totalTextItems,
            processedTextItems: renderProgress.processedTextItems,
            status: status,
            failedItemIndex: failedItemIndex,
            error: errorMessage
        });
    }

    function fitPageItemToRect(item, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var targetW = right - left;
        var targetH = top - bottom;
        for (var i = 0; i < FIT_ITERATIONS; i++) {
            var b = item.geometricBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) return;
            if (Math.abs(targetW - w) < 0.01 && Math.abs(targetH - h) < 0.01) break;
            try {
                item.resize((targetW / w) * 100, (targetH / h) * 100, true, true, true, true, 100, Transformation.CENTER);
            } catch (e1) {
                try { item.resize((targetW / w) * 100, (targetH / h) * 100); } catch (e2) {}
            }
            alignPageItemToRect(item, rect);
        }
    }

    function fitPageItemWithinRect(item, rect) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var targetW = right - left;
        var targetH = top - bottom;
        for (var i = 0; i < FIT_ITERATIONS; i++) {
            var b = pageItemBounds(item);
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) return;
            var ratio = Math.min(targetW / w, targetH / h);
            if (Math.abs(ratio - 1) > 0.001) {
                try {
                    item.resize(ratio * 100, ratio * 100, true, true, true, true, 100, Transformation.CENTER);
                } catch (e1) {
                    try { item.resize(ratio * 100, ratio * 100); } catch (e2) {}
                }
            }
            centerPageItemToRect(item, rect);
            clampPageItemToRect(item, rect);
            if (isPageItemWithinRect(item, rect)) break;
        }
    }

    function pageItemBounds(item) {
        try { return item.visibleBounds; } catch (e0) {}
        return item.geometricBounds;
    }

    function alignPageItemToRect(item, rect) {
        var b = item.geometricBounds;
        item.translate(rect[0] - b[0], rect[1] - b[1]);
    }

    function centerPageItemToRect(item, rect) {
        var b = pageItemBounds(item);
        var cx = (rect[0] + rect[2]) / 2;
        var cy = (rect[1] + rect[3]) / 2;
        try { item.translate(cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2); } catch (e0) {}
    }

    function clampPageItemToRect(item, rect) {
        var b = pageItemBounds(item);
        var tx = 0;
        var ty = 0;
        if (b[0] < rect[0]) tx = rect[0] - b[0];
        if (b[2] > rect[2]) tx = rect[2] - b[2];
        if (b[1] > rect[1]) ty = rect[1] - b[1];
        if (b[3] < rect[3]) ty = rect[3] - b[3];
        if (tx !== 0 || ty !== 0) {
            try { item.translate(tx, ty); } catch (e0) {}
        }
    }

    function isPageItemWithinRect(item, rect) {
        var b = pageItemBounds(item);
        return b[0] >= rect[0] - 0.01 && b[2] <= rect[2] + 0.01 && b[1] <= rect[1] + 0.01 && b[3] >= rect[3] - 0.01;
    }

    function cleanupOutline(item) {
        cleanupStats.attempted += 1;
        try { app.executeMenuCommand("deselectall"); } catch (e0) {}
        try {
            item.selected = true;
            app.executeMenuCommand("Live Pathfinder Add");
            app.executeMenuCommand("expandStyle");
        } catch (e1) {
            cleanupStats.failed += 1;
            throw e1;
        } finally {
            try { app.executeMenuCommand("deselectall"); } catch (e2) {}
        }
    }

    function settleIllustrator() {
        try { app.redraw(); } catch (e0) {}
        try { $.sleep(20); } catch (e1) {}
    }

    function removeItems(items) {
        for (var i = 0; i < items.length; i++) {
            try { items[i].remove(); } catch (e0) {}
        }
    }

    function readJSON(file) {
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open render task JSON.");
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
        try {
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

    function exportPreviewPNG(doc, file, dpi) {
        var opts = new ExportOptionsPNG24();
        var scale = Math.max(1, Number(dpi || 300) / 72 * 100);
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
