#target illustrator

(function () {
    try {
        var DEFAULT_REGION = "\u8bbe\u8ba1\u533a";

        function trim(value) {
            return String(value || "").replace(/^\s+|\s+$/g, "");
        }

        function bounds(item) {
            var b = item.visibleBounds;
            return { left: b[0], top: b[1], right: b[2], bottom: b[3] };
        }

        function centerY(b) {
            return (b.top + b.bottom) / 2;
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

        function collectTextFrames(container, out) {
            if (container.typename === "TextFrame") {
                out.push(container);
                return;
            }
            if (!container.pageItems) return;
            for (var i = 0; i < container.pageItems.length; i++) {
                var item = container.pageItems[i];
                if (item.typename === "TextFrame") out.push(item);
                else if (item.typename === "GroupItem") collectTextFrames(item, out);
            }
        }

        function nameInternals(target) {
            var frames = [];
            collectTextFrames(target, frames);
            frames.sort(function (a, b) {
                return centerY(bounds(b)) - centerY(bounds(a));
            });

            if (frames.length >= 1) frames[0].name = "Text1";
            if (frames.length >= 2) frames[frames.length - 1].name = "Text2";
            for (var i = 1; i < frames.length - 1; i++) {
                frames[i].name = "Text" + (i + 1);
            }

            var fixedNo = 1;
            if (!target.pageItems) return;
            for (var p = 0; p < target.pageItems.length; p++) {
                var item = target.pageItems[p];
                if (item.typename === "TextFrame") continue;
                try {
                    item.name = "FixedDesign" + fixedNo;
                    fixedNo++;
                } catch (err) {}
            }
        }

        function groupSelection(doc, variableName) {
            var sel = app.selection;
            if (!sel || sel.length === 0) {
                throw new Error("No selection. Select design objects first, then run this script.");
            }

            if (sel.length === 1 && sel[0].typename === "GroupItem") {
                unlock(sel[0]);
                sel[0].name = variableName;
                return sel[0];
            }

            var items = [];
            for (var i = 0; i < sel.length; i++) {
                items.push(sel[i]);
            }

            var group = doc.groupItems.add();
            group.name = variableName;
            for (var j = 0; j < items.length; j++) {
                unlock(items[j]);
                items[j].move(group, ElementPlacement.PLACEATEND);
            }
            return group;
        }

        if (app.documents.length === 0) {
            throw new Error("No document.");
        }

        var doc = app.activeDocument;
        var variableName = trim(prompt("Variable name, e.g. D5 / F10 / Style1", "D1"));
        if (!variableName) return;

        var regionName = trim(prompt("Region group name", DEFAULT_REGION));
        if (!regionName) return;

        var split = confirm("Name internal text objects as Text1/Text2/Text3 and fixed art as FixedDesign?");

        var regionGroup = ensureGroup(doc, regionName);
        var target = groupSelection(doc, variableName);
        target.name = variableName;
        if (split) nameInternals(target);
        target.move(regionGroup, ElementPlacement.PLACEATEND);

        alert("MARK_SELECTED_VARIABLE_OK: " + variableName);
    } catch (err) {
        alert("MARK_SELECTED_VARIABLE_ERROR: " + err + " line=" + (err.line || ""));
    }
}());
