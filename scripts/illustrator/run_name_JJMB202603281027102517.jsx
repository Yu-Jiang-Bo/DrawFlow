(function () {
    $.setenv(
        "CUSTOM_RENDER_TASK",
        "C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\.tmp\\template-inspect\\name-font-slots-task.json"
    );
    var result = $.evalFile(File("C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\scripts\\illustrator\\name_font_slots.jsx"));
    alert(result);
    return result;
}());
