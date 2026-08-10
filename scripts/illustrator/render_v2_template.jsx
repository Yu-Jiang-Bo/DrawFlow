#target illustrator

(function () {
    var EXECUTION_SCHEMA = "custom-renderer/v2-render-execution";
    var TASK_SCHEMA = "custom-renderer/v2-render-task";
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var execution = readJSON(taskPath);
    if (execution.$schema !== EXECUTION_SCHEMA) throw new Error("Unsupported V2 execution schema: " + execution.$schema);
    var task = execution.render_task || {};
    if (task.$schema !== TASK_SCHEMA) throw new Error("Unsupported V2 render task schema: " + task.$schema);

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (ignored) {}

    var templateDoc = app.open(File(String(execution.template_ai)));
    var doc = app.documents.add(DocumentColorSpace.RGB, 1000, 1000);
    var layer = doc.layers[0];
    layer.name = "V2_OUTPUT";
    var values = execution.values || {};
    var selections = execution.selections || {};

    try {
        for (var outputIndex = 0; outputIndex < (task.outputs || []).length; outputIndex++) {
            renderOutput(templateDoc, layer, task.outputs[outputIndex], values, selections);
        }
        var output = File(String(execution.output_ai));
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        saveAsAI8(doc, output);
        return output.fsName;
    } finally {
        try { templateDoc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeTemplateError) {}
        try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeOutputError) {}
    }

    function renderOutput(sourceDoc, targetLayer, output, valuesByField, selectionsByOutput) {
        var outputKey = String(output.key || "");
        var selected = selectionsByOutput[outputKey] || {};
        var copied = {};
        var actions = output.actions || [];
        for (var index = 0; index < actions.length; index++) {
            var action = actions[index] || {};
            if (action.type === "copy_option_group" && isSelected(action, selected)) {
                copied[copyKey(outputKey, action)] = copyOptionGroup(sourceDoc, targetLayer, action.object_path, action.source_only === true);
            }
        }
        for (var replaceIndex = 0; replaceIndex < actions.length; replaceIndex++) {
            var replaceAction = actions[replaceIndex] || {};
            if (replaceAction.type === "replace_slot_text" && isSelected(replaceAction, selected)) {
                replaceSlotText(copied, outputKey, replaceAction, valuesByField, selected);
            }
        }
        removeSourceOnlyCopies(copied);
    }

    function isSelected(action, selected) {
        var group = String(action.group || "");
        var optionKey = String(action.option_key || "");
        return group && optionKey && String(selected[group] || "") === optionKey;
    }

    function copyOptionGroup(sourceDoc, targetLayer, objectPath, sourceOnly) {
        var source = findPageItemByPath(sourceDoc, objectPath);
        var copy = source.duplicate(targetLayer, ElementPlacement.PLACEATEND);
        return { item: copy, source_path: String(objectPath || ""), source_only: sourceOnly === true };
    }

    function replaceSlotText(copied, outputKey, action, valuesByField, selected) {
        var holder = copied[copyKey(outputKey, action)];
        if (!holder || !holder.item) throw new Error("Selected option was not copied: " + copyKey(outputKey, action));
        var slot = findPageItemByRelativePath(holder.item, relativePath(String(action.object_path || ""), holder.source_path));
        var value = String(valuesByField[String(action.source_field || "")] || "");
        var parts = splitPipeValue(value);
        if (!hasText(value)) {
            if (action.required !== false) throw new Error("Required V2 slot has no value: " + action.source_field);
            removePageItem(slot);
            return;
        }
        var target = slot;
        if (action.style_source) {
            target = replaceWithFontStyleSource(copied, outputKey, action, selected, slot);
        }
        writeTextToItem(target, parts[0]);
        var tailPaths = action.tail_paths || [];
        for (var index = 0; index < tailPaths.length; index++) {
            var tail = findPageItemByRelativePath(holder.item, relativePath(String(tailPaths[index] || ""), holder.source_path));
            var tailText = parts[index + 1] || "";
            if (hasText(tailText)) {
                writeTextToItem(tail, tailText);
            } else {
                removePageItem(tail);
            }
        }
    }

    function replaceWithFontStyleSource(copied, outputKey, action, selected, targetSlot) {
        var sourceInfo = action.style_source || {};
        var group = String(sourceInfo.group || "");
        var fontOption = String(selected[group] || "");
        if (!fontOption) throw new Error("V2 font style source selection is missing");
        var paths = sourceInfo.paths_by_option || {};
        var sourcePath = String(paths[fontOption] || "");
        if (!sourcePath) throw new Error("V2 font style source path is missing: " + fontOption);
        var sourceHolder = copied[outputKey + "|" + group + "|" + fontOption];
        if (!sourceHolder || !sourceHolder.item) throw new Error("V2 font style source was not copied: " + fontOption);
        var sourceItem = findPageItemByRelativePath(sourceHolder.item, relativePath(sourcePath, sourceHolder.source_path));
        var parent = targetSlot.parent || sourceHolder.item.parent;
        var replacement = sourceItem.duplicate(parent, ElementPlacement.PLACEATEND);
        alignItemToItem(replacement, targetSlot);
        removePageItem(targetSlot);
        return replacement;
    }

    function removeSourceOnlyCopies(copied) {
        for (var key in copied) {
            if (copied.hasOwnProperty(key) && copied[key] && copied[key].source_only === true) {
                removePageItem(copied[key].item);
            }
        }
    }

    function writeTextToItem(item, text) {
        var frame = firstTextFrame(item);
        if (!frame) throw new Error("V2 slot has no text frame: " + String(item && item.name || ""));
        frame.contents = String(text || "");
    }

    function firstTextFrame(item) {
        if (!item) return null;
        if (item.typename === "TextFrame") return item;
        var children = item.pageItems || [];
        for (var index = 0; index < children.length; index++) {
            var found = firstTextFrame(children[index]);
            if (found) return found;
        }
        return null;
    }

    function removePageItem(item) {
        if (!item) return;
        try {
            item.remove();
        } catch (removeError) {
            try { item.hidden = true; } catch (hideError) {}
        }
    }

    function alignItemToItem(item, target) {
        try {
            var itemBounds = item.visibleBounds;
            var targetBounds = target.visibleBounds;
            var itemCenterX = (Number(itemBounds[0]) + Number(itemBounds[2])) / 2;
            var itemCenterY = (Number(itemBounds[1]) + Number(itemBounds[3])) / 2;
            var targetCenterX = (Number(targetBounds[0]) + Number(targetBounds[2])) / 2;
            var targetCenterY = (Number(targetBounds[1]) + Number(targetBounds[3])) / 2;
            item.translate(targetCenterX - itemCenterX, targetCenterY - itemCenterY);
        } catch (alignError) {}
    }

    function findPageItemByPath(root, objectPath) {
        var parts = splitPath(objectPath);
        if (!parts.length) throw new Error("V2 object path is empty");
        var current = root;
        for (var index = 0; index < parts.length; index++) {
            current = findChildByName(current, parts[index]);
            if (!current) throw new Error("V2 object path not found: " + objectPath);
        }
        return current;
    }

    function findPageItemByRelativePath(root, path) {
        var parts = splitPath(path);
        var current = root;
        for (var index = 0; index < parts.length; index++) {
            current = findChildByName(current, parts[index]);
            if (!current) throw new Error("V2 relative object path not found: " + path);
        }
        return current;
    }

    function findChildByName(container, name) {
        var layers = container.layers || [];
        for (var layerIndex = 0; layerIndex < layers.length; layerIndex++) {
            if (String(layers[layerIndex].name || "") === name) return layers[layerIndex];
        }
        var children = container.pageItems || [];
        for (var itemIndex = 0; itemIndex < children.length; itemIndex++) {
            if (String(children[itemIndex].name || "") === name) return children[itemIndex];
        }
        return null;
    }

    function relativePath(fullPath, rootPath) {
        if (fullPath === rootPath) return "";
        if (fullPath.indexOf(rootPath + "/") !== 0) {
            throw new Error("V2 slot path is outside selected option: " + fullPath);
        }
        return fullPath.substring(rootPath.length + 1);
    }

    function splitPath(path) {
        var raw = String(path || "").split("/");
        var parts = [];
        for (var index = 0; index < raw.length; index++) {
            if (raw[index]) parts.push(raw[index]);
        }
        return parts;
    }

    function splitPipeValue(value) {
        var raw = String(value || "").split("|");
        var parts = [];
        for (var index = 0; index < raw.length; index++) parts.push(raw[index]);
        return parts;
    }

    function hasText(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "") !== "";
    }

    function copyKey(outputKey, action) {
        return String(outputKey || "") + "|" + String(action.group || "") + "|" + String(action.option_key || "");
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("Task file not found: " + path);
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open task file: " + path);
        var text = file.read();
        file.close();
        return parseJson(text);
    }

    function parseJson(text) {
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        throw new Error("JSON parser is not available in this Illustrator runtime");
    }

    function saveAsAI8(doc, file) {
        var options = new IllustratorSaveOptions();
        options.compatibility = Compatibility.ILLUSTRATOR8;
        options.pdfCompatible = false;
        options.compressed = false;
        doc.saveAs(file, options);
    }

    function ensureFolder(folder) {
        if (!folder || folder.exists) return;
        ensureFolder(folder.parent);
        folder.create();
    }
}());
