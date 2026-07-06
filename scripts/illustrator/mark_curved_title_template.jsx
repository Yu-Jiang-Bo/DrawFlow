#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(File(taskPath));
    var input = File(String(task.input_ai));
    var output = File(String(task.output_ai));
    var reportFile = File(String(task.output_report));
    var maxFontIndex = Number(task.max_font_index || 14);

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var doc = app.open(input);
    var markerLayer = ensureLayer(doc, "AUTO_TITLE_PATHS");
    var labels = collectTitleLabels(doc, maxFontIndex);
    var samples = collectTitleSamples(doc);
    var frames = collectTitleFrames(doc);
    var usedSamples = {};
    var usedFrames = {};
    var entries = [];

    for (var i = 0; i < labels.length; i++) {
        var label = labels[i];
        var fontKey = "F" + label.index;
        var sample = nearestItem(label.item, samples, usedSamples, true);
        var frame = sample ? nearestItem(sample, frames, usedFrames, false) : null;
        if (!sample || !frame) {
            entries.push({
                font_option: fontKey,
                status: "missing_sample_or_frame",
                label_bounds: bounds(label.item)
            });
            continue;
        }

        label.item.name = "TITLE_" + fontKey + "_LABEL";
        sample.name = "TITLE_" + fontKey + "_SAMPLE";
        frame.name = "TITLE_" + fontKey + "_BOUNDS";
        var path = createTitlePath(markerLayer, frame, "TITLE_" + fontKey + "_PATH");

        usedSamples[sample.uuid || sample.name + "_" + i] = true;
        usedFrames[frame.uuid || frame.name + "_" + i] = true;

        entries.push({
            font_option: fontKey,
            status: "ok",
            label_name: label.item.name,
            sample_name: sample.name,
            bounds_name: frame.name,
            path_name: path.name,
            font_name: fontName(sample),
            label_bounds: bounds(label.item),
            sample_bounds: bounds(sample),
            bounds: bounds(frame),
            path_bounds: bounds(path),
            baseline_ratio: baselineRatio(frame)
        });
    }

    ensureFolder(output.parent);
    if (output.exists) output.remove();
    saveAI(doc, output);
    writeText(reportFile, toJson({
        input_ai: input.fsName,
        output_ai: output.fsName,
        count: entries.length,
        entries: entries
    }));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "MARK_CURVED_TITLE_TEMPLATE_OK";

    function collectTitleLabels(doc, maxIndex) {
        var result = [];
        for (var i = 0; i < doc.textFrames.length; i++) {
            var tf = doc.textFrames[i];
            var text = String(tf.contents || "").replace(/\s+/g, "");
            var match = /^F(\d+)$/.exec(text);
            if (!match) continue;
            var index = Number(match[1]);
            if (index < 1 || index > maxIndex) continue;
            var c = center(tf);
            if (c.x > 320 || c.y > -80 || c.y < -450) continue;
            result.push({ index: index, item: tf, center: c });
        }
        result.sort(function (a, b) { return a.index - b.index; });
        return result;
    }

    function collectTitleSamples(doc) {
        var result = [];
        for (var i = 0; i < doc.textFrames.length; i++) {
            var tf = doc.textFrames[i];
            var text = String(tf.contents || "");
            if (text !== "Merry Christmas" && text !== "MERRY CHRISTMAS") continue;
            var c = center(tf);
            if (c.x > 410 || c.y > -80 || c.y < -450) continue;
            result.push(tf);
        }
        return result;
    }

    function collectTitleFrames(doc) {
        var result = [];
        for (var i = 0; i < doc.pathItems.length; i++) {
            var item = doc.pathItems[i];
            var b = bounds(item);
            if (!b) continue;
            var width = Math.abs(b[2] - b[0]);
            var height = Math.abs(b[1] - b[3]);
            var cx = (b[0] + b[2]) / 2;
            var cy = (b[1] + b[3]) / 2;
            if (cx > 410 || cy > -80 || cy < -450) continue;
            if (width < 80 || width > 150 || height < 15 || height > 45) continue;
            result.push(item);
        }
        return result;
    }

    function nearestItem(anchorItem, candidates, used, mustBeRight) {
        var ac = center(anchorItem);
        var best = null;
        var bestScore = 999999999;
        for (var i = 0; i < candidates.length; i++) {
            var item = candidates[i];
            var key = item.uuid || item.name + "_" + i;
            if (used[key]) continue;
            var c = center(item);
            if (mustBeRight && c.x <= ac.x) continue;
            var dx = c.x - ac.x;
            var dy = c.y - ac.y;
            if (Math.abs(dy) > 35) continue;
            var score = dx * dx + dy * dy;
            if (score < bestScore) {
                best = item;
                bestScore = score;
            }
        }
        return best;
    }

    function createTitlePath(layer, frame, name) {
        var curve = baselineFromFrame(frame);
        var left = curve.left[0];
        var right = curve.right[0];
        var width = right - left;
        var path = layer.pathItems.add();
        path.name = name;
        path.setEntirePath([curve.left, curve.right]);
        path.closed = false;
        path.filled = false;
        path.stroked = true;
        path.strokeWidth = 0.35;
        var color = new RGBColor();
        color.red = 0;
        color.green = 160;
        color.blue = 255;
        path.strokeColor = color;
        path.pathPoints[0].leftDirection = path.pathPoints[0].anchor;
        path.pathPoints[0].rightDirection = curve.leftHandle || [left + width / 3, curve.mid[1]];
        path.pathPoints[0].pointType = PointType.SMOOTH;
        path.pathPoints[1].leftDirection = curve.rightHandle || [right - width / 3, curve.mid[1]];
        path.pathPoints[1].rightDirection = path.pathPoints[1].anchor;
        path.pathPoints[1].pointType = PointType.SMOOTH;
        return path;
    }

    function baselineFromFrame(frame) {
        var b = bounds(frame);
        var left = b[0];
        var top = b[1];
        var right = b[2];
        var bottom = b[3];
        var width = right - left;
        var cy = (top + bottom) / 2;
        if (frame.pathPoints && frame.pathPoints.length >= 9) {
            var pts = frame.pathPoints;
            var leftPoint = midpoint(pts[3].anchor, pts[6].anchor);
            var midPoint = midpoint(pts[2].anchor, pts[7].anchor);
            var rightPoint = midpoint(pts[1].anchor, pts[8].anchor);
            return {
                left: leftPoint,
                mid: midPoint,
                right: rightPoint,
                leftHandle: [leftPoint[0] + (rightPoint[0] - leftPoint[0]) / 3, midPoint[1]],
                rightHandle: [rightPoint[0] - (rightPoint[0] - leftPoint[0]) / 3, midPoint[1]]
            };
        }
        return {
            left: [left, cy],
            mid: [(left + right) / 2, cy - width * 0.08],
            right: [right, cy],
            leftHandle: [left + width / 3, cy - width * 0.08],
            rightHandle: [right - width / 3, cy - width * 0.08]
        };
    }

    function baselineRatio(frame) {
        var b = bounds(frame);
        var curve = baselineFromFrame(frame);
        return {
            left: pointRatio(curve.left, b),
            mid: pointRatio(curve.mid, b),
            right: pointRatio(curve.right, b),
            leftHandle: pointRatio(curve.leftHandle, b),
            rightHandle: pointRatio(curve.rightHandle, b)
        };
    }

    function midpoint(a, b) {
        return [(Number(a[0]) + Number(b[0])) / 2, (Number(a[1]) + Number(b[1])) / 2];
    }

    function pointRatio(point, b) {
        var width = Number(b[2]) - Number(b[0]);
        var height = Number(b[1]) - Number(b[3]);
        return [
            (Number(point[0]) - Number(b[0])) / width,
            (Number(b[1]) - Number(point[1])) / height
        ];
    }

    function ensureLayer(doc, name) {
        for (var i = 0; i < doc.layers.length; i++) {
            if (doc.layers[i].name === name) return doc.layers[i];
        }
        var layer = doc.layers.add();
        layer.name = name;
        return layer;
    }

    function center(item) {
        var b = bounds(item);
        return { x: (b[0] + b[2]) / 2, y: (b[1] + b[3]) / 2 };
    }

    function bounds(item) {
        try {
            var b = item.visibleBounds;
            return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
        } catch (e1) {
            return null;
        }
    }

    function fontName(tf) {
        try { return String(tf.textRange.characterAttributes.textFont.name); } catch (e1) {}
        return "";
    }

    function readJSON(file) {
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open task: " + file.fsName);
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }

    function writeText(file, text) {
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write: " + file.fsName);
        file.write(text);
        file.close();
    }

    function saveAI(doc, file) {
        var opts = new IllustratorSaveOptions();
        opts.pdfCompatible = true;
        doc.saveAs(file, opts);
    }

    function ensureFolder(folder) {
        if (!folder.exists) {
            ensureFolder(folder.parent);
            folder.create();
        }
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
}());
