#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "generic_template_rules") throw new Error("Unsupported task type: " + task.type);
    if (!task.orders || !task.orders.length) throw new Error("Generic task has no orders");
    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var outputs = [];
    for (var orderIndex = 0; orderIndex < task.orders.length; orderIndex++) {
        var order = task.orders[orderIndex];
        var doc = app.open(File(String(task.template_ai)));
        try {
            applyOptionGroups(doc, task.option_groups || [], order.selections || {});
            applyVariables(doc, order.variables || [], task.dimensions || {}, task.text_policies || {}, order.selections || {});
            applyAssets(doc, order.assets || []);
            applyTransforms(doc, order.transforms || task.transforms || {}, order.variables || []);
            applyOutputSettings(doc, task.output || {}, order.variables || []);
            var output = File(String(order.output_ai));
            ensureFolder(output.parent);
            if (output.exists) output.remove();
            saveAsAI8(doc, output);
            outputs.push(output.fsName);
        } finally {
            doc.close(SaveOptions.DONOTSAVECHANGES);
        }
    }
    return outputs.join("\n");

    function applyOptionGroups(doc, groups, selections) {
        for (var i = 0; i < groups.length; i++) {
            var group = groups[i] || {};
            var role = String(group.role || "");
            var selected = selectionForRole(role, selections);
            var values = group.values || group.options || [];
            for (var j = 0; j < values.length; j++) {
                var name = String(values[j]);
                var item = findPageItemByName(doc, name);
                if (!item) continue;
                try { item.hidden = Boolean(selected && name !== selected); } catch (e1) {}
                try { item.locked = false; } catch (e2) {}
            }
        }
    }

    function selectionForRole(role, selections) {
        if (role === "font_options") return String(selections.font || "");
        if (role === "design_options") return String(selections.design || "");
        if (role === "style_options") return String(selections.style || "");
        return "";
    }

    function applyVariables(doc, variables, dimensions, policies, selections) {
        var fontSource = firstTextFrame(findPageItemByName(doc, String(selections.font || "")));
        for (var i = 0; i < variables.length; i++) {
            var variable = variables[i];
            var items = findPageItemsByName(doc, String(variable.target || ""));
            if (!items.length) throw new Error("Text target not found: " + variable.target);
            var dimension = dimensions[String(variable.target || "")];
            if (!dimension) dimension = dimensions[String(variable.target || "") + "_ANCHOR"];
            if (!dimension && selections.style) dimension = dimensions[String(selections.style)];
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                var frame = firstTextFrame(items[itemIndex]);
                if (!frame) throw new Error("Target has no editable text: " + variable.target);
                try { frame.locked = false; frame.hidden = false; } catch (e1) {}
                frame.contents = String(variable.value || "");
                if (fontSource) copyTextStyle(fontSource, frame);
                applyTextColor(frame, String(selections.color || ""));
                applyNameAlternatingColors(frame, String(variable.target || ""), String(variable.name_delimiter || "|"));
                if (dimension && String(policies.fit || "") !== "none") {
                    fitText(frame, Number(dimension.width_mm || 0), Number(dimension.height_mm || 0));
                }
            }
        }
    }

    function applyAssets(doc, assets) {
        for (var i = 0; i < assets.length; i++) {
            var entry = assets[i];
            var target = findPageItemByName(doc, String(entry.target || ""));
            if (!target) throw new Error("Asset target not found: " + entry.target);
            var targetBounds = target.visibleBounds;
            var assetDoc = app.open(File(String(entry.asset)));
            try {
                var holder = target.typename === "GroupItem" ? target : target.parent.groupItems.add();
                for (var p = assetDoc.pageItems.length - 1; p >= 0; p--) {
                    assetDoc.pageItems[p].duplicate(holder, ElementPlacement.PLACEATEND);
                }
                centerItem(holder, targetBounds);
            } finally {
                assetDoc.close(SaveOptions.DONOTSAVECHANGES);
            }
        }
    }

    function applyTransforms(doc, transforms, variables) {
        var targets = transforms.targets || [];
        for (var t = 0; t < targets.length; t++) {
            var settings = targets[t] || {};
            var items = findPageItemsByName(doc, String(settings.target || ""));
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                var targetItem = items[itemIndex];
                if (Number(settings.rotation_deg || 0)) {
                    try { targetItem.rotate(Number(settings.rotation_deg)); } catch (e1) {}
                }
                if (Number(settings.scale_percent || 0)) {
                    try { targetItem.resize(Number(settings.scale_percent), Number(settings.scale_percent)); } catch (e2) {}
                }
                var offsetX = mmToPt(Number(settings.offset_x_mm || 0));
                var offsetY = mmToPt(Number(settings.offset_y_mm || 0));
                if (offsetX || offsetY) {
                    try { targetItem.translate(offsetX, offsetY); } catch (e3) {}
                }
            }
        }
        if (transforms.outline_text) {
            for (var i = 0; i < variables.length; i++) {
                var outlineItems = findPageItemsByName(doc, String(variables[i].target || ""));
                for (var outlineIndex = 0; outlineIndex < outlineItems.length; outlineIndex++) {
                    var frame = firstTextFrame(outlineItems[outlineIndex]);
                    if (!frame) continue;
                    try { frame.createOutline(); } catch (e4) {}
                }
            }
        }
    }

    function applyOutputSettings(doc, output, variables) {
        var mode = String(output.color_mode || "").toUpperCase();
        try {
            if (mode === "CMYK") app.executeMenuCommand("doc-color-cmyk");
            if (mode === "RGB") app.executeMenuCommand("doc-color-rgb");
        } catch (e1) {}
        if (output.outline_text) applyTransforms(doc, {outline_text: true}, variables);
    }

    function fitText(frame, widthMm, heightMm) {
        if (widthMm <= 0 || heightMm <= 0) return;
        var maxW = mmToPt(widthMm);
        var maxH = mmToPt(heightMm);
        for (var i = 0; i < 100; i++) {
            var bounds = frame.visibleBounds;
            var width = Math.abs(bounds[2] - bounds[0]);
            var height = Math.abs(bounds[1] - bounds[3]);
            if (width <= maxW && height <= maxH) break;
            var attrs = frame.textRange.characterAttributes;
            var size = Number(attrs.size || 12);
            if (size <= 4) break;
            attrs.size = Math.max(4, size * Math.min(maxW / width, maxH / height) * 0.96);
        }
    }

    function applyTextColor(frame, name) {
        if (!name) return;
        var rgb = colorValue(name);
        if (!rgb) return;
        var color = new RGBColor();
        color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
        try { frame.textRange.characterAttributes.fillColor = color; } catch (e1) {}
    }

    function applyNameAlternatingColors(frame, target, delimiter) {
        if (target !== "Name" || !delimiter) return;
        var text = String(frame.contents || "");
        if (text.indexOf(delimiter) < 0) return;
        var parts = text.split(delimiter);
        if (parts.length < 2) return;
        var cursor = 0;
        for (var partIndex = 0; partIndex < parts.length; partIndex++) {
            var rgb = partIndex % 2 === 0 ? [215, 25, 32] : [0, 0, 0];
            var color = new RGBColor();
            color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
            var part = parts[partIndex];
            for (var charIndex = 0; charIndex < part.length; charIndex++) {
                frame.characters[cursor + charIndex].characterAttributes.fillColor = color;
            }
            cursor += part.length + delimiter.length;
        }
    }

    function colorValue(name) {
        var map = {
            "black": [0, 0, 0], "white": [255, 255, 255], "red": [255, 0, 0],
            "blue": [0, 102, 204], "gold": [212, 175, 55],
            "黑色": [0, 0, 0], "白色": [255, 255, 255], "红色": [255, 0, 0],
            "蓝色": [0, 102, 204], "金色": [212, 175, 55]
        };
        return map[String(name).toLowerCase()] || null;
    }

    function findPageItemByName(doc, name) {
        for (var l = 0; l < doc.layers.length; l++) {
            var found = findInContainer(doc.layers[l], name);
            if (found) return found;
        }
        return null;
    }

    function findPageItemsByName(doc, name) {
        var result = [];
        for (var l = 0; l < doc.layers.length; l++) collectInContainer(doc.layers[l], name, result);
        return result;
    }

    function collectInContainer(container, name, result) {
        if (!container || !container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.name === name) result.push(item);
            if (item.typename === "GroupItem" || item.typename === "Layer") {
                collectInContainer(item, name, result);
            }
        }
    }

    function findInContainer(container, name) {
        if (!container || !container.pageItems) return null;
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

    function copyTextStyle(source, target) {
        var src = source.textRange.characterAttributes;
        var dst = target.textRange.characterAttributes;
        try { dst.textFont = src.textFont; } catch (e1) {}
        try { dst.size = src.size; } catch (e2) {}
        try { dst.tracking = src.tracking; } catch (e3) {}
        try { dst.horizontalScale = src.horizontalScale; } catch (e4) {}
        try { dst.verticalScale = src.verticalScale; } catch (e5) {}
        try { dst.fillColor = src.fillColor; } catch (e6) {}
        try { target.textRange.paragraphAttributes.justification = source.textRange.paragraphAttributes.justification; } catch (e7) {}
    }

    function centerItem(item, bounds) {
        var own = item.visibleBounds;
        item.translate(
            (Number(bounds[0]) + Number(bounds[2]) - Number(own[0]) - Number(own[2])) / 2,
            (Number(bounds[1]) + Number(bounds[3]) - Number(own[1]) - Number(own[3])) / 2
        );
    }

    function saveAsAI8(doc, file) {
        var options = new IllustratorSaveOptions();
        options.compatibility = Compatibility.ILLUSTRATOR8;
        options.pdfCompatible = false;
        options.compressed = false;
        doc.saveAs(file, options);
    }

    function ensureFolder(folder) {
        if (!folder.exists) {
            ensureFolder(folder.parent);
            folder.create();
        }
    }

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

    function mmToPt(value) { return value * 72 / 25.4; }
}());
