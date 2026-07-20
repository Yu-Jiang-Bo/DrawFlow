#target illustrator
#targetengine "template_annotator_panel_v2"

(function () {
    var TITLE = "\u6a21\u677f\u6807\u6ce8\u9762\u677f v2";
    var DEFAULT_REGION = "\u5b57\u4f53\u533a";

    function trim(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "");
    }

    function compact(value) {
        return trim(value).replace(/\s+/g, "");
    }

    function fail(message) {
        throw new Error(message);
    }

    function doc() {
        try {
            if (app.documents.length < 1) fail("\u8bf7\u5148\u6253\u5f00 AI \u6587\u6863");
            return app.activeDocument;
        } catch (e1) {
            try {
                return app.documents[0];
            } catch (e2) {
                fail("\u8bf7\u5148\u6253\u5f00 AI \u6587\u6863");
            }
        }
    }

    function selection() {
        var sel = null;
        try { sel = doc().selection; } catch (e1) {}
        if (!sel || sel.length < 1) {
            try { sel = app.selection; } catch (e2) {}
        }
        if (!sel || sel.length < 1) fail("\u8bf7\u5148\u9009\u4e2d\u5bf9\u8c61");
        return sel;
    }

    function unlock(item) {
        try { item.locked = false; } catch (e1) {}
        try { item.hidden = false; } catch (e2) {}
    }

    function getBounds(item) {
        var b = item.visibleBounds;
        return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
    }

    function centerX(item) {
        var b = getBounds(item);
        return (b.left + b.right) / 2;
    }

    function centerY(item) {
        var b = getBounds(item);
        return (b.top + b.bottom) / 2;
    }

    function textValue(item) {
        if (!item || item.typename !== "TextFrame") return "";
        return compact(item.contents || "");
    }

    function ensureGroup(parent, name) {
        for (var i = 0; i < parent.groupItems.length; i++) {
            if (parent.groupItems[i].name === name) return parent.groupItems[i];
        }
        var group = parent.groupItems.add();
        group.name = name;
        return group;
    }

    function collectPageItems(container, out) {
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            out.push(item);
            if (item.typename === "GroupItem") collectPageItems(item, out);
        }
    }

    function collectTextFrames(container, out) {
        for (var i = 0; i < container.textFrames.length; i++) out.push(container.textFrames[i]);
    }

    function groupSelection(name) {
        var d = doc();
        var sel = selection();
        if (sel.length === 1 && sel[0].typename === "GroupItem") {
            sel[0].name = name;
            return sel[0];
        }
        var group = d.groupItems.add();
        group.name = name;
        var items = [];
        for (var i = 0; i < sel.length; i++) items.push(sel[i]);
        for (var j = 0; j < items.length; j++) {
            unlock(items[j]);
            items[j].move(group, ElementPlacement.PLACEATEND);
        }
        return group;
    }

    function moveToRegion(item, regionName) {
        var region = ensureGroup(doc(), regionName);
        unlock(item);
        item.move(region, ElementPlacement.PLACEATEND);
    }

    function nameSelection(regionName, itemName) {
        var group = groupSelection(itemName);
        group.name = itemName;
        moveToRegion(group, regionName);
        alert("\u5df2\u547d\u540d: " + itemName);
    }

    function addSelectionToRegion(regionName) {
        var region = ensureGroup(doc(), regionName);
        var sel = selection();
        var items = [];
        for (var i = 0; i < sel.length; i++) items.push(sel[i]);
        for (var j = 0; j < items.length; j++) {
            unlock(items[j]);
            items[j].move(region, ElementPlacement.PLACEATEND);
        }
        alert("\u5df2\u7f16\u5165\u533a\u57df: " + items.length);
    }

    function findLabels(prefix, startNo, endNo) {
        var d = doc();
        var labels = [];
        for (var i = 0; i < d.textFrames.length; i++) {
            var tf = d.textFrames[i];
            var value = textValue(tf);
            for (var n = startNo; n <= endNo; n++) {
                var key = prefix + n;
                if (value === key || compact(tf.name) === key) {
                    labels.push({ number: n, name: key, item: tf });
                    break;
                }
            }
        }
        labels.sort(function (a, b) { return a.number - b.number; });
        return labels;
    }

    function isLabel(item, labels) {
        for (var i = 0; i < labels.length; i++) {
            if (labels[i].item === item) return true;
        }
        return false;
    }

    function collectTargets(mode, labels) {
        var d = doc();
        var targets = [];
        if (mode === "text") {
            for (var t = 0; t < d.textFrames.length; t++) {
                if (!isLabel(d.textFrames[t], labels)) targets.push(d.textFrames[t]);
            }
        } else {
            var all = [];
            collectPageItems(d, all);
            for (var i = 0; i < all.length; i++) {
                if (!isLabel(all[i], labels)) targets.push(all[i]);
            }
        }
        return targets;
    }

    function nearest(labelItem, targets, used) {
        var best = -1;
        var bestScore = Number.MAX_VALUE;
        var lx = centerX(labelItem);
        var ly = centerY(labelItem);
        for (var i = 0; i < targets.length; i++) {
            if (used[i]) continue;
            var dx = Math.abs(centerX(targets[i]) - lx);
            var dy = Math.abs(centerY(targets[i]) - ly);
            var score = dx * 2 + dy;
            if (score < bestScore) {
                bestScore = score;
                best = i;
            }
        }
        return best;
    }

    function autoName(regionName, prefix, startNo, endNo, mode) {
        var labels = findLabels(prefix, startNo, endNo);
        if (labels.length < 1) fail("\u672a\u627e\u5230\u6807\u7b7e");
        var targets = collectTargets(mode, labels);
        var used = {};
        var count = 0;
        for (var i = 0; i < labels.length; i++) {
            var idx = nearest(labels[i].item, targets, used);
            if (idx < 0) continue;
            used[idx] = true;
            labels[i].item.name = labels[i].name + "_LABEL";
            targets[idx].name = labels[i].name;
            moveToRegion(targets[idx], regionName);
            count++;
        }
        alert("\u5df2\u6279\u91cf\u547d\u540d: " + count + " / " + labels.length);
    }

    function checkRegion(regionName) {
        var d = doc();
        var region = null;
        for (var i = 0; i < d.groupItems.length; i++) {
            if (d.groupItems[i].name === regionName) region = d.groupItems[i];
        }
        if (!region) fail("\u533a\u57df\u4e0d\u5b58\u5728: " + regionName);
        alert(regionName + "\nitems: " + region.pageItems.length);
    }

    function parseNum(field, fallback) {
        var n = parseInt(field.text, 10);
        return isNaN(n) ? fallback : n;
    }

    function show() {
        var win = new Window("dialog", TITLE);
        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.spacing = 8;
        win.margins = 12;

        var row1 = win.add("group");
        row1.add("statictext", undefined, "\u533a\u57df");
        var regionInput = row1.add("edittext", undefined, DEFAULT_REGION);
        regionInput.characters = 18;

        var row2 = win.add("group");
        row2.add("statictext", undefined, "\u547d\u540d");
        var nameInput = row2.add("edittext", undefined, "F1");
        nameInput.characters = 10;

        var row3 = win.add("group");
        row3.add("statictext", undefined, "\u524d\u7f00");
        var prefixInput = row3.add("edittext", undefined, "F");
        prefixInput.characters = 5;
        row3.add("statictext", undefined, "\u8303\u56f4");
        var startInput = row3.add("edittext", undefined, "1");
        startInput.characters = 4;
        row3.add("statictext", undefined, "-");
        var endInput = row3.add("edittext", undefined, "10");
        endInput.characters = 4;

        var row4 = win.add("group");
        row4.add("statictext", undefined, "\u5339\u914d\u5bf9\u8c61");
        var modeList = row4.add("dropdownlist", undefined, ["text", "all"]);
        modeList.selection = 0;

        var b1 = win.add("button", undefined, "\u9009\u533a\u547d\u540d\u5e76\u7f16\u5165\u533a\u57df");
        var b2 = win.add("button", undefined, "\u9009\u533a\u7f16\u5165\u533a\u57df");
        var b3 = win.add("button", undefined, "\u6309\u6807\u7b7e\u6279\u91cf\u547d\u540d");
        var b4 = win.add("button", undefined, "\u68c0\u67e5\u533a\u57df");
        var b5 = win.add("button", undefined, "\u5173\u95ed");

        b1.onClick = function () {
            try { nameSelection(regionInput.text, compact(nameInput.text)); } catch (e) { alert("\u9519\u8bef: " + String(e)); }
        };
        b2.onClick = function () {
            try { addSelectionToRegion(regionInput.text); } catch (e) { alert("\u9519\u8bef: " + String(e)); }
        };
        b3.onClick = function () {
            try {
                autoName(regionInput.text, compact(prefixInput.text), parseNum(startInput, 1), parseNum(endInput, 10), modeList.selection.text);
            } catch (e) { alert("\u9519\u8bef: " + String(e)); }
        };
        b4.onClick = function () {
            try { checkRegion(regionInput.text); } catch (e) { alert("\u9519\u8bef: " + String(e)); }
        };
        b5.onClick = function () { win.close(); };

        win.center();
        win.show();
    }

    show();
}());
