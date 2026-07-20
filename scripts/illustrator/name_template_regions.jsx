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

        function normalizedText(item) {
            if (item.typename !== "TextFrame") {
                return "";
            }
            return trimText(item.contents || "").replace(/\s+/g, " ");
        }

        function compactText(item) {
            return normalizedText(item).replace(/\s+/g, "");
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

        function contains(outer, inner) {
            var pad = 0.5;
            return inner.left >= outer.left - pad &&
                inner.right <= outer.right + pad &&
                inner.top <= outer.top + pad &&
                inner.bottom >= outer.bottom - pad;
        }

        function findExistingGroup(doc, name) {
            for (var i = 0; i < doc.groupItems.length; i++) {
                if (doc.groupItems[i].name === name) {
                    return doc.groupItems[i];
                }
            }
            return null;
        }

        function ensureGroup(doc, name) {
            var group = findExistingGroup(doc, name);
            if (!group) {
                group = doc.groupItems.add();
                group.name = name;
            }
            return group;
        }

        function collectTextFrames(container, out) {
            for (var i = 0; i < container.pageItems.length; i++) {
                var item = container.pageItems[i];
                if (item.typename === "TextFrame") {
                    out.push(item);
                } else if (item.typename === "GroupItem") {
                    collectTextFrames(item, out);
                }
            }
        }

        function collectFixedItems(container, out) {
            for (var i = 0; i < container.pageItems.length; i++) {
                var item = container.pageItems[i];
                if (item.typename === "TextFrame") {
                    continue;
                }
                if (item.typename === "GroupItem") {
                    out.push(item);
                    collectFixedItems(item, out);
                } else {
                    out.push(item);
                }
            }
        }

        function groupText(group) {
            var texts = [];
            collectTextFrames(group, texts);
            var parts = [];
            for (var i = 0; i < texts.length; i++) {
                var t = normalizedText(texts[i]);
                if (t) {
                    parts.push(t);
                }
            }
            return parts.join(" ");
        }

        function candidateDesignGroups(doc) {
            var groups = [];
            for (var i = 0; i < doc.groupItems.length; i++) {
                var g = doc.groupItems[i];
                var text = groupText(g);
                if (!text) {
                    continue;
                }
                var b;
                try {
                    b = bounds(g);
                } catch (err) {
                    continue;
                }
                var looksLikeDesign = /Bride|BRIDESMAID|Mrs\.|EMILY|\d{1,2}\.\d{1,2}\.\d{2,4}/i.test(text);
                if (!looksLikeDesign) {
                    continue;
                }
                groups.push({ item: g, text: text, bounds: b, area: area(b) });
            }
            groups.sort(function (a, b) {
                return a.area - b.area;
            });

            var picked = [];
            for (var p = 0; p < groups.length && picked.length < 3; p++) {
                var duplicated = false;
                for (var j = 0; j < picked.length; j++) {
                    if (contains(groups[p].bounds, picked[j].bounds) || contains(picked[j].bounds, groups[p].bounds)) {
                        duplicated = true;
                        break;
                    }
                }
                if (!duplicated) {
                    picked.push(groups[p]);
                }
            }

            picked.sort(function (a, b) {
                return b.bounds.top - a.bounds.top;
            });
            return picked;
        }

        function simpleFontFrames(doc, designGroups) {
            var frames = [];
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                var text = normalizedText(tf);
                if (text !== "Sophia") {
                    continue;
                }
                var b;
                try {
                    b = bounds(tf);
                } catch (err) {
                    continue;
                }
                var insideDesign = false;
                for (var d = 0; d < designGroups.length; d++) {
                    if (contains(designGroups[d].bounds, b)) {
                        insideDesign = true;
                        break;
                    }
                }
                if (!insideDesign) {
                    frames.push({ item: tf, text: text, bounds: b });
                }
            }
            frames.sort(function (a, b) {
                var ax = centerX(a.bounds);
                var bx = centerX(b.bounds);
                if (Math.abs(ax - bx) > 25) {
                    return ax - bx;
                }
                return b.bounds.top - a.bounds.top;
            });
            return frames;
        }

        function nameDesignInternals(group) {
            var texts = [];
            collectTextFrames(group, texts);
            texts.sort(function (a, b) {
                return bounds(b).top - bounds(a).top;
            });
            if (texts.length < 2) {
                throw new Error("Design group " + group.name + " expected at least 2 text frames, found " + texts.length);
            }
            texts[0].name = "Text1";
            texts[texts.length - 1].name = "Text2";
            for (var i = 1; i < texts.length - 1; i++) {
                texts[i].name = "TextExtra" + i;
            }

            var fixed = [];
            collectFixedItems(group, fixed);
            var count = 1;
            for (var f = 0; f < fixed.length; f++) {
                try {
                    fixed[f].name = "FixedDesign" + count;
                    count++;
                } catch (err) {}
            }
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
                var match = /^Style([1-5])$/i.exec(compactText(tf));
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
                return parseInt(a.name.replace("Style", ""), 10) - parseInt(b.name.replace("Style", ""), 10);
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

        function line(kind, name, item, text) {
            var b = bounds(item);
            return "{\"kind\":" + q(kind) +
                ",\"name\":" + q(name) +
                ",\"text\":" + q(text || "") +
                ",\"bounds\":[" + [b.left, b.top, b.right, b.bottom].join(",") + "]}";
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
        var lines = [];

        var fontGroup = ensureGroup(doc, "\u5b57\u4f53\u533a");
        var designGroups = candidateDesignGroups(doc);
        var simpleFrames = simpleFontFrames(doc, designGroups);
        if (simpleFrames.length < 9) {
            throw new Error("Expected at least 9 simple Sophia text frames, found " + simpleFrames.length);
        }
        if (designGroups.length < 3) {
            throw new Error("Expected 3 design groups for F10-F12, found " + designGroups.length);
        }

        for (var s = 0; s < 9; s++) {
            var simpleName = "F" + (s + 1);
            simpleFrames[s].item.name = simpleName;
            simpleFrames[s].item.move(fontGroup, ElementPlacement.PLACEATEND);
            lines.push(line("font_text", simpleName, simpleFrames[s].item, simpleFrames[s].text));
        }

        for (var d = 0; d < 3; d++) {
            var designName = "F" + (d + 10);
            designGroups[d].item.name = designName;
            nameDesignInternals(designGroups[d].item);
            designGroups[d].item.move(fontGroup, ElementPlacement.PLACEATEND);
            lines.push(line("font_design_group", designName, designGroups[d].item, designGroups[d].text));
        }

        var artGroup = ensureGroup(doc, "\u4f5c\u56fe\u533a");
        var labels = findStyleLabels(doc);
        if (labels.length < 5) {
            throw new Error("Expected Style1-Style5 labels, found " + labels.length);
        }

        var rects = [];
        for (var p = 0; p < doc.pathItems.length; p++) {
            var path = doc.pathItems[p];
            if (isLikelyRectangle(path)) {
                rects.push({ item: path, bounds: bounds(path) });
            }
        }

        var used = {};
        for (var l = 0; l < labels.length; l++) {
            var match = findRectForLabel(rects, labels[l], used);
            if (!match) {
                throw new Error("Cannot find drawing rectangle for " + labels[l].name);
            }
            used[match.index] = true;
            labels[l].item.name = labels[l].name + "_LABEL";
            match.item.name = labels[l].name;
            match.item.move(artGroup, ElementPlacement.PLACEATEND);
            lines.push(line("art_zone", labels[l].name, match.item, ""));
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
        return "NAME_TEMPLATE_REGIONS_OK";
    } catch (err) {
        return "NAME_TEMPLATE_REGIONS_ERROR: " + err + " line=" + (err.line || "");
    }
}());
