#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    var doc = app.open(File(String(task.input_ai)));

    var config = {
        template_id: String(task.template_id || "JJMB202508261001394920"),
        template_type: "text_color_design",
        source_ai: String(task.input_ai || ""),
        units: "pt",
        defaults: {
            color_option: "Gold",
            design_option: "Design2"
        },
        font_options: {},
        color_options: colorOptions(),
        design_options: {},
        diagnostics: diagnostics(doc)
    };

    collectFonts(doc, config);
    collectDesigns(doc, config);
    writeText(File(String(task.output_json)), toJson(config));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "EXPORT_202508_CONFIG_OK";

    function collectFonts(doc, config) {
        var region = findGroupByName(doc, "\u5b57\u4f53\u533a") || findPageItemByName(doc, "\u5b57\u4f53\u533a");
        if (!region) {
            collectFontsByLabels(doc, config);
            return;
        }
        for (var i = 1; i <= 10; i++) {
            var name = "F" + i;
            var item = findInContainer(region, name);
            var tf = firstTextFrame(item);
            if (!tf) continue;
            config.font_options[name] = fontPayload(tf);
        }
    }

    function collectDesigns(doc, config) {
        var found = 0;
        for (var i = 1; i <= 3; i++) {
            var name = "Design" + i;
            var group = findGroupByName(doc, name) || findPageItemByName(doc, name);
            if (!group || group.typename !== "GroupItem") continue;
            var paths = [];
            collectPathItems(group, paths);
            if (setDesignFromPaths(config, name, paths)) found++;
        }
        if (found < 3) collectDesignsByLabels(doc, config);
        if (countProps(config.design_options) < 3) addFallbackDesigns(config);
    }

    function collectFontsByLabels(doc, config) {
        var texts = allTextFrames(doc);
        for (var i = 1; i <= 10; i++) {
            var label = findTextByContents(texts, "F" + i);
            var sample = label ? nearestFontSample(texts, label) : null;
            if (sample) config.font_options["F" + i] = fontPayload(sample);
        }
    }

    function nearestFontSample(texts, label) {
        var lb = visibleBounds(label);
        var best = null;
        var bestScore = 999999999;
        for (var i = 0; i < texts.length; i++) {
            var tf = texts[i];
            if (tf === label) continue;
            var value = trim(String(tf.contents || ""));
            if (!value || /^F\d+$/i.test(value)) continue;
            if (/Design/i.test(value) || /\d+\s*mm/i.test(value)) continue;
            if (/[\u4e00-\u9fff]/.test(value)) continue;
            var b = visibleBounds(tf);
            var dx = Number(b[0]) - Number(lb[2]);
            var dy = Math.abs(centerY(b) - centerY(lb));
            if (dx < -10 || dx > 420 || dy > 70) continue;
            var score = dx + dy * 4;
            if (score < bestScore) {
                bestScore = score;
                best = tf;
            }
        }
        return best;
    }

    function fontPayload(tf) {
        var attr = tf.textRange.characterAttributes;
        var font = null;
        try { font = attr.textFont; } catch (e1) {}
        return {
            type: "text",
            sample_text: String(tf.contents || ""),
            font_name: font ? String(font.name || "") : "",
            font_family: font ? String(font.family || "") : "",
            font_style: font ? String(font.style || "") : "",
            font_size_pt: numberOr(attr.size, 48),
            tracking: numberOr(attr.tracking, 0),
            horizontal_scale: numberOr(attr.horizontalScale, 100),
            vertical_scale: numberOr(attr.verticalScale, 100)
        };
    }

    function collectDesignsByLabels(doc, config) {
        var texts = allTextFrames(doc);
        var paths = allPathItems(doc);
        for (var i = 1; i <= 3; i++) {
            var name = "Design" + i;
            if (config.design_options[name]) continue;
            var label = findDesignLabel(texts, i);
            if (!label) continue;
            var labelBounds = visibleBounds(label);
            var cx = centerX(labelBounds);
            var candidates = [];
            for (var p = 0; p < paths.length; p++) {
                var b = bounds(paths[p]);
                var w = width(b);
                var h = height(b);
                if (w < 50 || h < 50) continue;
                if (Math.abs(centerX(b) - cx) > 190) continue;
                if (centerY(b) < centerY(labelBounds) - 20) continue;
                if (Number(b[3]) < Number(labelBounds[3]) - 80) continue;
                candidates.push(paths[p]);
            }
            setDesignFromPaths(config, name, candidates);
        }
    }

    function setDesignFromPaths(config, name, paths) {
        if (!paths || paths.length < 1) return false;
        paths.sort(function (a, b) {
            return area(bounds(a)) - area(bounds(b));
        });
        var anchor = paths[0];
        var product = paths[paths.length - 1];
        var anchorBounds = bounds(anchor);
        var productBounds = bounds(product);
        config.design_options[name] = {
            product_bounds_pt: productBounds,
            anchor_bounds_pt: anchorBounds,
            product_width_mm: ptToMm(width(productBounds)),
            product_height_mm: ptToMm(height(productBounds)),
            anchor_width_mm: ptToMm(width(anchorBounds)),
            anchor_height_mm: ptToMm(height(anchorBounds)),
            rotation_deg: name === "Design2" ? 15 : 0
        };
        return true;
    }

    function addFallbackDesigns(config) {
        var product = [0, 0, mmToPt(100), -mmToPt(100)];
        var anchorW = mmToPt(55);
        var anchorH = mmToPt(40);
        var leftCenter = (width(product) - anchorW) / 2;
        var topCenter = -(width(product) - anchorH) / 2;
        if (!config.design_options.Design1) {
            config.design_options.Design1 = designPayload(product, [leftCenter, topCenter, leftCenter + anchorW, topCenter - anchorH], 0);
        }
        if (!config.design_options.Design2) {
            config.design_options.Design2 = designPayload(product, [mmToPt(38), -mmToPt(53), mmToPt(93), -mmToPt(93)], 15);
        }
        if (!config.design_options.Design3) {
            config.design_options.Design3 = designPayload(product, [mmToPt(39), -mmToPt(53), mmToPt(94), -mmToPt(93)], 0);
        }
    }

    function designPayload(productBounds, anchorBounds, rotation) {
        return {
            product_bounds_pt: productBounds,
            anchor_bounds_pt: anchorBounds,
            product_width_mm: ptToMm(width(productBounds)),
            product_height_mm: ptToMm(height(productBounds)),
            anchor_width_mm: ptToMm(width(anchorBounds)),
            anchor_height_mm: ptToMm(height(anchorBounds)),
            rotation_deg: rotation
        };
    }

    function colorOptions() {
        return {
            "White": { rgb: [255, 255, 255] },
            "Black": { rgb: [0, 0, 0] },
            "Rose Gold": { rgb: [183, 110, 121] },
            "Gold": { rgb: [212, 175, 55] },
            "Silver": { rgb: [192, 192, 192] },
            "Blue": { rgb: [0, 114, 188] },
            "Navy": { rgb: [10, 24, 72] },
            "Pink": { rgb: [244, 170, 200] },
            "Red": { rgb: [190, 30, 45] },
            "Dark Green": { rgb: [0, 90, 55] }
        };
    }

    function diagnostics(doc) {
        var names = [];
        try {
            for (var i = 0; i < doc.groupItems.length && i < 20; i++) {
                names.push("G:" + String(doc.groupItems[i].name || ""));
            }
        } catch (e1) {}
        try {
            for (var t = 0; t < doc.textFrames.length && t < 20; t++) {
                names.push("T:" + String(doc.textFrames[t].name || "") + "=" + String(doc.textFrames[t].contents || ""));
            }
        } catch (e2) {}
        var firstLayerItems = 0;
        try { firstLayerItems = doc.layers[0].pageItems.length; } catch (e3) {}
        return {
            layers: doc.layers.length,
            group_count: doc.groupItems.length,
            text_count: doc.textFrames.length,
            path_count: doc.pathItems.length,
            first_layer_items: firstLayerItems,
            names: names
        };
    }

    function findGroupByName(doc, name) {
        for (var i = 0; i < doc.groupItems.length; i++) {
            if (doc.groupItems[i].name === name) return doc.groupItems[i];
        }
        return null;
    }

    function findTextFrameByName(doc, name) {
        for (var i = 0; i < doc.textFrames.length; i++) {
            if (doc.textFrames[i].name === name) return doc.textFrames[i];
        }
        return null;
    }

    function findPageItemByName(doc, name) {
        for (var l = 0; l < doc.layers.length; l++) {
            var found = findInContainer(doc.layers[l], name);
            if (found) return found;
        }
        return null;
    }

    function findInContainer(container, name) {
        if (!container.pageItems) return null;
        if (container.textFrames) {
            for (var t = 0; t < container.textFrames.length; t++) {
                if (container.textFrames[t].name === name) return container.textFrames[t];
            }
        }
        if (container.groupItems) {
            for (var g = 0; g < container.groupItems.length; g++) {
                if (container.groupItems[g].name === name) return container.groupItems[g];
            }
        }
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.name === name) return item;
            if (item.pageItems) {
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

    function collectPathItems(container, out) {
        if (!container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.typename === "PathItem") out.push(item);
            if (item.pageItems) collectPathItems(item, out);
        }
    }

    function allTextFrames(doc) {
        var out = [];
        for (var i = 0; i < doc.textFrames.length; i++) out.push(doc.textFrames[i]);
        return out;
    }

    function allPathItems(doc) {
        var out = [];
        for (var i = 0; i < doc.pathItems.length; i++) out.push(doc.pathItems[i]);
        return out;
    }

    function findTextByContents(texts, value) {
        for (var i = 0; i < texts.length; i++) {
            if (trim(String(texts[i].contents || "")) === value) return texts[i];
        }
        return null;
    }

    function findDesignLabel(texts, number) {
        var pattern = new RegExp("^\\s*Design\\s*" + number + "\\b", "i");
        for (var i = 0; i < texts.length; i++) {
            if (pattern.test(String(texts[i].contents || ""))) return texts[i];
        }
        return null;
    }

    function bounds(item) {
        var b = item.geometricBounds;
        return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
    }

    function visibleBounds(item) {
        var b = item.visibleBounds;
        return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
    }

    function width(b) {
        return Math.abs(Number(b[2]) - Number(b[0]));
    }

    function height(b) {
        return Math.abs(Number(b[1]) - Number(b[3]));
    }

    function area(b) {
        return width(b) * height(b);
    }

    function centerX(b) {
        return (Number(b[0]) + Number(b[2])) / 2;
    }

    function centerY(b) {
        return (Number(b[1]) + Number(b[3])) / 2;
    }

    function ptToMm(value) {
        return Number(value) * 25.4 / 72;
    }

    function mmToPt(value) {
        return Number(value) * 72 / 25.4;
    }

    function numberOr(value, fallback) {
        var number = Number(value);
        return isNaN(number) ? fallback : number;
    }

    function trim(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "");
    }

    function countProps(value) {
        var count = 0;
        for (var key in value) {
            if (value.hasOwnProperty(key)) count++;
        }
        return count;
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

    function writeText(file, text) {
        file.encoding = "UTF-8";
        ensureFolder(file.parent);
        if (!file.open("w")) throw new Error("Cannot write config: " + file.fsName);
        file.write(text);
        file.close();
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
        if (type === "string") return quote(value);
        if (value instanceof Array) {
            var arr = [];
            for (var i = 0; i < value.length; i++) arr.push(toJson(value[i]));
            return "[" + arr.join(",") + "]";
        }
        var props = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) props.push(quote(key) + ":" + toJson(value[key]));
        }
        return "{" + props.join(",") + "}";
    }

    function quote(value) {
        return "\"" + String(value)
            .replace(/\\/g, "\\\\")
            .replace(/"/g, "\\\"")
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n") + "\"";
    }
}());
