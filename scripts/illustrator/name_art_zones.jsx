(function () {
    try {
        function readText(file) {
            file.encoding = "UTF-8";
            if (!file.open("r")) {
                throw new Error("Cannot open task file: " + file.fsName);
            }
            var text = file.read();
            file.close();
            return text;
        }

        function parseJson(text) {
            if (typeof JSON !== "undefined" && JSON.parse) {
                return JSON.parse(text);
            }
            return eval("(" + text + ")");
        }

        function writeText(file, text) {
            file.encoding = "UTF-8";
            if (!file.open("w")) {
                throw new Error("Cannot write output file: " + file.fsName);
            }
            file.write(text);
            file.close();
        }

        function q(value) {
            if (value === null || value === undefined) {
                return "null";
            }
            return "\"" + String(value)
                .replace(/\\/g, "\\\\")
                .replace(/"/g, "\\\"")
                .replace(/\r/g, "\\r")
                .replace(/\n/g, "\\n") + "\"";
        }

        function trimText(value) {
            return String(value || "").replace(/^\s+|\s+$/g, "");
        }

        function textValue(item) {
            return trimText(item.contents || "").replace(/\s+/g, "");
        }

        function bounds(item) {
            var b = item.visibleBounds;
            return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
        }

        function width(b) {
            return Math.abs(b.right - b.left);
        }

        function height(b) {
            return Math.abs(b.top - b.bottom);
        }

        function centerX(b) {
            return (b.left + b.right) / 2;
        }

        function centerY(b) {
            return (b.top + b.bottom) / 2;
        }

        function area(b) {
            return width(b) * height(b);
        }

        function isLikelyRectangle(item) {
            if (item.typename !== "PathItem") {
                return false;
            }
            if (!item.closed) {
                return false;
            }
            if (item.pathPoints.length !== 4) {
                return false;
            }
            var b = bounds(item);
            return width(b) > 20 && height(b) > 20 && area(b) > 1000;
        }

        function findStyleLabels(doc) {
            var labels = [];
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                var text = textValue(tf);
                var match = /^Style([1-5])$/i.exec(text);
                if (!match) {
                    continue;
                }
                labels.push({
                    name: "Style" + match[1],
                    item: tf,
                    bounds: bounds(tf)
                });
            }
            labels.sort(function (a, b) {
                var n1 = parseInt(a.name.replace("Style", ""), 10);
                var n2 = parseInt(b.name.replace("Style", ""), 10);
                return n1 - n2;
            });
            return labels;
        }

        function findRectForLabel(rects, label, used) {
            var lb = label.bounds;
            var lx = centerX(lb);
            var ly = centerY(lb);
            var best = null;
            var bestScore = Number.MAX_VALUE;

            for (var i = 0; i < rects.length; i++) {
                if (used[i]) {
                    continue;
                }
                var rb = rects[i].bounds;
                var rx = centerX(rb);
                var ry = centerY(rb);

                // The drawing rectangle should sit above its Style label and align horizontally.
                if (ry <= ly) {
                    continue;
                }
                var dx = Math.abs(rx - lx);
                var dy = Math.abs(rb.bottom - lb.top);
                if (dx > width(rb) * 0.8) {
                    continue;
                }
                var score = dx * 2 + dy;
                if (score < bestScore) {
                    bestScore = score;
                    best = { index: i, item: rects[i].item, bounds: rb };
                }
            }
            return best;
        }

        function findExistingGroup(doc, name) {
            for (var i = 0; i < doc.groupItems.length; i++) {
                if (doc.groupItems[i].name === name) {
                    return doc.groupItems[i];
                }
            }
            return null;
        }

        function reportLine(name, rect, label) {
            var rb = bounds(rect);
            var lb = label.bounds;
            return "{\"name\":" + q(name) +
                ",\"rectBounds\":[" + [rb.left, rb.top, rb.right, rb.bottom].join(",") + "]" +
                ",\"labelBounds\":[" + [lb.left, lb.top, lb.right, lb.bottom].join(",") + "]}";
        }

        var taskPath = $.getenv("CUSTOM_RENDER_TASK");
        if (!taskPath) {
            throw new Error("CUSTOM_RENDER_TASK is not set");
        }
        var task = parseJson(readText(File(taskPath)));

        try {
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
        } catch (err) {}

        var doc = app.open(File(task.input_ai));
        var labels = findStyleLabels(doc);
        if (labels.length < 5) {
            throw new Error("Expected Style1-Style5 labels, found " + labels.length);
        }

        var rects = [];
        for (var p = 0; p < doc.pathItems.length; p++) {
            var path = doc.pathItems[p];
            if (!isLikelyRectangle(path)) {
                continue;
            }
            rects.push({ item: path, bounds: bounds(path) });
        }

        var used = {};
        var matched = [];
        var lines = [];
        for (var l = 0; l < labels.length; l++) {
            var match = findRectForLabel(rects, labels[l], used);
            if (!match) {
                throw new Error("Cannot find drawing rectangle for " + labels[l].name);
            }
            used[match.index] = true;
            labels[l].item.name = labels[l].name + "_LABEL";
            match.item.name = labels[l].name;
            matched.push(match.item);
            lines.push(reportLine(labels[l].name, match.item, labels[l]));
        }

        var group = findExistingGroup(doc, "作图区");
        if (!group) {
            group = doc.groupItems.add();
            group.name = "作图区";
        }
        for (var m = 0; m < matched.length; m++) {
            matched[m].move(group, ElementPlacement.PLACEATEND);
        }

        if (task.report_jsonl) {
            writeText(File(task.report_jsonl), lines.join("\n"));
        }

        var target = File(task.output_ai || task.input_ai);
        var saveOptions = new IllustratorSaveOptions();
        saveOptions.pdfCompatible = true;
        saveOptions.compressed = false;
        doc.saveAs(target, saveOptions);
        doc.close(SaveOptions.DONOTSAVECHANGES);
        return "NAME_ART_ZONES_OK";
    } catch (err) {
        return "NAME_ART_ZONES_ERROR: " + err + " line=" + (err.line || "");
    }
}());
