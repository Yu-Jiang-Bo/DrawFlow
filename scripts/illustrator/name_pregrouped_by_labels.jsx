#target illustrator

(function () {
    try {
        function trim(value) {
            return String(value || "").replace(/^\s+|\s+$/g, "");
        }

        function compact(value) {
            return trim(value).replace(/\s+/g, "");
        }

        function textOf(item) {
            if (!item || item.typename !== "TextFrame") return "";
            return trim(item.contents || "").replace(/\s+/g, " ");
        }

        function bounds(item) {
            var b = item.visibleBounds;
            return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
        }

        function centerX(b) { return (b.left + b.right) / 2; }
        function centerY(b) { return (b.top + b.bottom) / 2; }
        function width(b) { return Math.abs(b.right - b.left); }
        function height(b) { return Math.abs(b.top - b.bottom); }
        function area(b) { return width(b) * height(b); }

        function distance(a, b) {
            var dx = centerX(a) - centerX(b);
            var dy = centerY(a) - centerY(b);
            return Math.sqrt(dx * dx + dy * dy);
        }

        function unlock(item) {
            try { item.locked = false; } catch (err) {}
            try { item.hidden = false; } catch (err2) {}
        }

        function ensureGroup(doc, name) {
            for (var i = 0; i < doc.groupItems.length; i++) {
                if (doc.groupItems[i].name === name) return doc.groupItems[i];
            }
            var group = doc.groupItems.add();
            group.name = name;
            return group;
        }

        function collectTextFrames(item, out) {
            if (item.typename === "TextFrame") {
                out.push(item);
                return;
            }
            if (!item.pageItems) return;
            for (var i = 0; i < item.pageItems.length; i++) {
                collectTextFrames(item.pageItems[i], out);
            }
        }

        function collectNonTextItems(item, out) {
            if (!item.pageItems) return;
            for (var i = 0; i < item.pageItems.length; i++) {
                var child = item.pageItems[i];
                if (child.typename === "TextFrame") continue;
                out.push(child);
                if (child.typename === "GroupItem") {
                    collectNonTextItems(child, out);
                }
            }
        }

        function containsText(item, textFrame) {
            var frames = [];
            collectTextFrames(item, frames);
            for (var i = 0; i < frames.length; i++) {
                if (frames[i] === textFrame) return true;
            }
            return false;
        }

        function isRegionGroup(name) {
            return name === "\u8bbe\u8ba1\u533a" ||
                name === "\u5b57\u4f53\u533a" ||
                name === "\u4f5c\u56fe\u533a";
        }

        function labelRegex(prefix, startNo, endNo) {
            return {
                test: function (value) {
                    var re = new RegExp("^" + prefix + "([0-9]+)(?:_LABEL)?$", "i");
                    var match = re.exec(compact(value));
                    if (!match) return null;
                    var no = parseInt(match[1], 10);
                    if (no < startNo || no > endNo) return null;
                    return prefix + no;
                }
            };
        }

        function findLabels(doc, prefix, startNo, endNo) {
            var labels = [];
            var matcher = labelRegex(prefix, startNo, endNo);
            for (var i = 0; i < doc.textFrames.length; i++) {
                var tf = doc.textFrames[i];
                var labelName = matcher.test(textOf(tf)) || matcher.test(tf.name);
                if (!labelName) continue;
                labels.push({
                    name: labelName,
                    item: tf,
                    bounds: bounds(tf),
                    no: parseInt(labelName.replace(prefix, ""), 10)
                });
            }
            labels.sort(function (a, b) { return a.no - b.no; });
            return labels;
        }

        function findCandidateGroups(doc, labels) {
            var groups = [];
            for (var i = 0; i < doc.groupItems.length; i++) {
                var group = doc.groupItems[i];
                if (isRegionGroup(group.name)) continue;
                var hasLabel = false;
                for (var l = 0; l < labels.length; l++) {
                    if (containsText(group, labels[l].item)) {
                        hasLabel = true;
                        break;
                    }
                }
                if (hasLabel) continue;
                try {
                    var b = bounds(group);
                    if (area(b) < 20) continue;
                    groups.push({ item: group, bounds: b, area: area(b) });
                } catch (err) {}
            }
            groups.sort(function (a, b) { return a.area - b.area; });
            return groups;
        }

        function findNearestGroup(label, groups, used) {
            var best = null;
            var bestScore = Number.MAX_VALUE;
            for (var i = 0; i < groups.length; i++) {
                if (used[i]) continue;
                var g = groups[i];
                var score = distance(label.bounds, g.bounds);

                // Prefer a group above the label, because many templates put D1/D2 below the design.
                if (centerY(g.bounds) > centerY(label.bounds)) score -= 30;

                // Prefer similar horizontal center.
                score += Math.abs(centerX(g.bounds) - centerX(label.bounds)) * 1.5;

                if (score < bestScore) {
                    bestScore = score;
                    best = { index: i, group: g };
                }
            }
            return best;
        }

        function nameDesignInternals(group) {
            var frames = [];
            collectTextFrames(group, frames);
            frames.sort(function (a, b) {
                var ab = bounds(a);
                var bb = bounds(b);
                var ay = centerY(ab);
                var by = centerY(bb);
                if (Math.abs(by - ay) > 8) return by - ay;
                return centerX(ab) - centerX(bb);
            });

            for (var i = 0; i < frames.length; i++) {
                frames[i].name = "Text" + (i + 1);
            }

            var fixed = [];
            collectNonTextItems(group, fixed);
            var fixedNo = 1;
            for (var f = 0; f < fixed.length; f++) {
                try {
                    fixed[f].name = "FixedDesign" + fixedNo;
                    fixedNo++;
                } catch (err) {}
            }
        }

        function processPrefix(doc, prefix, startNo, endNo, regionName, splitInternals) {
            var labels = findLabels(doc, prefix, startNo, endNo);
            if (labels.length === 0) {
                alert("No labels found: " + prefix + startNo + "-" + prefix + endNo);
                return;
            }

            var regionGroup = ensureGroup(doc, regionName);
            var candidates = findCandidateGroups(doc, labels);
            var used = {};
            var renamed = 0;
            var missed = [];

            for (var i = 0; i < labels.length; i++) {
                var match = findNearestGroup(labels[i], candidates, used);
                if (!match) {
                    missed.push(labels[i].name);
                    continue;
                }
                used[match.index] = true;
                unlock(labels[i].item);
                unlock(match.group.item);

                labels[i].item.name = labels[i].name + "_LABEL";
                match.group.item.name = labels[i].name;
                if (splitInternals) nameDesignInternals(match.group.item);
                match.group.item.move(regionGroup, ElementPlacement.PLACEATEND);
                renamed++;
            }

            var msg = "PREGROUPED_LABELS_OK: " + renamed;
            if (missed.length > 0) msg += "\nMissed: " + missed.join(", ");
            alert(msg);
        }

        if (app.documents.length === 0) {
            throw new Error("No document.");
        }

        var doc = app.activeDocument;
        var prefix = trim(prompt("Label prefix, e.g. D / F", "D"));
        if (!prefix) return;

        var startNo = parseInt(prompt("Start number", "1"), 10);
        var endNo = parseInt(prompt("End number", "12"), 10);
        if (isNaN(startNo)) startNo = 1;
        if (isNaN(endNo)) endNo = 12;

        var defaultRegion = prefix.toUpperCase() === "D" ? "\u8bbe\u8ba1\u533a" : "\u5b57\u4f53\u533a";
        var regionName = trim(prompt("Region group name", defaultRegion));
        if (!regionName) return;

        var splitInternals = confirm("Split grouped design internals to Text1/Text2/Text3 and FixedDesign?");
        processPrefix(doc, prefix, startNo, endNo, regionName, splitInternals);
    } catch (err) {
        alert("PREGROUPED_LABELS_ERROR: " + err + " line=" + (err.line || ""));
    }
}());
