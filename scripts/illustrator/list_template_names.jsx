#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    var doc = app.open(File(String(task.input_ai)));
    var lines = [];

    for (var l = 0; l < doc.layers.length; l++) {
        lines.push("Layer\t" + doc.layers[l].name);
        walk(doc.layers[l], 1);
    }

    writeText(File(String(task.output_txt)), lines.join("\n"));
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return "LIST_TEMPLATE_NAMES_OK";

    function walk(container, depth) {
        if (!container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            var text = "";
            if (item.typename === "TextFrame") {
                text = String(item.contents || "").replace(/\r/g, "\\r").replace(/\n/g, "\\n");
            }
            if (item.name || text) {
                lines.push(depth + "\t" + item.typename + "\t" + (item.name || "") + "\t" + text);
            }
            if (item.pageItems) walk(item, depth + 1);
        }
    }

    function readJSON(path) {
        var file = File(path);
        file.encoding = "UTF-8";
        file.open("r");
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }

    function writeText(file, text) {
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write output");
        file.write(text);
        file.close();
    }
}());
