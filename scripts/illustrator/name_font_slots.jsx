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

    function bounds(item) {
        var b = item.visibleBounds;
        return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
    }

    function area(b) {
        return Math.abs((b.right - b.left) * (b.top - b.bottom));
    }

    function centerX(b) {
        return (b.left + b.right) / 2;
    }

    function contains(outer, inner) {
        var pad = 0.5;
        return inner.left >= outer.left - pad &&
            inner.right <= outer.right + pad &&
            inner.top <= outer.top + pad &&
            inner.bottom >= outer.bottom - pad;
    }

    function collectText(group, texts) {
        for (var i = 0; i < group.pageItems.length; i++) {
            var item = group.pageItems[i];
            if (item.typename === "TextFrame") {
                texts.push(item);
            } else if (item.typename === "GroupItem") {
                collectText(item, texts);
            }
        }
    }

    function groupText(group) {
        var texts = [];
        collectText(group, texts);
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

    function reportLine(kind, name, item, text) {
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
    var designGroups = candidateDesignGroups(doc);
    var simpleFrames = simpleFontFrames(doc, designGroups);
    var lines = [];

    if (simpleFrames.length < 9) {
        throw new Error("Expected at least 9 simple Sophia text frames, found " + simpleFrames.length);
    }
    if (designGroups.length < 3) {
        throw new Error("Expected 3 design groups for F10-F12, found " + designGroups.length);
    }

    for (var s = 0; s < 9; s++) {
        var simpleName = "F" + (s + 1);
        simpleFrames[s].item.name = simpleName;
        lines.push(reportLine("text", simpleName, simpleFrames[s].item, simpleFrames[s].text));
    }

    for (var d = 0; d < 3; d++) {
        var designName = "F" + (d + 10);
        designGroups[d].item.name = designName;
        lines.push(reportLine("group", designName, designGroups[d].item, designGroups[d].text));
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
    return "NAME_FONT_SLOTS_OK";
    } catch (err) {
        return "NAME_FONT_SLOTS_ERROR: " + err + " line=" + (err.line || "");
    }
}());
