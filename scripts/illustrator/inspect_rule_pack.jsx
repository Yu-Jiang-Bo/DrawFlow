#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    var sourceFile = File(String(task.input_ai));
    var doc = app.open(sourceFile);
    var result = {
        document: {
            source_ai: sourceFile.fsName,
            name: String(doc.name || ""),
            color_space: String(doc.documentColorSpace || ""),
            width_pt: numberOr(doc.width, 0),
            height_pt: numberOr(doc.height, 0)
        },
        layers: [],
        items: [],
        scan_errors: []
    };

    for (var l = 0; l < doc.layers.length; l++) {
        var layer = doc.layers[l];
        var layerPath = String(layer.name || ("Layer " + (l + 1)));
        result.layers.push({
            name: String(layer.name || ""),
            visible: booleanOr(layer.visible, true),
            locked: booleanOr(layer.locked, false),
            child_count: safeChildCount(layer)
        });
        for (var p = 0; p < layer.pageItems.length; p++) {
            safeCollect(layer.pageItems[p], layerPath, 1, result.items, result.scan_errors);
        }
    }

    writeText(File(String(task.output_json)), toJson(result));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "INSPECT_RULE_PACK_OK";

    function safeCollect(item, parentPath, depth, output, errors) {
        try {
            collectItem(item, parentPath, depth, output, errors);
        } catch (error) {
            errors.push({ path: parentPath, depth: depth, error: String(error) });
        }
    }

    function collectItem(item, parentPath, depth, output, errors) {
        var type = safeString(item, "typename", "Unknown");
        var name = safeString(item, "name", "");
        var segment = name || (type + "[" + output.length + "]");
        var path = parentPath + "/" + segment;
        var record = {
            depth: depth,
            path: path,
            type: type,
            name: name,
            text: "",
            text_kind: "",
            font_name: "",
            font_family: "",
            font_style: "",
            font_size_pt: 0,
            bounds: boundsArray(item),
            fill_color: fillColor(item),
            opacity: safeNumber(item, "opacity", 100),
            hidden: safeBoolean(item, "hidden", false),
            locked: safeBoolean(item, "locked", false),
            child_count: safeChildCount(item)
        };
        if (type === "TextFrame") readTextFrame(item, record);
        output.push(record);
        if (type === "GroupItem") {
            for (var i = 0; i < item.pageItems.length; i++) {
                safeCollect(item.pageItems[i], path, depth + 1, output, errors);
            }
        }
    }

    function readTextFrame(item, record) {
        record.text = String(item.contents || "");
        try { record.text_kind = String(item.kind || ""); } catch (e1) {}
        try {
            var attr = item.textRange.characterAttributes;
            var font = attr.textFont;
            record.font_name = font ? String(font.name || "") : "";
            record.font_family = font ? String(font.family || "") : "";
            record.font_style = font ? String(font.style || "") : "";
            record.font_size_pt = numberOr(attr.size, 0);
        } catch (e2) {}
    }

    function boundsArray(item) {
        try {
            var b = item.visibleBounds;
            return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
        } catch (e1) {
            return null;
        }
    }

    function fillColor(item) {
        var color = null;
        try {
            if (item.typename === "TextFrame") color = item.textRange.characterAttributes.fillColor;
            else if (item.filled) color = item.fillColor;
        } catch (e1) {}
        if (!color) return null;
        var type = String(color.typename || "Unknown");
        var value = { type: type };
        try {
            if (type === "RGBColor") {
                value.red = Number(color.red);
                value.green = Number(color.green);
                value.blue = Number(color.blue);
            } else if (type === "CMYKColor") {
                value.cyan = Number(color.cyan);
                value.magenta = Number(color.magenta);
                value.yellow = Number(color.yellow);
                value.black = Number(color.black);
            } else if (type === "GrayColor") {
                value.gray = Number(color.gray);
            } else if (type === "SpotColor") {
                value.spot = String(color.spot ? color.spot.name : "");
                value.tint = Number(color.tint);
            }
        } catch (e2) {}
        return value;
    }

    function numberOr(value, fallback) {
        var number = Number(value);
        return isNaN(number) ? fallback : number;
    }

    function booleanOr(value, fallback) {
        return value === true || value === false ? value : fallback;
    }

    function safeString(item, property, fallback) {
        try { return String(item[property] || fallback); } catch (e1) { return fallback; }
    }

    function safeNumber(item, property, fallback) {
        try { return numberOr(item[property], fallback); } catch (e1) { return fallback; }
    }

    function safeBoolean(item, property, fallback) {
        try { return booleanOr(item[property], fallback); } catch (e1) { return fallback; }
    }

    function safeChildCount(item) {
        try { return item.pageItems ? item.pageItems.length : 0; } catch (e1) { return 0; }
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("Task file not found: " + path);
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open task file: " + path);
        var text = file.read();
        file.close();
        if (typeof JSON === "undefined" || !JSON.parse) throw new Error("JSON.parse unavailable");
        return JSON.parse(text);
    }

    function writeText(file, text) {
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write output: " + file.fsName);
        file.write(text);
        file.close();
    }

    function toJson(value) {
        if (value === null || value === undefined) return "null";
        var type = typeof value;
        if (type === "number") return isNaN(value) ? "null" : String(value);
        if (type === "boolean") return value ? "true" : "false";
        if (type === "string") return quote(value);
        if (value instanceof Array) {
            var values = [];
            for (var i = 0; i < value.length; i++) values.push(toJson(value[i]));
            return "[" + values.join(",") + "]";
        }
        var properties = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) properties.push(quote(key) + ":" + toJson(value[key]));
        }
        return "{" + properties.join(",") + "}";
    }

    function quote(value) {
        return "\"" + String(value)
            .replace(/\\/g, "\\\\")
            .replace(/"/g, "\\\"")
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n")
            .replace(/\t/g, "\\t") + "\"";
    }
}());
