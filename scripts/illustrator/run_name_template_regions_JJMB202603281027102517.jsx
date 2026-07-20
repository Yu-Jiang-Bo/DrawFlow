(function () {
    function readText(file) {
        file.encoding = "UTF-8";
        if (!file.open("r")) {
            throw new Error("Cannot open script file: " + file.fsName);
        }
        var text = file.read();
        file.close();
        return text;
    }

    $.setenv(
        "CUSTOM_RENDER_TASK",
        "C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\.tmp\\template-inspect\\name-template-regions-task.json"
    );
    var scriptFile = File("C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\scripts\\illustrator\\name_template_regions.jsx");
    var result = eval(readText(scriptFile));
    alert(result);
    return result;
}());
