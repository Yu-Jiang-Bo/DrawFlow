#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    var files = task.input_files || [];
    var rows = ["file,width_pt,height_pt,width_mm,height_mm,width_cm,height_cm"];

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}

    for (var i = 0; i < files.length; i++) {
        var file = File(String(files[i]));
        if (!file.exists) continue;
        var doc = app.open(file);
        var rect = doc.artboards[0].artboardRect;
        var widthPt = Math.abs(Number(rect[2]) - Number(rect[0]));
        var heightPt = Math.abs(Number(rect[1]) - Number(rect[3]));
        var widthMm = ptToMm(widthPt);
        var heightMm = ptToMm(heightPt);
        rows.push([
            csv(file.fsName),
            fixed(widthPt),
            fixed(heightPt),
            fixed(widthMm),
            fixed(heightMm),
            fixed(widthMm / 10),
            fixed(heightMm / 10)
        ].join(","));
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }

    writeText(File(String(task.output_csv)), rows.join("\n"));
    return "REPORT_AI_SIZES_OK";

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
        if (!file.open("w")) throw new Error("Cannot write report: " + file.fsName);
        file.write(text);
        file.close();
    }

    function ptToMm(value) {
        return value * 25.4 / 72;
    }

    function fixed(value) {
        return Number(value).toFixed(3);
    }

    function csv(value) {
        return "\"" + String(value).replace(/"/g, "\"\"") + "\"";
    }
}());
