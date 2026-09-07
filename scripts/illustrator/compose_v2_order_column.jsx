#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    if (task.type !== "compose_v2_order_column") throw new Error("Unsupported compose task type");
    var inputs = task.inputs || [];
    if (!inputs.length) throw new Error("No V2 artwork inputs to compose");

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (ignored) {}

    var doc = app.documents.add(DocumentColorSpace.RGB, 1000, 1000);
    var layer = doc.layers[0];
    layer.name = "V2_ORDER_COLUMN";
    var gap = mmToPt(Number(task.gap_mm || 8));
    var labelLines = cleanLines(task.label_lines || []);
    var labelHeight = mmToPt(Number(task.label_height_mm || 4));
    var labelGap = mmToPt(Number(task.label_gap_mm || 0.8));
    var labelFontSize = Number(task.label_font_size_pt || 6);
    var orderBuckets = [];
    var orderBucketByKey = {};
    var composedItems = [];

    try {
        for (var inputIndex = 0; inputIndex < inputs.length; inputIndex++) {
            var input = inputs[inputIndex] || {};
            var sourcePath = String(input.path || "");
            if (!sourcePath) throw new Error("V2 compose input path missing");
            var componentFrame = readSingleComponentFrame(input);
            var source = app.open(File(sourcePath));
            try {
                var copied = duplicateVisibleArtwork(source, layer);
                if (!copied.length) throw new Error("V2 compose input has no artwork");
                for (var copiedIndex = 0; copiedIndex < copied.length; copiedIndex++) sanitizePackNames(copied[copiedIndex]);
                if (input.target_dimensions && (!input.target_dimensions.width_mm || !input.target_dimensions.height_mm)) throw new Error("V2 order column target dimensions missing");
                validateRequestedDimensions(componentFrame, input.target_dimensions || {});
                var item = groupPageItems(layer, copied, "ORDER_PACK_ITEM_PENDING_" + inputIndex);
                orderBucketFor(input, inputIndex).items.push({item: item, frame: componentFrame, source_path: sourcePath});
            } finally {
                try { source.close(SaveOptions.DONOTSAVECHANGES); } catch (closeSourceError) {}
            }
        }
        var orderBlocks = layoutOrderBlocks(layer, orderBuckets, gap, labelHeight, labelGap, labelFontSize);
        var allItems = orderBlocks.slice(0);
        if (labelLines.length) {
            var labelResult = addProductionLabels(layer, labelLines, orderBlocks, labelHeight, labelGap, labelFontSize);
            translateComposedFrames(composedItems, labelResult.order_translation.x, labelResult.order_translation.y);
            allItems = labelResult.items.concat(orderBlocks);
        }
        fitArtboard(doc, allItems);
        applyOutputTransforms(doc, task.output || {});
        writeComponentContract(task, composedItems);
        var output = File(String(task.output_ai || ""));
        ensureFolder(output.parent);
        if (output.exists) output.remove();
        saveAI(doc, output, String(task.compatibility || "Illustrator 8"));
        return output.fsName;
    } finally {
        try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeOutputError) {}
    }

    function duplicateVisibleArtwork(sourceDoc, targetLayer) {
        var copied = [];
        for (var layerIndex = 0; layerIndex < sourceDoc.layers.length; layerIndex++) {
            var sourceLayer = sourceDoc.layers[layerIndex];
            if (sourceLayer.visible === false) continue;
            var items = sourceLayer.pageItems || [];
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                var item = items[itemIndex];
                if (item.hidden === true) continue;
                copied.push(item.duplicate(targetLayer, ElementPlacement.PLACEATEND));
            }
        }
        return copied;
    }

    function applyOutputTransforms(doc, policy) {
        if (!policy || policy.outline_text !== true) return;
        var outlines = outlineCurrentTextFrames(doc, "V2 order column");
        if (policy.pathfinder_merge === true) mergeOverlappingTextOutlines(outlines, "V2 order column");
        assertNoTextFrames(doc, "V2 order column output");
    }

    function outlineCurrentTextFrames(doc, context) {
        var outlines = [];
        var safety = Number(doc.textFrames.length) + 1;
        while (doc.textFrames.length > 0) {
            if (safety-- <= 0) throw new Error(context + " text outline collection did not converge");
            var beforeCount = Number(doc.textFrames.length);
            var frame = doc.textFrames[beforeCount - 1];
            if (!frame || typeof frame.createOutline !== "function") throw new Error(context + " text outline source is invalid");
            var styleKey = uniformTextStyleKey(frame);
            var outline = frame.createOutline();
            if (!outline) throw new Error(context + " text outline failed");
            outlines.push({ item: outline, bounds: itemBounds(outline), styleKey: styleKey });
            if (Number(doc.textFrames.length) >= beforeCount) throw new Error(context + " text outline did not remove its source");
        }
        return outlines;
    }

    function mergeOverlappingTextOutlines(outlines, context) {
        var consumed = [];
        for (var index = 0; index < outlines.length; index++) consumed[index] = false;
        for (var start = 0; start < outlines.length; start++) {
            if (consumed[start]) continue;
            var cluster = [start];
            consumed[start] = true;
            for (var cursor = 0; cursor < cluster.length; cursor++) {
                var current = outlines[cluster[cursor]];
                for (var candidate = 0; candidate < outlines.length; candidate++) {
                    if (consumed[candidate] || !sameMergeStyle(current, outlines[candidate])) continue;
                    if (!boundsOverlap(current.bounds, outlines[candidate].bounds)) continue;
                    consumed[candidate] = true;
                    cluster.push(candidate);
                }
            }
            var items = [];
            for (var itemIndex = 0; itemIndex < cluster.length; itemIndex++) items.push(outlines[cluster[itemIndex]].item);
            mergeOutlineItems(items, context);
        }
    }

    function sameMergeStyle(left, right) {
        return left.styleKey !== null && right.styleKey !== null && left.styleKey === right.styleKey;
    }

    function boundsOverlap(left, right) {
        return Number(left[0]) < Number(right[2]) && Number(left[2]) > Number(right[0]) && Number(left[1]) > Number(right[3]) && Number(left[3]) < Number(right[1]);
    }

    function mergeOutlineItems(items, context) {
        if (items.length < 2) return;
        try { app.executeMenuCommand("deselectall"); } catch (ignored) {}
        try {
            for (var index = 0; index < items.length; index++) items[index].selected = true;
            app.executeMenuCommand("Live Pathfinder Add");
            app.executeMenuCommand("expandStyle");
        } catch (error) {
            throw new Error(context + " Pathfinder merge failed: " + error);
        } finally {
            try { app.executeMenuCommand("deselectall"); } catch (ignored2) {}
        }
    }

    function uniformTextStyleKey(frame) {
        var frameStyle = stylePropertyValues(frame, ["opacity", "blendingMode"]);
        var textRange = stylePropertyValues(frame, ["textRange"]);
        if (frameStyle === null || textRange === null) return null;
        var characters = stylePropertyValues(textRange[0], ["characters"]);
        if (characters === null || !characters[0] || !characters[0].length) return null;
        var key = null;
        for (var index = 0; index < characters[0].length; index++) {
            var attributes = stylePropertyValues(characters[0][index], ["characterAttributes"]);
            if (attributes === null) return null;
            var candidate = characterStyleKey(attributes[0]);
            if (candidate === null) return null;
            if (key === null) key = candidate;
            else if (key !== candidate) return null;
        }
        return key + "|opacity=" + frameStyle[0] + "|blend=" + frameStyle[1];
    }

    function characterStyleKey(attributes) {
        var style = stylePropertyValues(attributes, [
            "textFont", "fillColor", "strokeColor", "strokeWeight", "size",
            "horizontalScale", "verticalScale",
            "baselineShift", "tracking", "overprintFill", "overprintStroke"
        ]);
        if (style === null) return null;
        var font = stylePropertyValues(style[0], ["name"]);
        var fill = colorStyleKey(style[1]);
        var stroke = colorStyleKey(style[2]);
        if (font === null || fill === null || stroke === null) return null;
        return [
            fill, stroke,
            style[3], style[4], style[5], style[6], style[7],
            style[8], style[9], style[10], font[0]
        ].join("|");
    }

    function stylePropertyValues(object, names) {
        if (object === null || typeof object === "undefined") return null;
        var values = [];
        try {
            for (var index = 0; index < names.length; index++) {
                var value = object[names[index]];
                if (typeof value === "undefined") return null;
                values.push(value);
            }
        } catch (ignored) {
            return null;
        }
        return values;
    }

    function colorStyleKey(color) {
        var type = stylePropertyValues(color, ["typename"]);
        if (type === null) return null;
        if (type[0] === "CMYKColor") {
            var cmyk = stylePropertyValues(color, ["cyan", "magenta", "yellow", "black"]);
            return cmyk === null ? null : "CMYK:" + cmyk.join(",");
        }
        if (type[0] === "RGBColor") {
            var rgb = stylePropertyValues(color, ["red", "green", "blue"]);
            return rgb === null ? null : "RGB:" + rgb.join(",");
        }
        if (type[0] === "GrayColor") {
            var gray = stylePropertyValues(color, ["gray"]);
            return gray === null ? null : "Gray:" + gray[0];
        }
        if (type[0] === "LabColor") {
            var lab = stylePropertyValues(color, ["l", "a", "b"]);
            return lab === null ? null : "Lab:" + lab.join(",");
        }
        if (type[0] === "NoColor") return "NoColor";
        if (type[0] === "SpotColor") {
            var spot = stylePropertyValues(color, ["spot", "tint"]);
            if (spot === null) return null;
            var spotName = stylePropertyValues(spot[0], ["name"]);
            return spotName === null ? null : "Spot:" + spotName[0] + "," + spot[1];
        }
        // Gradient and pattern transforms are object-level state.  Without a
        // complete, stable signature they must never enter a cross-frame merge.
        return null;
    }

    function collectTextFrames(container, result) {
        if (!container || !container.pageItems) return;
        for (var index = 0; index < container.pageItems.length; index++) {
            var item = container.pageItems[index];
            if (item.parent !== container) continue;
            if (item.typename === "TextFrame") result.push(item);
            else if (item.typename === "GroupItem" || item.typename === "Layer") collectTextFrames(item, result);
        }
    }

    function assertNoTextFrames(doc, stage) {
        var remaining = [];
        for (var layerIndex = 0; layerIndex < doc.layers.length; layerIndex++) collectTextFrames(doc.layers[layerIndex], remaining);
        if (remaining.length) throw new Error(stage + " retains live text: " + remaining.length);
    }

    function orderBucketFor(input, inputIndex) {
        var orderNo = String(input.order_no || "").replace(/^\s+|\s+$/g, "");
        var annotationGroup = String(input.annotation_group || "").replace(/^\s+|\s+$/g, "");
        var key = annotationGroup || orderNo || "__input_" + inputIndex;
        var inputLabels = cleanLines(input.label_lines || []);
        if (!orderBucketByKey[key]) {
            orderBucketByKey[key] = { key: key, orderNo: orderNo, items: [], labelLines: inputLabels };
            orderBuckets.push(orderBucketByKey[key]);
        } else if (!orderBucketByKey[key].labelLines.length && inputLabels.length) {
            orderBucketByKey[key].labelLines = inputLabels;
        }
        return orderBucketByKey[key];
    }

    function layoutOrderBlocks(layer, buckets, gap, labelHeight, labelGap, labelFontSize) {
        var currentTop = 0;
        var outputItems = [];
        for (var orderIndex = 0; orderIndex < buckets.length; orderIndex++) {
            var bucket = buckets[orderIndex];
            for (var itemIndex = 0; itemIndex < bucket.items.length; itemIndex++) {
                bucket.items[itemIndex].item.name = "ORDER_PACK_ITEM_" + orderIndex + "_" + itemIndex;
            }
            var groupItems = [];
            for (var groupedIndex = 0; groupedIndex < bucket.items.length; groupedIndex++) {
                groupItems.push(bucket.items[groupedIndex].item);
            }
            var block = groupPageItems(layer, groupItems, "ORDER_PACK_BLOCK_" + orderIndex);
            var labelSpace = bucket.labelLines.length
                ? bucket.labelLines.length * labelHeight + Math.max(bucket.labelLines.length - 1, 0) * labelGap + labelGap
                : 0;
            var artworkTop = currentTop - labelSpace;
            for (var childIndex = 0; childIndex < bucket.items.length; childIndex++) {
                var entry = bucket.items[childIndex];
                var frame = entry.frame.frame_bounds;
                var dx = 0 - Number(frame[0]);
                var dy = artworkTop - Number(frame[1]);
                entry.copy_coordinate_translation = placeArtworkAtExpected(
                    entry.item,
                    entry.frame.artwork_bounds_after,
                    dx,
                    dy,
                    "order column placement"
                );
                entry.translation = {x: dx, y: dy};
                entry.final_frame_bounds = translateBounds(frame, dx, dy);
                entry.actual_artwork_bounds = verifyTranslatedArtwork(
                    entry.item,
                    entry.frame.artwork_bounds_after,
                    dx,
                    dy,
                    "order column placement"
                );
                entry.key = String(entry.item.name || "");
                composedItems.push(entry);
                artworkTop = Number(entry.final_frame_bounds[3]) - gap;
            }
            var blockItems = [block];
            if (bucket.labelLines.length) {
                var localLabels = addProductionLabelsAboveBlock(
                    layer,
                    bucket.labelLines,
                    block,
                    labelHeight,
                    labelGap,
                    labelFontSize
                );
                blockItems = localLabels.concat([block]);
            }
            var placed = unionBounds(blockItems);
            currentTop = Number(placed[3]) - gap;
            outputItems = outputItems.concat(blockItems);
        }
        if (!outputItems.length) throw new Error("V2 compose produced no order blocks");
        return outputItems;
    }

    function addProductionLabelsAboveBlock(layer, lines, block, labelHeight, labelGap, fontSize) {
        var bounds = unionBounds([block]);
        var width = Math.max(Number(bounds[2]) - Number(bounds[0]), mmToPt(30));
        var totalLabelHeight = lines.length * labelHeight + Math.max(lines.length - 1, 0) * labelGap;
        var labels = [];
        for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
            var top = Number(bounds[1]) + labelGap + totalLabelHeight - lineIndex * (labelHeight + labelGap);
            var label = drawLabel(layer, lines[lineIndex], Number(bounds[0]), top, Number(bounds[0]) + width, top - labelHeight, fontSize);
            if (label) labels.push(label);
        }
        return labels;
    }

    function translateItems(items, dx, dy) {
        for (var index = 0; index < items.length; index++) {
            items[index].translate(dx, dy);
        }
    }

    function groupPageItems(parent, items, name) {
        if (!items || !items.length) throw new Error("V2 compose group has no artwork");
        var group = createDomGroup(parent, name);
        if (group) {
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                items[itemIndex].move(group, ElementPlacement.PLACEATEND);
            }
            group.name = name;
            return group;
        }
        var doc = app.activeDocument;
        doc.selection = null;
        for (var index = 0; index < items.length; index++) {
            items[index].selected = true;
        }
        app.executeMenuCommand("group");
        group = doc.selection.length ? doc.selection[0] : null;
        if (!group || group.typename !== "GroupItem") throw new Error("Cannot create V2 compose group");
        group.name = name;
        doc.selection = null;
        return group;
    }

    function createDomGroup(parent, name) {
        try {
            if (parent.groupItems && parent.groupItems.add) {
                var group = parent.groupItems.add();
                group.name = name;
                return group;
            }
        } catch (groupError) {}
        return null;
    }

    function sanitizePackNames(item) {
        if (!item) return;
        if (/^ORDER_PACK_(?:BLOCK|ITEM)_/.test(String(item.name || ""))) {
            item.name = "SOURCE_" + item.name;
        }
        var children = item.pageItems || [];
        for (var childIndex = 0; childIndex < children.length; childIndex++) {
            sanitizePackNames(children[childIndex]);
        }
    }

    function addProductionLabels(layer, lines, orderBlocks, labelHeight, labelGap, fontSize) {
        var bounds = unionBounds(orderBlocks);
        var width = Math.max(Number(bounds[2]) - Number(bounds[0]), mmToPt(30));
        var totalLabelHeight = lines.length * labelHeight + Math.max(lines.length - 1, 0) * labelGap;
        var dx = 0 - Number(bounds[0]);
        var dy = -(totalLabelHeight + labelGap) - Number(bounds[1]);
        translateItems(orderBlocks, dx, dy);
        var labels = [];
        for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
            var top = -(lineIndex * (labelHeight + labelGap));
            var label = drawLabel(layer, lines[lineIndex], 0, top, width, top - labelHeight, fontSize);
            if (label) labels.push(label);
        }
        return {items: labels, order_translation: {x: dx, y: dy}};
    }

    function drawLabel(layer, text, left, top, right, bottom, size) {
        if (top <= bottom) return null;
        var frame = layer.textFrames.add();
        frame.contents = String(text || "");
        frame.textRange.characterAttributes.size = size;
        applyBlack(frame);
        fitLabelToRect(frame, [left, top, right, bottom], 3, size);
        return frame;
    }

    function fitLabelToRect(frame, rect, minSize, maxSize) {
        var rectWidth = rect[2] - rect[0];
        var rectHeight = rect[1] - rect[3];
        var size = maxSize;
        for (var attempt = 0; attempt < 12; attempt++) {
            frame.textRange.characterAttributes.size = size;
            var bounds = itemBounds(frame);
            var width = Math.max(bounds[2] - bounds[0], 0.01);
            var height = Math.max(bounds[1] - bounds[3], 0.01);
            if ((width <= rectWidth + 0.01 && height <= rectHeight + 0.01) || size <= minSize) break;
            size = Math.max(minSize, size * Math.min(rectWidth / width, rectHeight / height, 0.92));
        }
        var finalBounds = itemBounds(frame);
        var finalWidth = finalBounds[2] - finalBounds[0];
        var finalHeight = finalBounds[1] - finalBounds[3];
        var targetLeft = rect[0] + Math.max((rectWidth - finalWidth) / 2, 0);
        var targetTop = rect[1] - Math.max((rectHeight - finalHeight) / 2, 0);
        frame.translate(targetLeft - finalBounds[0], targetTop - finalBounds[1]);
    }

    function applyBlack(frame) {
        try {
            var color = new CMYKColor();
            color.cyan = 0;
            color.magenta = 0;
            color.yellow = 0;
            color.black = 100;
            frame.textRange.characterAttributes.fillColor = color;
        } catch (colorError) {}
    }

    function readSingleComponentFrame(input) {
        var path = String(input.component_contract_file || "");
        if (!path) throw new Error("V2 component frame contract path missing");
        var contract = readJSON(path);
        if (Number(contract.component_contract_version || 0) !== 1) throw new Error("Unsupported V2 component frame contract");
        var frames = contract.component_frames || [];
        if (frames.length !== 1) throw new Error("V2 component input must contain exactly one fixed frame");
        var frame = frames[0] || {};
        if (!validBounds(frame.frame_bounds)) throw new Error("V2 component frame bounds missing");
        if (!validBounds(frame.artwork_bounds_after)) throw new Error("V2 component artwork audit bounds missing");
        return {
            frame_bounds: copyBounds(frame.frame_bounds),
            artwork_bounds_after: copyBounds(frame.artwork_bounds_after),
            tracked_slots: frame.tracked_slots || [],
            source: String(frame.source || ""),
            output_key: String(frame.output_key || "")
        };
    }

    function validateRequestedDimensions(frame, dimensions) {
        var requestedWidth = mmToPt(Number(dimensions.width_mm || 0));
        var requestedHeight = mmToPt(Number(dimensions.height_mm || 0));
        if (requestedWidth <= 0 && requestedHeight <= 0) return;
        if (requestedWidth <= 0 || requestedHeight <= 0) throw new Error("V2 order column target dimensions missing");
        var width = Number(frame.frame_bounds[2]) - Number(frame.frame_bounds[0]);
        var height = Number(frame.frame_bounds[1]) - Number(frame.frame_bounds[3]);
        var epsilon = mmToPt(0.01);
        if (Math.abs(width - requestedWidth) > epsilon || Math.abs(height - requestedHeight) > epsilon) {
            throw new Error("V2 component frame does not match requested dimensions; refusing resize");
        }
    }

    function translateComposedFrames(entries, dx, dy) {
        for (var index = 0; index < entries.length; index++) {
            var entry = entries[index];
            entry.final_frame_bounds = translateBounds(entry.final_frame_bounds, dx, dy);
            entry.translation.x += dx;
            entry.translation.y += dy;
            entry.actual_artwork_bounds = verifyTranslatedArtwork(entry.item, entry.frame.artwork_bounds_after, entry.translation.x, entry.translation.y, "order column label placement");
        }
    }

    function translateBounds(bounds, dx, dy) {
        return [Number(bounds[0]) + Number(dx), Number(bounds[1]) + Number(dy), Number(bounds[2]) + Number(dx), Number(bounds[3]) + Number(dy)];
    }

    function copyBounds(bounds) {
        return [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
    }

    function verifyTranslatedArtwork(item, sourceBounds, dx, dy, stage) {
        var expected = translateBounds(sourceBounds, dx, dy);
        var actual = itemBounds(item);
        var epsilon = 1 / 64;
        for (var index = 0; index < 4; index++) {
            if (Math.abs(Number(actual[index]) - Number(expected[index])) > epsilon) {
                throw new Error("V2 component artwork bounds changed during " + stage + "; expected=" + expected + ", actual=" + actual);
            }
        }
        return copyBounds(actual);
    }

    function placeArtworkAtExpected(item, sourceBounds, logicalDx, logicalDy, stage) {
        var expected = translateBounds(sourceBounds, logicalDx, logicalDy);
        var actual = itemBounds(item);
        var copyDx = Number(expected[0]) - Number(actual[0]);
        var copyDy = Number(expected[1]) - Number(actual[1]);
        item.translate(copyDx, copyDy);
        return {x: copyDx, y: copyDy, stage: stage};
    }

    function translateTrackedSlots(trackedSlots, dx, dy) {
        var result = [];
        for (var index = 0; index < trackedSlots.length; index++) {
            var tracked = trackedSlots[index] || {};
            if (!validBounds(tracked.bounds)) throw new Error("V2 tracked slot bounds missing for " + tracked.slot_key);
            result.push({
                slot_key: String(tracked.slot_key || ""),
                track_name: String(tracked.track_name || ""),
                source_bounds: copyBounds(tracked.bounds),
                bounds: translateBounds(tracked.bounds, dx, dy),
                compose_translation: {x: Number(dx), y: Number(dy)}
            });
        }
        return result;
    }

    function writeComponentContract(task, entries) {
        var path = String(task.component_contract_file || "");
        if (!path) throw new Error("V2 composed output contract path missing");
        var frames = [];
        for (var index = 0; index < entries.length; index++) {
            var entry = entries[index];
            frames.push({
                key: String(entry.key || ""),
                frame_bounds: copyBounds(entry.final_frame_bounds),
                source_frame_bounds: copyBounds(entry.frame.frame_bounds),
                compose_translation: {x: Number(entry.translation.x), y: Number(entry.translation.y)},
                copy_coordinate_translation: entry.copy_coordinate_translation || {x: 0, y: 0},
                source_artwork_bounds: copyBounds(entry.frame.artwork_bounds_after),
                artwork_bounds_after: copyBounds(entry.actual_artwork_bounds),
                tracked_slots: translateTrackedSlots(entry.frame.tracked_slots || [], entry.translation.x, entry.translation.y),
                source: "compose_v2_order_column"
            });
        }
        var file = File(path);
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write V2 composed component contract: " + file.fsName);
        file.write(stringifyJson({component_contract_version: 1, component_frames: frames}));
        file.close();
    }

    function itemBounds(item) {
        var bounds = item.visibleBounds || item.geometricBounds;
        if (!validBounds(bounds)) throw new Error("V2 compose bounds are not measurable");
        return [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
    }

    function cleanLines(value) {
        var result = [];
        if (!value || typeof value.length === "undefined") return result;
        for (var index = 0; index < value.length; index++) {
            var text = String(value[index] || "").replace(/^\s+|\s+$/g, "");
            if (text) result.push(text);
        }
        return result;
    }

    function fitArtboard(targetDoc, items) {
        var bounds = unionBounds(items);
        targetDoc.artboards[0].artboardRect = [
            Number(bounds[0]),
            Number(bounds[1]),
            Number(bounds[2]),
            Number(bounds[3])
        ];
    }

    function unionBounds(items) {
        if (!items || !items.length) throw new Error("V2 compose artwork is empty");
        var result = null;
        for (var index = 0; index < items.length; index++) {
            var bounds = items[index].visibleBounds || items[index].geometricBounds;
            if (!validBounds(bounds)) continue;
            if (!result) {
                result = [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
            } else {
                result[0] = Math.min(result[0], Number(bounds[0]));
                result[1] = Math.max(result[1], Number(bounds[1]));
                result[2] = Math.max(result[2], Number(bounds[2]));
                result[3] = Math.min(result[3], Number(bounds[3]));
            }
        }
        if (!result) throw new Error("V2 compose bounds are not measurable");
        return result;
    }

    function validBounds(bounds) {
        return bounds && bounds.length >= 4
            && isFinite(Number(bounds[0]))
            && isFinite(Number(bounds[1]))
            && isFinite(Number(bounds[2]))
            && isFinite(Number(bounds[3]));
    }

    function mmToPt(mm) {
        return mm * 72 / 25.4;
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

    function stringifyJson(value) {
        if (typeof JSON !== "undefined" && JSON.stringify) return JSON.stringify(value);
        if (value === null || value === undefined) return "null";
        if (typeof value === "number") return isFinite(value) ? String(value) : "null";
        if (typeof value === "boolean") return value ? "true" : "false";
        if (typeof value === "string") return '"' + String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r/g, "\\r").replace(/\n/g, "\\n") + '"';
        if (Object.prototype.toString.call(value) === "[object Array]") {
            var arrayParts = [];
            for (var arrayIndex = 0; arrayIndex < value.length; arrayIndex++) arrayParts.push(stringifyJson(value[arrayIndex]));
            return "[" + arrayParts.join(",") + "]";
        }
        var fields = [];
        for (var key in value) {
            if (Object.prototype.hasOwnProperty.call(value, key)) fields.push(stringifyJson(String(key)) + ":" + stringifyJson(value[key]));
        }
        return "{" + fields.join(",") + "}";
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

    function saveAI(targetDoc, file, compatibility) {
        var options = new IllustratorSaveOptions();
        options.compatibility = compatibility === "CS5" ? Compatibility.ILLUSTRATOR15 : Compatibility.ILLUSTRATOR8;
        options.pdfCompatible = false;
        options.compressed = false;
        targetDoc.saveAs(file, options);
    }

    function ensureFolder(folder) {
        if (!folder || folder.exists) return;
        ensureFolder(folder.parent);
        folder.create();
    }
}());
