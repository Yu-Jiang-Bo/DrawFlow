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

    function bounds(item) {
        try {
            var b = item.visibleBounds;
            return "[" + [b[0], b[1], b[2], b[3]].join(",") + "]";
        } catch (err) {
            return "null";
        }
    }

    function line(type, item, extra) {
        var text = "";
        if (item.typename === "TextFrame") {
            text = item.contents || "";
        }
        return "{\"type\":" + q(type) +
            ",\"typename\":" + q(item.typename || "") +
            ",\"name\":" + q(item.name || "") +
            ",\"text\":" + q(text) +
            ",\"bounds\":" + bounds(item) +
            ",\"extra\":" + q(extra || "") + "}";
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
    var lines = [];

    for (var t = 0; t < doc.textFrames.length; t++) {
        var tf = doc.textFrames[t];
        lines.push(line("text", tf, "index=" + t));
    }

    for (var g = 0; g < doc.groupItems.length; g++) {
        var group = doc.groupItems[g];
        lines.push(line("group", group, "index=" + g + ";items=" + group.pageItems.length));
    }

    writeText(File(task.output_jsonl), lines.join("\n"));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "FONT_INSPECT_OK";
}());
