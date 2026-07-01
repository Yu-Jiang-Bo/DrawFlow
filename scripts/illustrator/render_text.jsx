#target illustrator

(function () {
    var taskPath = $.getenv('CUSTOM_RENDER_TASK');
    if (!taskPath) throw new Error('缺少 CUSTOM_RENDER_TASK');

    var task = readJSON(taskPath);
    if (task.type !== 'pure_text') throw new Error('不支持的任务类型: ' + task.type);

    var widthPt = Number(task.artboard.width_pt);
    var heightPt = Number(task.artboard.height_pt);
    var doc = app.documents.add(DocumentColorSpace.RGB, widthPt, heightPt);
    var layer = doc.layers[0];
    layer.name = 'PURE_TEXT';

    var textFrame = layer.textFrames.add();
    textFrame.contents = String(task.text || '');
    textFrame.textRange.characterAttributes.size = Number(task.style.font_size_pt || 48);
    applyFont(textFrame, String(task.style.font_name || ''));
    applyColor(textFrame, String(task.style.color_name || 'black'));

    var paddingPt = mmToPt(Number(task.fit.padding_mm || 1));
    fitTextToRect(textFrame, [paddingPt, heightPt - paddingPt, widthPt - paddingPt, paddingPt], Number(task.fit.min_font_size_pt || 4));

    if (task.export && task.export.outline_text) {
        try {
            textFrame.createOutline();
        } catch (outlineError) {}
    }

    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAsAI8(doc, output);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error('任务文件不存在: ' + path);
        file.encoding = 'UTF-8';
        file.open('r');
        var text = file.read();
        file.close();
        if (typeof JSON !== 'undefined' && JSON.parse) {
            return JSON.parse(text);
        }
        return eval('(' + text + ')');
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

    function applyColor(tf, name) {
        var rgb = colorMap(String(name || 'black'));
        var color = new RGBColor();
        color.red = rgb[0];
        color.green = rgb[1];
        color.blue = rgb[2];
        tf.textRange.characterAttributes.fillColor = color;
    }

    function colorMap(name) {
        var key = name.toLowerCase();
        var map = {
            'black': [0, 0, 0], '黑': [0, 0, 0], '黑色': [0, 0, 0],
            'white': [255, 255, 255], '白': [255, 255, 255], '白色': [255, 255, 255],
            'red': [255, 0, 0], '红': [255, 0, 0], '红色': [255, 0, 0],
            'blue': [0, 102, 204], '蓝': [0, 102, 204], '蓝色': [0, 102, 204],
            'gold': [212, 175, 55], '金': [212, 175, 55], '金色': [212, 175, 55]
        };
        return map[key] || map.black;
    }

    function fitTextToRect(tf, rect, minSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        for (var i = 0; i < 80; i++) {
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            var size = tf.textRange.characterAttributes.size;
            if ((w <= maxW && h <= maxH) || size <= minSize) break;
            tf.textRange.characterAttributes.size = Math.max(minSize, size * Math.min(maxW / w, maxH / h) * 0.95);
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
