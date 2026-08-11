#target illustrator
#include "v2_tail_text.jsxinc"

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
    var layoutWarnings = [];

    try {
        for (var outputIndex = 0; outputIndex < (task.outputs || []).length; outputIndex++) {
            renderOutput(templateDoc, layer, task.outputs[outputIndex], values, selections);
        }
        var output = File(String(execution.output_ai));
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        saveAsAI8(doc, output);
        writeLayoutWarnings(execution.layout_warning_file, layoutWarnings);
        return output.fsName;
    } finally {
        try { templateDoc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeTemplateError) {}
        try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeOutputError) {}
    }

    function renderOutput(sourceDoc, targetLayer, output, valuesByField, selectionsByOutput) {
        var outputKey = String(output.key || "");
        var selected = selectionsByOutput[outputKey] || {};
        var copied = {};
        var renderedItems = [];
        var actions = output.actions || [];
        for (var index = 0; index < actions.length; index++) {
            var action = actions[index] || {};
            if (action.type === "copy_option_group" && isSelected(action, selected)) {
                copied[copyKey(outputKey, action)] = copyOptionGroup(sourceDoc, targetLayer, action.object_path, action.source_only === true);
                if (action.source_only !== true) renderedItems.push(copied[copyKey(outputKey, action)].item);
            }
        }
        for (var replaceIndex = 0; replaceIndex < actions.length; replaceIndex++) {
            var replaceAction = actions[replaceIndex] || {};
            if (replaceAction.type === "replace_slot_text" && isSelected(replaceAction, selected)) {
                replaceSlotText(copied, outputKey, replaceAction, valuesByField, selected);
            }
        }
        cleanupAuxiliaryObjects(renderedItems);
        for (var fitIndex = 0; fitIndex < actions.length; fitIndex++) {
            var fitAction = actions[fitIndex] || {};
            if (fitAction.type === "fit_output_bounds" && isSelected(fitAction, selected)) {
                fitRenderedOutput(renderedItems, fitAction);
            }
        }
        cleanupAuxiliaryObjects(renderedItems);
        removeSourceOnlyCopies(copied);
    }

    function isSelected(action, selected) {
        var group = String(action.group || "");
        var optionKey = String(action.option_key || action.style_key || "");
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
        var fitBounds = localFitBounds(holder.item, holder.source_path, action, slot);
        var value = String(valuesByField[String(action.source_field || "")] || "");
        var parts = splitPipeValue(value);
        var preset = String(action.preset || "");
        var slotValue = preset === "split_by_pipe" ? splitPart(parts, action.source_part_index) : parts[0];
        var requiredValue = preset === "split_by_pipe" ? slotValue : value;
        if (!hasText(requiredValue)) {
            if (action.required !== false) throw new Error("Required V2 slot has no value: " + action.source_field);
            removePageItem(slot);
            return;
        }
        var target = slot;
        if (action.style_source) {
            target = replaceWithFontStyleSource(copied, outputKey, action, selected, slot);
        }
        if (preset === "tail_text") {
            V2TailText.replaceTailText(
                tailTextEnvironment(),
                holder.item,
                holder.source_path,
                target,
                value,
                fitBounds,
                action
            );
            return;
        }
        var textFrame = writeTextToItem(target, slotValue);
        fitItemWithinBounds(textFrame, fitBounds, action);
        var tailPaths = action.tail_paths || [];
        for (var index = 0; index < tailPaths.length; index++) {
            var tail = findPageItemByRelativePath(holder.item, relativePath(String(tailPaths[index] || ""), holder.source_path));
            var tailText = parts[index + 1] || "";
            if (hasText(tailText)) {
                var tailFrame = writeTextToItem(tail, tailText);
                fitItemWithinBounds(tailFrame, measuredBounds(tail), action);
            } else {
                removePageItem(tail);
            }
        }
    }

    function tailTextEnvironment() {
        return {
            writeTextToItem: writeTextToItem,
            fitItemWithinBounds: fitItemWithinBounds,
            measuredBounds: measuredBounds,
            findPageItemByRelativePath: findPageItemByRelativePath,
            relativePath: relativePath,
            hasText: hasText,
            removePageItem: removePageItem
        };
    }

    function localFitBounds(root, sourcePath, action, slot) {
        var anchorPath = String(action.anchor_path || "");
        if (anchorPath) {
            var anchor = findPageItemByRelativePath(root, relativePath(anchorPath, sourcePath));
            return measuredBounds(anchor);
        }
        return measuredBounds(slot);
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
        var targetFrame = firstTextFrame(targetSlot);
        if (!targetFrame) throw new Error("V2 design slot has no text frame for style source");
        var parent = targetSlot.typename === "TextFrame" ? (targetSlot.parent || sourceHolder.item.parent) : targetSlot;
        var replacement = sourceItem.duplicate(parent, ElementPlacement.PLACEATEND);
        alignItemToItem(replacement, targetFrame);
        removePageItem(targetFrame);
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
        return frame;
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

    function fitItemWithinBounds(item, bounds, action) {
        if (!bounds) return;
        var targetWidth = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var targetHeight = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        if (targetWidth <= 0 || targetHeight <= 0) return;
        if (isPathTextFrame(item)) {
            fitPathTextWithinBounds(item, bounds, action, targetWidth, targetHeight);
            return;
        }
        var shrinkCount = 0;
        var smallestScale = 1;
        for (var index = 0; index < 20; index++) {
            var current = measuredBounds(item);
            var width = Math.abs(Number(current[2]) - Number(current[0]));
            var height = Math.abs(Number(current[1]) - Number(current[3]));
            if (width <= targetWidth && height <= targetHeight) break;
            var scale = Math.min(targetWidth / width, targetHeight / height) * 0.98;
            if (!isFinite(scale) || scale <= 0 || scale >= 1) break;
            shrinkCount += 1;
            smallestScale = Math.min(smallestScale, scale);
            try { item.resize(scale * 100, scale * 100, true, true, true, true, 100, Transformation.CENTER); }
            catch (resizeError1) {
                try { item.resize(scale * 100, scale * 100); } catch (resizeError2) { break; }
            }
        }
        centerItemInBounds(item, bounds);
        var finalBounds = measuredBounds(item);
        var finalWidth = Math.abs(Number(finalBounds[2]) - Number(finalBounds[0]));
        var finalHeight = Math.abs(Number(finalBounds[1]) - Number(finalBounds[3]));
        if (finalWidth > targetWidth || finalHeight > targetHeight) {
            layoutWarnings.push({
                code: "text_fit_extreme",
                severity: "warning",
                slot_key: String(action && action.slot_key || ""),
                object_path: String(action && action.object_path || ""),
                actual_width: finalWidth,
                actual_height: finalHeight,
                target_width: targetWidth,
                target_height: targetHeight
            });
        } else if (shrinkCount > 0 && smallestScale < 0.35) {
            layoutWarnings.push({
                code: "text_fit_extreme",
                severity: "warning",
                slot_key: String(action && action.slot_key || ""),
                object_path: String(action && action.object_path || ""),
                shrink_count: shrinkCount,
                min_scale: smallestScale,
                target_width: targetWidth,
                target_height: targetHeight
            });
        }
    }

    function fitPathTextWithinBounds(item, bounds, action, targetWidth, targetHeight) {
        var shrinkCount = 0;
        var smallestScale = 1;
        for (var index = 0; index < 20; index++) {
            var current = measuredBounds(item);
            var width = Math.abs(Number(current[2]) - Number(current[0]));
            var height = Math.abs(Number(current[1]) - Number(current[3]));
            if (width <= targetWidth && height <= targetHeight) break;
            var scale = Math.min(targetWidth / width, targetHeight / height) * 0.98;
            if (!isFinite(scale) || scale <= 0 || scale >= 1) break;
            if (!scaleTextSize(item, scale)) break;
            shrinkCount += 1;
            smallestScale = Math.min(smallestScale, scale);
        }
        var finalBounds = measuredBounds(item);
        var finalWidth = Math.abs(Number(finalBounds[2]) - Number(finalBounds[0]));
        var finalHeight = Math.abs(Number(finalBounds[1]) - Number(finalBounds[3]));
        if (finalWidth > targetWidth || finalHeight > targetHeight) {
            throw new Error("V2 path text exceeds anchor bounds: " + String(action && action.slot_key || ""));
        }
        if (shrinkCount > 0 && smallestScale < 0.35) {
            layoutWarnings.push({
                code: "path_text_fit_extreme",
                severity: "warning",
                slot_key: String(action && action.slot_key || ""),
                object_path: String(action && action.object_path || ""),
                shrink_count: shrinkCount,
                min_scale: smallestScale,
                target_width: targetWidth,
                target_height: targetHeight
            });
        }
    }

    function isPathTextFrame(item) {
        if (!item || item.typename !== "TextFrame") return false;
        try {
            if (typeof TextType !== "undefined" && item.kind === TextType.PATHTEXT) return true;
        } catch (typeError) {}
        try {
            return String(item.kind || "").toLowerCase().indexOf("path") >= 0;
        } catch (kindError) {}
        return false;
    }

    function scaleTextSize(item, scale) {
        try {
            var attributes = item.textRange.characterAttributes;
            var size = Number(attributes.size);
            if (!isFinite(size) || size <= 0) return false;
            attributes.size = size * scale;
            return true;
        } catch (sizeError) {}
        return false;
    }

    function centerItemInBounds(item, bounds) {
        var current = measuredBounds(item);
        var itemCenterX = (Number(current[0]) + Number(current[2])) / 2;
        var itemCenterY = (Number(current[1]) + Number(current[3])) / 2;
        var targetCenterX = (Number(bounds[0]) + Number(bounds[2])) / 2;
        var targetCenterY = (Number(bounds[1]) + Number(bounds[3])) / 2;
        item.translate(targetCenterX - itemCenterX, targetCenterY - itemCenterY);
    }

    function measuredBounds(item) {
        try {
            var visible = item.visibleBounds;
            if (validBounds(visible)) return visible;
        } catch (visibleError) {}
        try {
            var geometric = item.geometricBounds;
            if (validBounds(geometric)) return geometric;
        } catch (geometricError) {}
        throw new Error("Cannot measure V2 item bounds");
    }

    function visibleBoundsStrict(item) {
        try {
            var visible = item.visibleBounds;
            if (validBounds(visible)) return visible;
        } catch (visibleError) {}
        throw new Error("Cannot measure V2 output visible bounds");
    }

    function validBounds(bounds) {
        return bounds && bounds.length >= 4 && isFinite(Number(bounds[0])) && isFinite(Number(bounds[1])) && isFinite(Number(bounds[2])) && isFinite(Number(bounds[3]));
    }

    function fitRenderedOutput(items, action) {
        var dimensions = action.dimensions || {};
        var targetWidth = mmToPt(Number(dimensions.width_mm || 0));
        var targetHeight = mmToPt(Number(dimensions.height_mm || 0));
        if (targetWidth <= 0 || targetHeight <= 0) throw new Error("V2 output target dimensions are invalid");
        var bounds = unionBounds(items, true);
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        if (width <= 0 || height <= 0) throw new Error("V2 output visible bounds are not measurable");
        var fitInset = Math.min(mmToPt(0.001), targetWidth / 1000, targetHeight / 1000);
        var fitTargetWidth = targetWidth - fitInset;
        var fitTargetHeight = targetHeight - fitInset;
        var scaleX = fitTargetWidth / width * 100;
        var scaleY = fitTargetHeight / height * 100;
        for (var index = 0; index < items.length; index++) {
            try { items[index].resize(scaleX, scaleY, true, true, true, true, 100, Transformation.CENTER); }
            catch (resizeError1) {
                try { items[index].resize(scaleX, scaleY); } catch (resizeError2) { throw resizeError2; }
            }
        }
        var fitted = unionBounds(items, true);
        var targetLeft = Number(bounds[0]);
        var targetTop = Number(bounds[1]);
        translateItems(items, targetLeft - Number(fitted[0]), targetTop - Number(fitted[1]));
        validateOutputBounds(items, targetWidth, targetHeight);
    }

    function validateOutputBounds(items, targetWidth, targetHeight) {
        var bounds = unionBounds(items, true);
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        var tolerance = mmToPt(0.007);
        if (width > targetWidth || height > targetHeight) {
            throw new Error("V2 output exceeds target bounds");
        }
        if (width < targetWidth - tolerance || height < targetHeight - tolerance) {
            throw new Error("V2 output is below target tolerance");
        }
    }

    function unionBounds(items, strictVisible) {
        if (!items || !items.length) throw new Error("V2 output has no rendered items");
        var result = null;
        for (var index = 0; index < items.length; index++) {
            var bounds = strictVisible ? visibleBoundsStrict(items[index]) : measuredBounds(items[index]);
            if (!result) {
                result = [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
            } else {
                result[0] = Math.min(result[0], Number(bounds[0]));
                result[1] = Math.max(result[1], Number(bounds[1]));
                result[2] = Math.max(result[2], Number(bounds[2]));
                result[3] = Math.min(result[3], Number(bounds[3]));
            }
        }
        return result;
    }

    function translateItems(items, dx, dy) {
        for (var index = 0; index < items.length; index++) {
            items[index].translate(dx, dy);
        }
    }

    function cleanupAuxiliaryObjects(items) {
        for (var index = 0; index < items.length; index++) {
            cleanupAuxiliaryIn(items[index]);
        }
    }

    function cleanupAuxiliaryIn(item) {
        var children = item.pageItems || [];
        for (var index = children.length - 1; index >= 0; index--) {
            var child = children[index];
            if (isAuxiliaryObject(child)) {
                removePageItem(child);
            } else {
                cleanupAuxiliaryIn(child);
            }
        }
    }

    function isAuxiliaryObject(item) {
        var name = String(item && item.name || "");
        return name.indexOf("anchor_") === 0 || name.indexOf("size_") === 0 || name.indexOf("dimension_") === 0;
    }

    function mmToPt(mm) {
        return mm * 72 / 25.4;
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

    function splitPart(parts, rawIndex) {
        var index = Number(rawIndex || 0);
        if (!isFinite(index) || index < 0) index = 0;
        return parts[Math.floor(index)] || "";
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

    function writeLayoutWarnings(path, warnings) {
        if (!path) return;
        var file = File(String(path));
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write V2 layout warnings: " + file.fsName);
        file.write(JSON.stringify({warnings: warnings || []}));
        file.close();
    }
}());
