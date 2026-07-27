#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "jjmb_202508_batch") throw new Error("Unsupported task type: " + task.type);
    if (!task.tasks || task.tasks.length === 0) throw new Error("No batch render tasks");

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var originalTaskPath = taskPath;
    var outputs = [];
    try {
        for (var i = 0; i < task.tasks.length; i++) {
            var entry = task.tasks[i] || {};
            var scriptPath = String(entry.script || task.render_script || "");
            var childTaskPath = String(entry.task_file || entry.task_path || "");
            if (!scriptPath) throw new Error("Batch task missing script at index " + i);
            if (!childTaskPath) throw new Error("Batch task missing task_file at index " + i);
            $.setenv("CUSTOM_RENDER_TASK", childTaskPath);
            outputs.push(String($.evalFile(File(scriptPath)) || ""));
            try {
                if ($.gc) $.gc();
            } catch (ignored) {}
        }
    } finally {
        $.setenv("CUSTOM_RENDER_TASK", originalTaskPath);
    }
    return outputs.join("\n");

    function readJSON(path) {
        var file = File(path);
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open task JSON: " + path);
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }
}());
