#target illustrator

(function () {
    try {
        var taskFile = File.openDialog("Select template text render task JSON", "*.json");
        if (!taskFile) return "CANCELLED";
        $.setenv("CUSTOM_RENDER_TASK", taskFile.fsName);
        var result = $.evalFile(File("C:/Users/Administrator/Desktop/image/custom-renderer/scripts/illustrator/render_template_text.jsx"));
        alert("RENDER_TEMPLATE_TEXT_OK\n" + result);
        return result;
    } catch (err) {
        alert("RENDER_TEMPLATE_TEXT_ERROR: " + err + " line=" + (err.line || ""));
        return "RENDER_TEMPLATE_TEXT_ERROR: " + err;
    }
}());
