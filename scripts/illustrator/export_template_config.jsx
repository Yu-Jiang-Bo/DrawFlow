#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    var doc = app.open(File(String(task.input_ai)));

    var config = {
        template_id: String(task.template_id || ""),
        template_type: "text_style_font",
        source_ai: String(task.input_ai || ""),
        units: "pt",
        regions: {
            font_region: "\u5b57\u4f53\u533a",
            art_region: "\u4f5c\u56fe\u533a"
        },
        font_options: {},
        style_options: {},
        "export": {
            format: "ai",
            compatibility: "Illustrator 8",
            outline_text: true,
            pathfinder_merge: true
        }
    };

    collectFonts(doc, config);
    collectStyles(doc, config);
    writeText(File(String(task.output_json)), toJson(config));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "EXPORT_TEMPLATE_CONFIG_OK";

    function collectFonts(doc, config) {
        for (var i = 1; i <= 99; i++) {
            var name = "F" + i;
            var item = findPageItemByName(doc, name);
            if (!item) continue;
            var tf = firstTextFrame(item);
            if (!tf) {
                config.font_options[name] = { type: "design", editable_text: false };
                continue;
            }
            var attr = tf.textRange.characterAttributes;
            var font = null;
            try { font = attr.textFont; } catch (e1) {}
            config.font_options[name] = {
                type: "text",
                editable_text: true,
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
    }

    function collectStyles(doc, config) {
        for (var i = 1; i <= 99; i++) {
            var name = "Style" + i;
            var item = findPageItemByName(doc, name);
            if (!item) continue;
            var b = visibleBounds(item);
            var widthPt = Math.abs(b[2] - b[0]);
            var heightPt = Math.abs(b[1] - b[3]);
            config.style_options[name] = {
                type: "art_box",
                bounds_pt: b,
                width_pt: widthPt,
                height_pt: heightPt,
                width_mm: ptToMm(widthPt),
                height_mm: ptToMm(heightPt)
            };
        }
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

    function visibleBounds(item) {
        var b = item.visibleBounds;
        return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
    }

    function ptToMm(value) {
        return Number(value) * 25.4 / 72;
    }

    function numberOr(value, fallback) {
        var number = Number(value);
        return isNaN(number) ? fallback : number;
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
