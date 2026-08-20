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
    var selectedOutputKey = String(execution.output_key || "");
    var renderedOutputItems = [];
    var renderedOutputCount = 0;
    var tailPuaBaseCache = {};

    try {
        for (var outputIndex = 0; outputIndex < (task.outputs || []).length; outputIndex++) {
            var taskOutput = task.outputs[outputIndex] || {};
            if (selectedOutputKey && String(taskOutput.key || "") !== selectedOutputKey) continue;
            renderedOutputItems = renderedOutputItems.concat(renderOutput(templateDoc, layer, taskOutput, values, selections));
            renderedOutputCount += 1;
        }
        if (selectedOutputKey && renderedOutputCount !== 1) throw new Error("Selected V2 output was not rendered: " + selectedOutputKey);
        if (execution.pack_order_blocks === true) {
            renderedOutputItems = [groupRenderedOutputBlock(layer, renderedOutputItems, 0)];
        }
        applyOutputTransforms(doc, execution.output || task.output || {});
        var finalFitAction = selectedFitAction(task, selectedOutputKey, selections);
        if (finalFitAction) fitRenderedOutput(renderedOutputItems, finalFitAction);
        if (execution.preview_png) fitArtboardToVisibleContent(doc, renderedOutputItems, 0);
        var output = File(String(execution.output_ai));
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        saveAsAI8(doc, output);
        if (execution.preview_png) {
            fitArtboardToVisibleContent(doc, renderedOutputItems, 12);
            exportPreviewPNG(doc, File(String(execution.preview_png)), execution.preview_dpi);
        }
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
            if (action.type === "select_style" && isSelected(action, selected)) {
                copied[copyKey(outputKey, action)] = copyOptionGroup(sourceDoc, targetLayer, action.object_path, action.source_only === true);
                if (action.source_only !== true) renderedItems.push(copied[copyKey(outputKey, action)].item);
            }
            if (action.type === "copy_option_group" && isSelected(action, selected)) {
                copied[copyKey(outputKey, action)] = copyOptionGroup(sourceDoc, targetLayer, action.object_path, action.source_only === true);
                if (action.source_only !== true) renderedItems.push(copied[copyKey(outputKey, action)].item);
            }
        }
        for (var assetIndex = 0; assetIndex < actions.length; assetIndex++) {
            var assetAction = actions[assetIndex] || {};
            if (assetAction.type === "bind_asset_library" && isSelected(assetAction, selected)) {
                bindAssetLibrary(copied, outputKey, assetAction, valuesByField);
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
        return renderedItems;
    }

    function selectedFitAction(taskData, outputKey, selectedValues) {
        var chosen = String(outputKey || "");
        var outputs = taskData.outputs || [];
        for (var outputIndex = 0; outputIndex < outputs.length; outputIndex++) {
            var output = outputs[outputIndex] || {};
            if (chosen && String(output.key || "") !== chosen) continue;
            var selected = selectedValues[String(output.key || "")] || {};
            var actions = output.actions || [];
            for (var actionIndex = 0; actionIndex < actions.length; actionIndex++) {
                var action = actions[actionIndex] || {};
                if (action.type === "fit_output_bounds" && String(selected.style || "") === String(action.style_key || "")) return action;
            }
        }
        return null;
    }

    function applyOutputTransforms(doc, policy) {
        if (!policy || policy.outline_text !== true) return;
        outlineAllTextFrames(doc, policy.pathfinder_merge === true);
    }

    function outlineAllTextFrames(doc, pathfinderMerge) {
        var frames = [];
        for (var layerIndex = 0; layerIndex < doc.layers.length; layerIndex++) collectTextFrames(doc.layers[layerIndex], frames);
        for (var index = frames.length - 1; index >= 0; index--) {
            var outline = frames[index].createOutline();
            if (!outline) throw new Error("V2 text outline failed");
            if (pathfinderMerge) cleanupOutline(outline);
        }
    }

    function collectTextFrames(container, result) {
        if (!container || !container.pageItems) return;
        for (var index = 0; index < container.pageItems.length; index++) {
            var item = container.pageItems[index];
            if (item.typename === "TextFrame") result.push(item);
            if (item.typename === "GroupItem" || item.typename === "Layer") collectTextFrames(item, result);
        }
    }

    function cleanupOutline(item) {
        if (!item) throw new Error("V2 outline item is missing");
        try { app.executeMenuCommand("deselectall"); } catch (ignored) {}
        item.selected = true;
        app.executeMenuCommand("Live Pathfinder Add");
        app.executeMenuCommand("expandStyle");
        item.selected = false;
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
        fitBounds = selectedStyleFitBoundsForFont(copied, outputKey, action, selected, fitBounds);
        var value = String(valuesByField[String(action.source_field || "")] || "");
        var parts = splitPipeValue(value);
        var preset = String(action.preset || "");
        var slotValue = preset === "split_by_pipe" ? splitPart(parts, action.source_part_index) : value;
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
        var tailSpecs = action.tails || [];
        if (preset === "tail_text" || (preset === "split_by_pipe" && tailSpecs.length)) {
            var tailSourceValue = preset === "split_by_pipe" ? slotValue : value;
            V2TailText.replaceTailText(
                tailTextEnvironment(),
                holder.item,
                holder.source_path,
                target,
                tailSourceValue,
                fitBounds,
                action
            );
            return;
        }
        var tailPaths = action.tail_paths || [];
        var directTailParts = tailSpecs.length && preset === "direct_text"
            ? applyDirectTailSamples(holder.item, holder.source_path, tailSpecs, slotValue)
            : null;
        var textFrame = writeTextToItem(target, directTailParts ? directTailParts.main_text : slotValue);
        fitItemWithinBounds(textFrame, fitBounds, action, shouldPreserveSlotComposition(target, action));
        if (directTailParts) {
            removeDirectTailSamples(holder.item, holder.source_path, tailSpecs);
            return;
        }
        for (var index = 0; index < tailPaths.length; index++) {
            var tail = findPageItemByRelativePath(holder.item, relativePath(String(tailPaths[index] || ""), holder.source_path));
            var tailText = preset === "split_by_pipe" ? parts[index + 1] || "" : "";
            if (hasText(tailText)) {
                var tailBounds = measuredBounds(tail);
                var tailFrame = writeTextToItem(tail, tailText);
                fitItemWithinBounds(tailFrame, tailBounds, action, shouldPreserveSlotComposition(tail, action));
            } else {
                removePageItem(tail);
            }
        }
    }

    function bindAssetLibrary(copied, outputKey, action, valuesByField) {
        var holder = copied[copyKey(outputKey, action)];
        if (!holder || !holder.item) throw new Error("Selected option was not copied: " + copyKey(outputKey, action));
        var sourceField = String(action.source_field || "");
        var rawValue = String(valuesByField[sourceField] || "");
        var targetKey = assetTargetKey(rawValue, action.supported_values || []);
        if (!targetKey) {
            if (action.required !== false) throw new Error("Required V2 asset slot has no value: " + sourceField);
            return;
        }
        var library = findPageItemByRelativePath(holder.item, relativePath(String(action.object_path || ""), holder.source_path));
        var slot = findPageItemByRelativePath(holder.item, relativePath(String(action.slot_path || ""), holder.source_path));
        var sourceAsset = findDirectChildByName(library, targetKey);
        if (!sourceAsset) throw new Error("V2 asset library has no item: " + targetKey);
        var parent = slot.parent || holder.item;
        var replacement = sourceAsset.duplicate(parent, ElementPlacement.PLACEATEND);
        fitItemWithinBounds(replacement, measuredBounds(slot), action);
        alignItemToItem(replacement, slot);
        removePageItem(slot);
        removePageItem(library);
    }

    function assetTargetKey(rawValue, supportedValues) {
        var value = String(rawValue || "").replace(/^\s+|\s+$/g, "");
        if (!value) return "";
        var exact = supportedAssetValue(value, supportedValues);
        if (exact) return exact;
        return supportedAssetValue(value.charAt(0).toUpperCase(), supportedValues);
    }

    function supportedAssetValue(value, supportedValues) {
        var target = String(value || "");
        if (!target) return "";
        for (var index = 0; index < supportedValues.length; index++) {
            var candidate = String(supportedValues[index] || "");
            if (candidate === target || candidate.toUpperCase() === target.toUpperCase()) return candidate;
        }
        return target.length === 1 ? target : "";
    }

    function findDirectChildByName(item, name) {
        var expected = String(name || "").toUpperCase();
        var children = item.pageItems || [];
        for (var index = 0; index < children.length; index++) {
            var childName = String(children[index].name || "");
            if (childName === name || childName.toUpperCase() === expected) return children[index];
        }
        return null;
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

    function selectedStyleFitBoundsForFont(copied, outputKey, action, selected, fallbackBounds) {
        if (!action || String(action.group || "") !== "font") return fallbackBounds;
        if (String(action.anchor_path || "")) return fallbackBounds;
        if (String(selected.design || "")) return fallbackBounds;
        var styleKey = String(selected.style || "");
        if (!styleKey) return fallbackBounds;
        var holder = copied[String(outputKey || "") + "|style|" + styleKey];
        if (!holder || !holder.item) return fallbackBounds;
        return measuredBounds(holder.item);
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

    function applyDirectTailSamples(root, sourcePath, tailSpecs, value) {
        var parsed = V2TailText.tailEndpointParts(String(value || ""), tailSpecs);
        var replacements = [];
        for (var index = 0; index < tailSpecs.length; index++) {
            var spec = tailSpecs[index] || {};
            var position = String(spec.position || "");
            var endpointIndex = position === "first" ? parsed.first_index : (position === "last" ? parsed.last_index : -1);
            var endpoint = position === "first" ? parsed.first_tail : (position === "last" ? parsed.last_tail : "");
            if (endpointIndex < 0 || !hasText(endpoint)) continue;
            var tail = findPageItemByRelativePath(root, relativePath(String(spec.path || ""), sourcePath));
            var tailFrame = firstTextFrame(tail);
            if (!tailFrame) throw new Error("V2 tail sample has no text frame: " + String(spec.key || ""));
            var glyph = directTailGlyph(tailFrame, endpoint, spec, position);
            var segment = V2TailText.tailSampleSegment(String(tailFrame.contents || ""), glyph, position);
            replacements.push({
                index: endpointIndex,
                text: segment.text
            });
        }
        replacements.sort(function (left, right) { return right.index - left.index; });
        var text = String(value || "");
        for (var replacementIndex = 0; replacementIndex < replacements.length; replacementIndex++) {
            var replacement = replacements[replacementIndex];
            text = text.substring(0, replacement.index) + replacement.text + text.substring(replacement.index + 1);
        }
        parsed.main_text = text;
        return parsed;
    }

    function directTailGlyph(tailFrame, endpoint, spec, position) {
        var letter = String(endpoint || "").toLowerCase();
        var fallback = V2TailText.tailGlyphForSpec(letter, spec);
        if (!isPlainTextTailSpec(spec)) return fallback;
        var sampleText = String(tailFrame.contents || "");
        var sampleIndex = tailSampleLatinIndex(sampleText, position);
        if (sampleText.length !== 1 || sampleIndex !== 0) return fallback;
        var base = inferPuaBaseFromTailSample(tailFrame, sampleText.charAt(0).toLowerCase());
        return base ? String.fromCharCode(base + letter.charCodeAt(0) - 97) : fallback;
    }

    function tailSampleLatinIndex(text, position) {
        var start = position === "first" ? 0 : String(text || "").length - 1;
        var step = position === "first" ? 1 : -1;
        for (var index = start; index >= 0 && index < String(text || "").length; index += step) {
            if (/^[A-Za-z]$/.test(String(text || "").charAt(index))) return index;
        }
        return -1;
    }

    function isPlainTextTailSpec(spec) {
        if (String((spec || {}).glyph_mode || "") !== "plain_text") return false;
        if ((spec || {}).pua_base !== undefined && String((spec || {}).pua_base || "") !== "") return false;
        var map = (spec || {}).glyph_map || {};
        for (var key in map) if (map.hasOwnProperty(key)) return false;
        return true;
    }

    function inferPuaBaseFromTailSample(frame, sampleLetter) {
        var sampleIndex = sampleLetter.charCodeAt(0) - 97;
        if (sampleIndex < 0 || sampleIndex > 25) return 0;
        var sourceEvidence = outlinedTextEvidence(frame);
        if (!sourceEvidence) return 0;
        var sourceWidth = Math.abs(Number(sourceEvidence.bounds[2]) - Number(sourceEvidence.bounds[0]));
        var sourceHeight = Math.abs(Number(sourceEvidence.bounds[1]) - Number(sourceEvidence.bounds[3]));
        if (sourceWidth <= 0 || sourceHeight <= 0 || !sourceEvidence.signature) return 0;
        var cacheKey = tailPuaSampleCacheKey(frame, sampleLetter, sourceWidth, sourceHeight);
        if (tailPuaBaseCache.hasOwnProperty(cacheKey)) return tailPuaBaseCache[cacheKey];
        var base = 0;
        for (var candidate = 0xE000; candidate <= 0xF8FF - 25; candidate++) {
            var candidateEvidence = outlinedTailGlyphEvidence(frame, candidate + sampleIndex);
            if (!candidateEvidence || candidateEvidence.signature !== sourceEvidence.signature) continue;
            if (puaTailAlphabetIsComplete(frame, candidate)) {
                base = candidate;
                break;
            }
        }
        tailPuaBaseCache[cacheKey] = base;
        return base;
    }

    function tailPuaSampleCacheKey(frame, sampleLetter, width, height) {
        var fontName = "";
        try { fontName = String(frame.textRange.characterAttributes.textFont.name || ""); } catch (error) {}
        return fontName + "|" + sampleLetter + "|" + Math.round(width * 100) + "x" + Math.round(height * 100);
    }

    function puaTailAlphabetIsComplete(frame, base) {
        var signatures = {};
        for (var index = 0; index < 26; index++) {
            var evidence = outlinedTailGlyphEvidence(frame, base + index);
            if (!evidence || !evidence.signature || signatures.hasOwnProperty(evidence.signature)) return false;
            signatures[evidence.signature] = true;
        }
        return true;
    }

    function outlinedTailGlyphEvidence(frame, code) {
        var duplicate = null;
        try {
            duplicate = frame.duplicate();
            duplicate.contents = String.fromCharCode(code);
            return outlinedTextEvidence(duplicate);
        } catch (error) {
            return null;
        } finally {
            removePageItem(duplicate);
        }
    }

    function outlinedTextEvidence(frame) {
        var duplicate = null;
        var outlined = null;
        try {
            duplicate = frame.duplicate();
            outlined = duplicate.createOutline();
            var bounds = measuredBounds(outlined);
            var signature = outlineGeometrySignature(outlined, bounds);
            return signature ? { bounds: bounds, signature: signature } : null;
        } catch (error) {
            return null;
        } finally {
            removePageItem(outlined || duplicate);
        }
    }

    function outlineGeometrySignature(item, bounds) {
        var paths = [];
        collectOutlinePathSignatures(item, bounds, paths);
        if (!paths.length) return "";
        paths.sort();
        return paths.join("|");
    }

    function collectOutlinePathSignatures(item, bounds, paths) {
        if (!item) return;
        if (item.typename === "PathItem") {
            var signature = outlinePathSignature(item, bounds);
            if (signature) paths.push(signature);
            return;
        }
        if (item.typename === "CompoundPathItem" && item.pathItems) {
            for (var pathIndex = 0; pathIndex < item.pathItems.length; pathIndex++) {
                collectOutlinePathSignatures(item.pathItems[pathIndex], bounds, paths);
            }
            return;
        }
        var children = item.pageItems || [];
        for (var childIndex = 0; childIndex < children.length; childIndex++) {
            collectOutlinePathSignatures(children[childIndex], bounds, paths);
        }
    }

    function outlinePathSignature(path, bounds) {
        var points = path.pathPoints || [];
        if (!points.length) return "";
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        if (width <= 0 || height <= 0) return "";
        var result = String(path.closed === true ? "C" : "O") + ":" + points.length;
        for (var index = 0; index < points.length; index++) {
            var point = points[index];
            result += ":" + outlinePointSignature(point.anchor, bounds, width, height);
            result += ":" + outlinePointSignature(point.leftDirection, bounds, width, height);
            result += ":" + outlinePointSignature(point.rightDirection, bounds, width, height);
        }
        return result;
    }

    function outlinePointSignature(point, bounds, width, height) {
        if (!point || point.length < 2) return "?";
        return Math.round((Number(point[0]) - Number(bounds[0])) * 1000 / width)
            + "," + Math.round((Number(point[1]) - Number(bounds[3])) * 1000 / height);
    }

    function removeDirectTailSamples(root, sourcePath, tailSpecs) {
        for (var index = 0; index < tailSpecs.length; index++) {
            var path = String((tailSpecs[index] || {}).path || "");
            if (path) removePageItem(findPageItemByRelativePath(root, relativePath(path, sourcePath)));
        }
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

    function fitItemWithinBounds(item, bounds, action, preserveComposition) {
        if (!bounds) return;
        preserveComposition = preserveComposition === true || (action && action.preserve_composition === true);
        var targetWidth = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var targetHeight = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        if (targetWidth <= 0 || targetHeight <= 0) return;
        if (isPathTextFrame(item)) {
            fitPathTextWithinBounds(item, bounds, action, targetWidth, targetHeight);
            return;
        }
        var resizeCount = 0;
        var smallestScale = 1;
        for (var index = 0; index < 20; index++) {
            var current = measuredBounds(item);
            var width = Math.abs(Number(current[2]) - Number(current[0]));
            var height = Math.abs(Number(current[1]) - Number(current[3]));
            if (width <= 0 || height <= 0) break;
            var scaleX = targetWidth / width;
            var scaleY = targetHeight / height;
            if (preserveComposition) {
                if (width <= targetWidth && height <= targetHeight) break;
                var proportionalScale = Math.min(scaleX, scaleY);
                scaleX = proportionalScale;
                scaleY = proportionalScale;
            }
            if (!isFinite(scaleX) || !isFinite(scaleY) || scaleX <= 0 || scaleY <= 0) break;
            if (Math.abs(scaleX - 1) <= 0.001 && Math.abs(scaleY - 1) <= 0.001) break;
            resizeCount += 1;
            smallestScale = Math.min(smallestScale, Math.min(scaleX, scaleY));
            try { item.resize(scaleX * 100, scaleY * 100, true, true, true, true, 100, Transformation.CENTER); }
            catch (resizeError1) {
                try { item.resize(scaleX * 100, scaleY * 100); } catch (resizeError2) { break; }
            }
        }
        centerItemInBounds(item, bounds);
        var finalBounds = measuredBounds(item);
        var finalWidth = Math.abs(Number(finalBounds[2]) - Number(finalBounds[0]));
        var finalHeight = Math.abs(Number(finalBounds[1]) - Number(finalBounds[3]));
        var boundsTolerance = mmToPt(0.007);
        if (finalWidth > targetWidth + boundsTolerance || finalHeight > targetHeight + boundsTolerance) {
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
        } else if (resizeCount > 0 && smallestScale < 0.35) {
            layoutWarnings.push({
                code: "text_fit_extreme",
                severity: "warning",
                slot_key: String(action && action.slot_key || ""),
                object_path: String(action && action.object_path || ""),
                shrink_count: resizeCount,
                min_scale: smallestScale,
                target_width: targetWidth,
                target_height: targetHeight
            });
        }
    }

    function shouldPreserveSlotComposition(slot, action) {
        if (action && action.preserve_composition === true) return true;
        return slotHasKeepRatioMarker(slot);
    }

    function slotHasKeepRatioMarker(slot) {
        if (!slot || !slot.pageItems || !slot.pageItems.length) return false;
        var children = slot.pageItems || [];
        for (var index = 0; index < children.length; index++) {
            if (hasKeepRatioMarker(children[index])) return true;
        }
        return false;
    }

    function hasKeepRatioMarker(item) {
        if (!item) return false;
        var name = normalizedName(item.name);
        if (name === "keep_ratio" || name.indexOf("keep_ratio_") === 0) return true;
        var children = item.pageItems || [];
        for (var index = 0; index < children.length; index++) {
            if (hasKeepRatioMarker(children[index])) return true;
        }
        return false;
    }

    function normalizedName(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "").toLowerCase();
    }

    function fitPathTextWithinBounds(item, bounds, action, targetWidth, targetHeight) {
        var resizeCount = 0;
        var smallestScale = 1;
        for (var index = 0; index < 20; index++) {
            var current = measuredBounds(item);
            var width = Math.abs(Number(current[2]) - Number(current[0]));
            var height = Math.abs(Number(current[1]) - Number(current[3]));
            if (width <= 0 || height <= 0) break;
            var scale = Math.min(targetWidth / width, targetHeight / height);
            if (!isFinite(scale) || scale <= 0 || Math.abs(scale - 1) <= 0.001) break;
            if (!scaleTextSize(item, scale)) break;
            resizeCount += 1;
            if (scale < 1) smallestScale = Math.min(smallestScale, scale);
        }
        var finalBounds = measuredBounds(item);
        var finalWidth = Math.abs(Number(finalBounds[2]) - Number(finalBounds[0]));
        var finalHeight = Math.abs(Number(finalBounds[1]) - Number(finalBounds[3]));
        var boundsTolerance = mmToPt(0.007);
        if (finalWidth > targetWidth + boundsTolerance || finalHeight > targetHeight + boundsTolerance) {
            throw new Error("V2 path text exceeds anchor bounds: " + String(action && action.slot_key || ""));
        }
        if (resizeCount > 0 && smallestScale < 0.35) {
            layoutWarnings.push({
                code: "path_text_fit_extreme",
                severity: "warning",
                slot_key: String(action && action.slot_key || ""),
                object_path: String(action && action.object_path || ""),
                shrink_count: resizeCount,
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
        var fitSafety = outputFitSafetyPoints(dimensions);
        var fitTargetWidth = targetWidth - fitSafety;
        var fitTargetHeight = targetHeight - fitSafety;
        var targetLeft = Number(bounds[0]);
        var targetTop = Number(bounds[1]);
        for (var attempt = 0; attempt < 4; attempt++) {
            var current = unionBounds(items, true);
            var width = Math.abs(Number(current[2]) - Number(current[0]));
            var height = Math.abs(Number(current[1]) - Number(current[3]));
            if (width <= 0 || height <= 0) throw new Error("V2 output visible bounds are not measurable");
            var scaleX = fitTargetWidth / width * 100;
            var scaleY = fitTargetHeight / height * 100;
            if (Math.abs(scaleX - 100) <= 0.001 && Math.abs(scaleY - 100) <= 0.001
                && outputBoundsWithinTargetRange(current, targetWidth, targetHeight, dimensions)) break;
            resizeItemsAroundBounds(items, current, scaleX, scaleY);
            var fitted = unionBounds(items, true);
            translateItems(items, targetLeft - Number(fitted[0]), targetTop - Number(fitted[1]));
            if (outputBoundsWithinTargetRange(fitted, targetWidth, targetHeight, dimensions)) break;
        }
        validateOutputBounds(items, dimensions, targetWidth, targetHeight);
    }

    function resizeItemsAroundBounds(items, bounds, scaleX, scaleY) {
        var scaleXRatio = Number(scaleX) / 100;
        var scaleYRatio = Number(scaleY) / 100;
        var centerX = (Number(bounds[0]) + Number(bounds[2])) / 2;
        var centerY = (Number(bounds[1]) + Number(bounds[3])) / 2;
        for (var index = 0; index < items.length; index++) {
            var itemBounds = visibleBoundsStrict(items[index]);
            var itemCenterX = (Number(itemBounds[0]) + Number(itemBounds[2])) / 2;
            var itemCenterY = (Number(itemBounds[1]) + Number(itemBounds[3])) / 2;
            var targetCenterX = centerX + (itemCenterX - centerX) * scaleXRatio;
            var targetCenterY = centerY + (itemCenterY - centerY) * scaleYRatio;
            resizePageItem(items[index], scaleX, scaleY);
            var resized = visibleBoundsStrict(items[index]);
            var resizedCenterX = (Number(resized[0]) + Number(resized[2])) / 2;
            var resizedCenterY = (Number(resized[1]) + Number(resized[3])) / 2;
            items[index].translate(targetCenterX - resizedCenterX, targetCenterY - resizedCenterY);
        }
    }

    function resizePageItem(item, scaleX, scaleY) {
        try { item.resize(scaleX, scaleY, true, true, true, true, 100, Transformation.CENTER); }
        catch (resizeError1) {
            try { item.resize(scaleX, scaleY); } catch (resizeError2) { throw resizeError2; }
        }
    }

    function validateOutputBounds(items, dimensions, targetWidth, targetHeight) {
        var bounds = unionBounds(items, true);
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        var epsilon = dimensionTolerancePoints(dimensions);
        if (width > targetWidth || height > targetHeight
            || width < targetWidth - epsilon || height < targetHeight - epsilon) {
            throw new Error(
                "V2 output exceeds target bounds or does not match target bounds: actual="
                + width + "x" + height
                + ", target=" + targetWidth + "x" + targetHeight
                + ", tolerance=" + epsilon
            );
        }
    }

    function outputBoundsWithinTargetRange(bounds, targetWidth, targetHeight, dimensions) {
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        var epsilon = dimensionTolerancePoints(dimensions);
        return width <= targetWidth && height <= targetHeight
            && width >= targetWidth - epsilon && height >= targetHeight - epsilon;
    }

    function dimensionTolerancePoints(dimensions) {
        var toleranceMm = Number(dimensions && dimensions.tolerance_mm);
        if (!isFinite(toleranceMm) || toleranceMm < 0) toleranceMm = 0.007;
        return mmToPt(Math.min(toleranceMm, 0.007));
    }

    function outputFitSafetyPoints(dimensions) {
        // Illustrator reports visible bounds on a point grid. Keep the fit target
        // inside the frame so a sub-point rounding step cannot create an overflow.
        return Math.min(0.003, dimensionTolerancePoints(dimensions) / 2);
    }

    function fitArtboardToVisibleContent(doc, items, padding) {
        var bounds = unionBounds(items, true);
        if (!doc.artboards || !doc.artboards.length) throw new Error("V2 preview artboard is unavailable");
        var margin = Number(padding || 0);
        doc.artboards[0].artboardRect = [
            Number(bounds[0]) - margin,
            Number(bounds[1]) + margin,
            Number(bounds[2]) + margin,
            Number(bounds[3]) - margin
        ];
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

    function groupRenderedOutputBlock(layer, items, blockIndex) {
        var candidates = directRenderableItems(items);
        if (!candidates.length) throw new Error("V2 order block has no artwork");
        if (candidates.length === 1 && candidates[0].typename === "GroupItem") {
            candidates[0].name = "ORDER_PACK_BLOCK_" + blockIndex;
            return candidates[0];
        }
        var domGroup = groupRenderedOutputBlockByDom(layer, candidates, blockIndex);
        if (domGroup) return domGroup;
        var doc = app.activeDocument;
        doc.selection = null;
        for (var index = 0; index < candidates.length; index++) {
            candidates[index].selected = true;
        }
        app.executeMenuCommand("group");
        var block = doc.selection.length ? doc.selection[0] : null;
        if (!block || block.typename !== "GroupItem") throw new Error("Cannot create V2 order block");
        block.name = "ORDER_PACK_BLOCK_" + blockIndex;
        doc.selection = null;
        return block;
    }

    function groupRenderedOutputBlockByDom(layer, candidates, blockIndex) {
        var group = null;
        var moved = [];
        try {
            if (!layer || !layer.groupItems || !layer.groupItems.add) return null;
            group = layer.groupItems.add();
            group.name = "ORDER_PACK_BLOCK_" + blockIndex;
            for (var index = 0; index < candidates.length; index++) {
                candidates[index].move(group, ElementPlacement.PLACEATEND);
                moved.push(candidates[index]);
            }
            return group;
        } catch (ignored) {
            cleanupFailedDomGroup(layer, group, moved);
            return null;
        }
    }

    function cleanupFailedDomGroup(layer, group, moved) {
        try {
            for (var index = moved.length - 1; index >= 0; index--) {
                moved[index].move(layer, ElementPlacement.PLACEATEND);
            }
            if (group && group.remove) group.remove();
        } catch (cleanupIgnored) {
        }
    }

    function directRenderableItems(items) {
        var result = [];
        for (var index = 0; index < items.length; index++) {
            var item = items[index];
            if (!item || item.hidden === true) continue;
            if (containsSamePageItem(result, item)) continue;
            result.push(item);
        }
        return result;
    }

    function containsSamePageItem(items, candidate) {
        for (var index = 0; index < items.length; index++) {
            if (items[index] === candidate) return true;
        }
        return false;
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
        var normalized = normalizedName(name);
        return normalized === "keep_ratio" || name === "Assets" || name.indexOf("anchor_") === 0 || name.indexOf("size_") === 0 || name.indexOf("dimension_") === 0;
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
        for (var index = 0; index < raw.length; index++) {
            var part = String(raw[index] || "").replace(/^\s+|\s+$/g, "");
            if (part) parts.push(part);
        }
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
        return parseJsonFallback(String(text || ""));
    }

    function parseJsonFallback(text) {
        var index = 0;

        function fail(message) {
            throw new Error("Invalid JSON task file: " + message);
        }

        function skipWhitespace() {
            while (index < text.length && /[\s]/.test(text.charAt(index))) index++;
        }

        function parseValue() {
            skipWhitespace();
            var ch = text.charAt(index);
            if (ch === '"') return parseString();
            if (ch === "{") return parseObject();
            if (ch === "[") return parseArray();
            if (ch === "t") return parseLiteral("true", true);
            if (ch === "f") return parseLiteral("false", false);
            if (ch === "n") return parseLiteral("null", null);
            if (ch === "-" || (ch >= "0" && ch <= "9")) return parseNumber();
            fail("unexpected token at " + index);
        }

        function parseLiteral(token, value) {
            if (text.substr(index, token.length) !== token) fail("invalid literal at " + index);
            index += token.length;
            return value;
        }

        function parseNumber() {
            var match = text.substring(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?/);
            if (!match) fail("invalid number at " + index);
            index += match[0].length;
            return Number(match[0]);
        }

        function parseString() {
            var result = "";
            index++;
            while (index < text.length) {
                var ch = text.charAt(index++);
                if (ch === '"') return result;
                if (ch !== "\\") {
                    result += ch;
                    continue;
                }
                if (index >= text.length) fail("unterminated escape");
                var esc = text.charAt(index++);
                if (esc === '"' || esc === "\\" || esc === "/") result += esc;
                else if (esc === "b") result += "\b";
                else if (esc === "f") result += "\f";
                else if (esc === "n") result += "\n";
                else if (esc === "r") result += "\r";
                else if (esc === "t") result += "\t";
                else if (esc === "u") {
                    var hex = text.substr(index, 4);
                    if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("invalid unicode escape at " + index);
                    result += String.fromCharCode(parseInt(hex, 16));
                    index += 4;
                } else {
                    fail("invalid escape at " + index);
                }
            }
            fail("unterminated string");
        }

        function parseArray() {
            var result = [];
            index++;
            skipWhitespace();
            if (text.charAt(index) === "]") {
                index++;
                return result;
            }
            while (index < text.length) {
                result.push(parseValue());
                skipWhitespace();
                var ch = text.charAt(index++);
                if (ch === "]") return result;
                if (ch !== ",") fail("expected comma in array");
            }
            fail("unterminated array");
        }

        function parseObject() {
            var result = {};
            index++;
            skipWhitespace();
            if (text.charAt(index) === "}") {
                index++;
                return result;
            }
            while (index < text.length) {
                skipWhitespace();
                if (text.charAt(index) !== '"') fail("expected object key");
                var key = parseString();
                skipWhitespace();
                if (text.charAt(index++) !== ":") fail("expected colon after object key");
                result[key] = parseValue();
                skipWhitespace();
                var ch = text.charAt(index++);
                if (ch === "}") return result;
                if (ch !== ",") fail("expected comma in object");
            }
            fail("unterminated object");
        }

        var parsed = parseValue();
        skipWhitespace();
        if (index !== text.length) fail("trailing content at " + index);
        return parsed;
    }

    function stringifyJson(value) {
        if (typeof JSON !== "undefined" && JSON.stringify) return JSON.stringify(value);
        return stringifyJsonFallback(value);
    }

    function stringifyJsonFallback(value) {
        if (value === null || value === undefined) return "null";
        var type = typeof value;
        if (type === "string") return quoteJsonString(value);
        if (type === "number") return isFinite(value) ? String(value) : "null";
        if (type === "boolean") return value ? "true" : "false";
        if (isArray(value)) {
            var parts = [];
            for (var index = 0; index < value.length; index++) parts.push(stringifyJsonFallback(value[index]));
            return "[" + parts.join(",") + "]";
        }
        var fields = [];
        for (var key in value) {
            if (Object.prototype.hasOwnProperty.call(value, key)) {
                fields.push(quoteJsonString(key) + ":" + stringifyJsonFallback(value[key]));
            }
        }
        return "{" + fields.join(",") + "}";
    }

    function quoteJsonString(value) {
        var text = String(value);
        var result = '"';
        for (var index = 0; index < text.length; index++) {
            var ch = text.charAt(index);
            var code = text.charCodeAt(index);
            if (ch === '"' || ch === "\\") result += "\\" + ch;
            else if (ch === "\b") result += "\\b";
            else if (ch === "\f") result += "\\f";
            else if (ch === "\n") result += "\\n";
            else if (ch === "\r") result += "\\r";
            else if (ch === "\t") result += "\\t";
            else if (code < 32) {
                var hex = code.toString(16);
                while (hex.length < 4) hex = "0" + hex;
                result += "\\u" + hex;
            } else {
                result += ch;
            }
        }
        return result + '"';
    }

    function isArray(value) {
        return Object.prototype.toString.call(value) === "[object Array]";
    }

    function saveAsAI8(doc, file) {
        var options = new IllustratorSaveOptions();
        options.compatibility = Compatibility.ILLUSTRATOR8;
        options.pdfCompatible = false;
        options.compressed = false;
        doc.saveAs(file, options);
    }

    function exportPreviewPNG(doc, file, dpi) {
        ensureFolder(file.parent);
        if (file.exists) file.remove();
        // Illustrator appends .png for PNG24 exports. Pass an extension-free
        // target so callers receive the exact preview_png path they requested.
        var exportTarget = File(String(file.fsName).replace(/\.png$/i, ""));
        var options = new ExportOptionsPNG24();
        var scale = Math.max(1, Number(dpi || 144) / 72 * 100);
        options.antiAliasing = true;
        options.artBoardClipping = true;
        options.transparency = true;
        options.horizontalScale = scale;
        options.verticalScale = scale;
        doc.exportFile(exportTarget, ExportType.PNG24, options);
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
        file.write(stringifyJson({warnings: warnings || []}));
        file.close();
    }
}());
