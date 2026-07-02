#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    if (task.type !== "template_text_sheet") throw new Error("Unsupported task type: " + task.type);
    if (!task.items || task.items.length === 0) throw new Error("No sheet items");

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}

    var templateDoc = app.open(File(String(task.template_ai)));
    var styles = collectStyleBounds(templateDoc, task.items);
    var fonts = collectFonts(templateDoc, task.items);

    var layout = task.layout || {};
    var columns = Math.max(Number(layout.columns || 4), 1);
    var gap = mmToPt(Number(layout.gap_mm || 8));
    var margin = mmToPt(Number(layout.margin_mm || 8));
    var labelHeight = mmToPt(Number(layout.label_height_mm || 4));
    var labelFontSize = Number(layout.label_font_size_pt || 7);
    var padding = mmToPt(Number(task.fit && task.fit.padding_mm || 1));
    var minFontSize = Number(task.fit && task.fit.min_font_size_pt || 4);
    var maxFontSize = Number(task.fit && task.fit.max_font_size_pt || 300);

    var maxCellWidth = 0;
    var maxCellHeight = 0;
    for (var s in styles) {
        if (!styles.hasOwnProperty(s)) continue;
        maxCellWidth = Math.max(maxCellWidth, styles[s].width);
        maxCellHeight = Math.max(maxCellHeight, styles[s].height + labelHeight);
    }

    var rows = Math.ceil(task.items.length / columns);
    var docWidth = margin * 2 + columns * maxCellWidth + (columns - 1) * gap;
    var docHeight = margin * 2 + rows * maxCellHeight + (rows - 1) * gap;
    var doc = app.documents.add(DocumentColorSpace.RGB, docWidth, docHeight);
    var layer = doc.layers[0];
    layer.name = "COMBINED_OUTPUT";

    var outlines = [];
    for (var i = 0; i < task.items.length; i++) {
        var item = task.items[i];
        var style = styles[String(item.style_option)];
        var fontSource = fonts[String(item.font_option)];
        if (!style) throw new Error("Style not found: " + item.style_option);
        if (!fontSource) throw new Error("Font not found: " + item.font_option);

        var col = i % columns;
        var row = Math.floor(i / columns);
        var cellLeft = margin + col * (maxCellWidth + gap);
        var cellTop = docHeight - margin - row * (maxCellHeight + gap);
        var boxLeft = cellLeft + (maxCellWidth - style.width) / 2;
        var boxTop = cellTop - labelHeight;
        var boxRight = boxLeft + style.width;
        var boxBottom = boxTop - style.height;

        var label = layer.textFrames.add();
        label.contents = labelText(item);
        label.textRange.characterAttributes.size = labelFontSize;
        applyColor(label, "black");
        fitLabel(label, [boxLeft, cellTop, boxRight, cellTop - labelHeight], 4, labelFontSize);
        outlines.push(label);

        var tf = layer.textFrames.add();
        tf.contents = String(item.text || "");
        copyTextStyle(fontSource, tf);
        applyColor(tf, String(task.style && task.style.color_name || "black"));
        fitTextToRect(tf, [boxLeft + padding, boxTop - padding, boxRight - padding, boxBottom + padding], minFontSize, maxFontSize);
        outlines.push(tf);
    }

    templateDoc.close(SaveOptions.DONOTSAVECHANGES);

    if (task.export && task.export.outline_text) {
        outlineAndClean(outlines);
    }

    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAsAI8(doc, output);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function collectStyleBounds(doc, items) {
        var result = {};
        for (var i = 0; i < items.length; i++) {
            var name = String(items[i].style_option);
            if (result[name]) continue;
            var styleItem = findPageItemByName(doc, name);
            if (!styleItem) throw new Error("Style option not found: " + name);
            var b = visibleBounds(styleItem);
            result[name] = { width: Math.abs(b[2] - b[0]), height: Math.abs(b[1] - b[3]) };
        }
        return result;
    }

    function collectFonts(doc, items) {
        var result = {};
        for (var i = 0; i < items.length; i++) {
            var name = String(items[i].font_option);
            if (result[name]) continue;
            var fontItem = findPageItemByName(doc, name);
            if (!fontItem) throw new Error("Font option not found: " + name);
            var tf = firstTextFrame(fontItem);
            if (!tf) throw new Error("Font option has no editable text: " + name);
            result[name] = tf;
        }
        return result;
    }

    function labelText(item) {
        var text = String(item.order_no || "");
        if (item.quantity_index && Number(item.quantity_index) > 1) text += "-" + item.quantity_index;
        return text;
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("Task file not found: " + path);
        file.encoding = "UTF-8";
        file.open("r");
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
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

    function firstTextFrame(item) {
        if (!item) return null;
        if (item.typename === "TextFrame") return item;
        if (!item.pageItems) return null;
        for (var i = 0; i < item.pageItems.length; i++) {
            var found = firstTextFrame(item.pageItems[i]);
            if (found) return found;
        }
        return null;
    }

    function visibleBounds(item) {
        var b = item.visibleBounds;
        return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
    }

    function copyTextStyle(source, target) {
        var src = source.textRange.characterAttributes;
        var dst = target.textRange.characterAttributes;
        try { dst.textFont = src.textFont; } catch (e1) {}
        try { dst.size = src.size; } catch (e2) {}
        try { dst.tracking = src.tracking; } catch (e3) {}
        try { dst.horizontalScale = src.horizontalScale; } catch (e4) {}
        try { dst.verticalScale = src.verticalScale; } catch (e5) {}
        try { dst.fillColor = src.fillColor; } catch (e6) {}
        try {
            target.textRange.paragraphAttributes.justification = source.textRange.paragraphAttributes.justification;
        } catch (e7) {}
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

    function fitLabel(tf, rect, minSize, maxSize) {
        tf.textRange.characterAttributes.size = maxSize;
        fitTextToRect(tf, rect, minSize, maxSize);
    }

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        tf.textRange.characterAttributes.size = Math.min(tf.textRange.characterAttributes.size, maxSize);

        for (var grow = 0; grow < 80; grow++) {
            var gb = tf.visibleBounds;
            var gw = Math.abs(gb[2] - gb[0]);
            var gh = Math.abs(gb[1] - gb[3]);
            var current = tf.textRange.characterAttributes.size;
            if (gw >= maxW * 0.92 || gh >= maxH * 0.92 || current >= maxSize) break;
            tf.textRange.characterAttributes.size = Math.min(maxSize, current * 1.08);
        }

        for (var shrink = 0; shrink < 120; shrink++) {
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            var currentSize = tf.textRange.characterAttributes.size;
            if ((w <= maxW && h <= maxH) || currentSize <= minSize) break;
            tf.textRange.characterAttributes.size = Math.max(minSize, currentSize * Math.min(maxW / w, maxH / h) * 0.96);
        }

        var bounds = tf.visibleBounds;
        var cx = (left + right) / 2;
        var cy = (top + bottom) / 2;
        var tx = cx - (bounds[0] + bounds[2]) / 2;
        var ty = cy - (bounds[1] + bounds[3]) / 2;
        tf.translate(tx, ty);
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
