#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "render_batch") throw new Error("Unsupported batch task type: " + task.type);
    if (!task.tasks || task.tasks.length === 0) throw new Error("No batch render tasks");

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var originalTaskPath = taskPath;
    var outputs = [];
    try {
        for (var i = 0; i < task.tasks.length; i++) {
            var entry = task.tasks[i] || {};
            var scriptPath = String(entry.script || "");
            var childTaskPath = String(entry.task_file || entry.task_path || "");
            if (!scriptPath) throw new Error("Batch task missing script at index " + i);
            if (!childTaskPath) throw new Error("Batch task missing task_file at index " + i);
            $.setenv("CUSTOM_RENDER_TASK", childTaskPath);
            outputs.push(String($.evalFile(File(scriptPath)) || ""));
            // Saving outlined component artwork creates substantially more native
            // Illustrator objects than deferred live text.  Give Illustrator one
            // redraw/cleanup turn before the next child reopens the template.
            // Without this hand-off, long reuse batches can intermittently fail
            // the next app.open() with Illustrator error 248.
            try { app.redraw(); } catch (redrawError) {}
            try { if ($.gc) $.gc(); } catch (ignored) {}
            try { $.sleep(100); } catch (sleepError) {}
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
