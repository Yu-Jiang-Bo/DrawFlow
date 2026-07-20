(function () {
    $.setenv(
        "CUSTOM_RENDER_TASK",
        "C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\.tmp\\template-inspect\\name-art-zones-task.json"
    );
    var result = $.evalFile(File("C:\\Users\\Administrator\\Desktop\\image\\custom-renderer\\scripts\\illustrator\\name_art_zones.jsx"));
    alert(result);
    return result;
}());
