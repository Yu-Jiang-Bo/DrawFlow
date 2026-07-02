#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    if (task.type !== "template_text") throw new Error("Unsupported task type: " + task.type);

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}

    var templateDoc = app.open(File(String(task.template_ai)));
    var fontItem = findPageItemByName(templateDoc, String(task.font_option));
    var styleItem = findPageItemByName(templateDoc, String(task.style_option));
    if (!fontItem) throw new Error("Font option not found: " + task.font_option);
    if (!styleItem) throw new Error("Style option not found: " + task.style_option);

    var sourceText = firstTextFrame(fontItem);
    if (!sourceText) throw new Error("Font option has no editable text: " + task.font_option);

    var styleBounds = visibleBounds(styleItem);
    var widthPt = Math.abs(styleBounds[2] - styleBounds[0]);
    var heightPt = Math.abs(styleBounds[1] - styleBounds[3]);
    if (widthPt <= 0 || heightPt <= 0) throw new Error("Invalid style bounds: " + task.style_option);

    var attrs = sourceText.textRange.characterAttributes;
    var doc = app.documents.add(DocumentColorSpace.RGB, widthPt, heightPt);
    var layer = doc.layers[0];
    layer.name = "OUTPUT";

    var textFrame = layer.textFrames.add();
    textFrame.contents = String(task.text || "");
    copyTextStyle(sourceText, textFrame);
    applyColor(textFrame, String(task.style && task.style.color_name || "black"));

    var initialSize = Math.max(Number(attrs.size || 48), 12);
    textFrame.textRange.characterAttributes.size = initialSize;

    var padding = mmToPt(Number(task.fit && task.fit.padding_mm || 1));
    var rect = [padding, heightPt - padding, widthPt - padding, padding];
    fitTextToRect(textFrame, rect, Number(task.fit && task.fit.min_font_size_pt || 4), Number(task.fit && task.fit.max_font_size_pt || 300));

    if (task.export && task.export.outline_text) {
        try { textFrame.createOutline(); } catch (outlineError) {}
    }

    templateDoc.close(SaveOptions.DONOTSAVECHANGES);

    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAsAI8(doc, output);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

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
            if (item.typename === "GroupItem" || item.typename === "Layer") {
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

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        var size = tf.textRange.characterAttributes.size;
        tf.textRange.characterAttributes.size = Math.min(size, maxSize);

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
