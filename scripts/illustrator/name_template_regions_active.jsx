(function () {
    try {
        function q(value) {
            if (value === null || value === undefined) return "null";
            return "\"" + String(value)
                .replace(/\\/g, "\\\\")
                .replace(/"/g, "\\\"")
                .replace(/\r/g, "\\r")
                .replace(/\n/g, "\\n") + "\"";
        }

        function writeText(file, text) {
            file.encoding = "UTF-8";
            if (!file.open("w")) throw new Error("Cannot write: " + file.fsName);
            file.write(text);
            file.close();
        }

        function trim(value) {
            return String(value || "").replace(/^\s+|\s+$/g, "");
        }

        function compact(value) {
            return trim(value).replace(/\s+/g, "");
        }

        function textOf(item) {
            if (item.typename !== "TextFrame") return "";
            return trim(item.contents || "").replace(/\s+/g, " ");
        }

        function compactTextOf(item) {
            return compact(textOf(item));
        }

        function bounds(item) {
            var b = item.visibleBounds;
            return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
        }

        function width(b) { return Math.abs(b.right - b.left); }
        function height(b) { return Math.abs(b.top - b.bottom); }
        function area(b) { return width(b) * height(b); }
        function centerX(b) { return (b.left + b.right) / 2; }
        function centerY(b) { return (b.top + b.bottom) / 2; }

        function contains(outer, inner) {
            var pad = 1;
            return inner.left >= outer.left - pad &&
                inner.right <= outer.right + pad &&
                Math.min(inner.top, inner.bottom) >= Math.min(outer.top, outer.bottom) - pad &&
                Math.max(inner.top, inner.bottom) <= Math.max(outer.top, outer.bottom) + pad;
        }

        function ensureGroup(doc, name) {
            for (var i = 0; i < doc.groupItems.length; i++) {
                if (doc.groupItems[i].name === name) return doc.groupItems[i];
            }
            var group = doc.groupItems.add();
            group.name = name;
            return group;
        }

        function unlockItem(item) {
            try { item.locked = false; } catch (err) {}
            try { item.hidden = false; } catch (err2) {}
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

        function collectNonTextItems(container, out) {
            for (var i = 0; i < container.pageItems.length; i++) {
                var item = container.pageItems[i];
                if (item.typename === "TextFrame") continue;
                out.push(item);
                if (item.typename === "GroupItem") collectNonTextItems(item, out);
            }
        }

        function groupText(group) {
            var frames = [];
            collectTextFrames(group, frames);
            var parts = [];
            for (var i = 0; i < frames.length; i++) {
                var t = textOf(frames[i]);
                if (t) parts.push(t);
            }
            return parts.join(" ");
        }

        function renameVisibleLabels(doc, lines) {
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                var text = compactTextOf(tf);
                var fontMatch = /^F([1-9]|1[0-2])$/i.exec(text);
                if (fontMatch) {
                    tf.name = "F" + fontMatch[1] + "_LABEL";
                    lines.push(line("label", tf.name, tf, textOf(tf)));
                    continue;
                }
                var styleMatch = /^Style([1-5])$/i.exec(text) || /^Style([1-5])$/i.exec(compact(tf.name));
                if (styleMatch) {
                    tf.name = "Style" + styleMatch[1] + "_LABEL";
                    lines.push(line("label", tf.name, tf, textOf(tf)));
                }
            }
        }

        function candidateDesignGroups(doc) {
            var groups = [];
            for (var i = 0; i < doc.groupItems.length; i++) {
                var group = doc.groupItems[i];
                var text = groupText(group);
                if (!text) continue;
                if (!/Bride|BRIDESMAID|Mrs\.|EMILY|\d{1,2}\.\d{1,2}\.\d{2,4}/i.test(text)) continue;
                var b;
                try { b = bounds(group); } catch (err) { continue; }
                groups.push({ item: group, text: text, bounds: b, area: area(b) });
            }
            groups.sort(function (a, b) { return a.area - b.area; });

            var picked = [];
            for (var p = 0; p < groups.length && picked.length < 3; p++) {
                var duplicate = false;
                for (var j = 0; j < picked.length; j++) {
                    if (contains(groups[p].bounds, picked[j].bounds) || contains(picked[j].bounds, groups[p].bounds)) {
                        duplicate = true;
                        break;
                    }
                }
                if (!duplicate) picked.push(groups[p]);
            }
            picked.sort(function (a, b) { return centerY(b.bounds) - centerY(a.bounds); });
            return picked;
        }

        function simpleFontFrames(doc, designGroups) {
            var frames = [];
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                if (textOf(tf) !== "Sophia") continue;
                var b;
                try { b = bounds(tf); } catch (err) { continue; }
                var inDesign = false;
                for (var d = 0; d < designGroups.length; d++) {
                    if (contains(designGroups[d].bounds, b)) {
                        inDesign = true;
                        break;
                    }
                }
                if (!inDesign) frames.push({ item: tf, text: textOf(tf), bounds: b });
            }
            frames.sort(function (a, b) {
                var ax = centerX(a.bounds), bx = centerX(b.bounds);
                if (Math.abs(ax - bx) > 25) return ax - bx;
                return centerY(b.bounds) - centerY(a.bounds);
            });
            return frames;
        }

        function nameDesignInternals(group) {
            var frames = [];
            collectTextFrames(group, frames);
            frames.sort(function (a, b) { return centerY(bounds(b)) - centerY(bounds(a)); });
            if (frames.length >= 1) frames[0].name = "Text1";
            if (frames.length >= 2) frames[frames.length - 1].name = "Text2";
            for (var i = 1; i < frames.length - 1; i++) {
                frames[i].name = "TextExtra" + i;
            }

            var fixed = [];
            collectNonTextItems(group, fixed);
            var n = 1;
            for (var f = 0; f < fixed.length; f++) {
                try { fixed[f].name = "FixedDesign" + n; n++; } catch (err) {}
            }
        }

        function isLikelyDrawingRect(item) {
            if (item.typename !== "PathItem") return false;
            try {
                if (!item.closed || item.pathPoints.length !== 4) return false;
                var b = bounds(item);
                return width(b) > 25 && height(b) > 25 && area(b) > 1200;
            } catch (err) {
                return false;
            }
        }

        function findStyleLabels(doc) {
            var labels = [];
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                var textMatch = /^Style([1-5])(?:_LABEL)?$/i.exec(compactTextOf(tf));
                var nameMatch = /^Style([1-5])(?:_LABEL)?$/i.exec(compact(tf.name));
                var match = textMatch || nameMatch;
                if (!match) continue;
                labels.push({ name: "Style" + match[1], item: tf, bounds: bounds(tf) });
            }
            labels.sort(function (a, b) {
                return parseInt(a.name.replace("Style", ""), 10) - parseInt(b.name.replace("Style", ""), 10);
            });
            return labels;
        }

        function findRectForLabel(rects, label, used) {
            var lb = label.bounds;
            var lx = centerX(lb);
            var best = null;
            var bestScore = Number.MAX_VALUE;
            for (var i = 0; i < rects.length; i++) {
                if (used[i]) continue;
                var rb = rects[i].bounds;
                var rx = centerX(rb);
                var dx = Math.abs(rx - lx);
                if (dx > Math.max(width(rb), width(lb))) continue;
                var gap1 = Math.abs(rb.bottom - lb.top);
                var gap2 = Math.abs(rb.top - lb.bottom);
                var gap = Math.min(gap1, gap2);
                var score = dx * 3 + gap;
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

        if (app.documents.length === 0) {
            throw new Error("Please open the template AI document first.");
        }

        try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (err) {}

        var doc = app.activeDocument;
        for (var layerIndex = 0; layerIndex < doc.layers.length; layerIndex++) {
            unlockItem(doc.layers[layerIndex]);
        }

        var lines = [];
        renameVisibleLabels(doc, lines);

        var fontGroup = ensureGroup(doc, "\u5b57\u4f53\u533a");
        var designGroups = candidateDesignGroups(doc);
        var simpleFrames = simpleFontFrames(doc, designGroups);
        if (simpleFrames.length < 9) {
            throw new Error("Need 9 simple Sophia font text frames, found " + simpleFrames.length);
        }
        if (designGroups.length < 3) {
            throw new Error("Need 3 design groups for F10-F12, found " + designGroups.length);
        }

        for (var s = 0; s < 9; s++) {
            var fontName = "F" + (s + 1);
            unlockItem(simpleFrames[s].item);
            simpleFrames[s].item.name = fontName;
            simpleFrames[s].item.move(fontGroup, ElementPlacement.PLACEATEND);
            lines.push(line("font_text", fontName, simpleFrames[s].item, simpleFrames[s].text));
        }

        for (var d = 0; d < 3; d++) {
            var designName = "F" + (d + 10);
            unlockItem(designGroups[d].item);
            designGroups[d].item.name = designName;
            nameDesignInternals(designGroups[d].item);
            designGroups[d].item.move(fontGroup, ElementPlacement.PLACEATEND);
            lines.push(line("font_design_group", designName, designGroups[d].item, designGroups[d].text));
        }

        var labels = findStyleLabels(doc);
        if (labels.length < 5) {
            throw new Error("Need Style1-Style5 labels, found " + labels.length);
        }
        var rects = [];
        for (var p = 0; p < doc.pathItems.length; p++) {
            if (isLikelyDrawingRect(doc.pathItems[p])) {
                rects.push({ item: doc.pathItems[p], bounds: bounds(doc.pathItems[p]) });
            }
        }

        var artGroup = ensureGroup(doc, "\u4f5c\u56fe\u533a");
        var used = {};
        for (var l = 0; l < labels.length; l++) {
            var match = findRectForLabel(rects, labels[l], used);
            if (!match) throw new Error("Cannot find drawing rectangle for " + labels[l].name);
            used[match.index] = true;
            labels[l].item.name = labels[l].name + "_LABEL";
            unlockItem(match.item);
            match.item.name = labels[l].name;
            match.item.move(artGroup, ElementPlacement.PLACEATEND);
            lines.push(line("art_zone", labels[l].name, match.item, ""));
        }

        var outDir = Folder("C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\output\\template-named\\JJMB202603281027102517");
        if (!outDir.exists) outDir.create();
        writeText(File(outDir.fsName + "\\template-regions-active-report.jsonl"), lines.join("\n"));

        alert("NAME_TEMPLATE_REGIONS_ACTIVE_OK");
        return "NAME_TEMPLATE_REGIONS_ACTIVE_OK";
    } catch (err) {
        alert("NAME_TEMPLATE_REGIONS_ACTIVE_ERROR: " + err + " line=" + (err.line || ""));
        return "NAME_TEMPLATE_REGIONS_ACTIVE_ERROR: " + err + " line=" + (err.line || "");
    }
}());
