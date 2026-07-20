(function () {
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

    function itemType(item) {
        return item.typename || "Unknown";
    }

    function itemText(item) {
        if (item.typename === "TextFrame") {
            return item.contents || "";
        }
        return "";
    }

    function boundsArray(item) {
        try {
            var b = item.visibleBounds;
            return "[" + [b[0], b[1], b[2], b[3]].join(",") + "]";
        } catch (err) {
            return "null";
        }
    }

    function dumpItem(item, depth, lines) {
        var children = [];
        if (item.typename === "GroupItem") {
            for (var i = 0; i < item.pageItems.length; i++) {
                children.push(item.pageItems[i]);
            }
        }
        lines.push(
            "{\"depth\":" + depth +
            ",\"type\":" + q(itemType(item)) +
            ",\"name\":" + q(item.name || "") +
            ",\"text\":" + q(itemText(item)) +
            ",\"bounds\":" + boundsArray(item) +
            ",\"children\":" + children.length + "}"
        );
        for (var c = 0; c < children.length; c++) {
            dumpItem(children[c], depth + 1, lines);
        }
    }

    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) {
        throw new Error("CUSTOM_RENDER_TASK is not set");
    }
    var task = parseJson(readText(File(taskPath)));
    var doc = app.open(File(task.input_ai));
    var lines = [];

    for (var l = 0; l < doc.layers.length; l++) {
        var layer = doc.layers[l];
        lines.push("{\"depth\":0,\"type\":\"Layer\",\"name\":" + q(layer.name) + ",\"text\":\"\",\"bounds\":null,\"children\":" + layer.pageItems.length + "}");
        for (var p = 0; p < layer.pageItems.length; p++) {
            dumpItem(layer.pageItems[p], 1, lines);
        }
    }

    writeText(File(task.output_jsonl), lines.join("\n"));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "INSPECT_OK";
}());
