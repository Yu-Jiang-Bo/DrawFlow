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

    try {
        for (var inputIndex = 0; inputIndex < inputs.length; inputIndex++) {
            var input = inputs[inputIndex] || {};
            var sourcePath = String(input.path || "");
            if (!sourcePath) throw new Error("V2 compose input path missing");
            var source = app.open(File(sourcePath));
            try {
                var copied = duplicateVisibleArtwork(source, layer);
                if (!copied.length) throw new Error("V2 compose input has no artwork");
                for (var copiedIndex = 0; copiedIndex < copied.length; copiedIndex++) sanitizePackNames(copied[copiedIndex]);
                if (input.target_dimensions && (!input.target_dimensions.width_mm || !input.target_dimensions.height_mm)) throw new Error("V2 order column target dimensions missing");
                fitCopiedArtwork(copied, input.target_dimensions || {});
                var item = groupPageItems(layer, copied, "ORDER_PACK_ITEM_PENDING_" + inputIndex);
                orderBucketFor(input, inputIndex).items.push(item);
            } finally {
                try { source.close(SaveOptions.DONOTSAVECHANGES); } catch (closeSourceError) {}
            }
        }
        var orderBlocks = layoutOrderBlocks(layer, orderBuckets, gap);
        var allItems = orderBlocks.slice(0);
        if (labelLines.length) {
            var labelItems = addProductionLabels(layer, labelLines, orderBlocks, labelHeight, labelGap, labelFontSize);
            allItems = labelItems.concat(orderBlocks);
        }
        fitArtboard(doc, allItems);
        applyOutputTransforms(doc, task.output || {});
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

    function fitCopiedArtwork(items, dimensions) {
        var targetWidth = mmToPt(Number(dimensions.width_mm || 0));
        var targetHeight = mmToPt(Number(dimensions.height_mm || 0));
        if (targetWidth <= 0 || targetHeight <= 0) return;
        for (var index = 0; index < items.length; index++) fitPageItem(items[index], targetWidth, targetHeight);
    }

    function fitPageItem(item, targetWidth, targetHeight) {
        var bounds = itemBounds(item);
        var width = Number(bounds[2]) - Number(bounds[0]);
        var height = Number(bounds[1]) - Number(bounds[3]);
        if (width <= 0 || height <= 0) throw new Error("V2 compose artwork bounds are empty");
        item.resize(targetWidth / width * 100, targetHeight / height * 100, true, true, true, true, 100, Transformation.CENTER);
        var fitted = itemBounds(item);
        item.translate((Number(bounds[0]) + Number(bounds[2]) - Number(fitted[0]) - Number(fitted[2])) / 2, (Number(bounds[1]) + Number(bounds[3]) - Number(fitted[1]) - Number(fitted[3])) / 2);
        validatePageItem(item, targetWidth, targetHeight);
    }

    function validatePageItem(item, targetWidth, targetHeight) {
        var bounds = itemBounds(item);
        var epsilon = mmToPt(0.007);
        if (Math.abs((Number(bounds[2]) - Number(bounds[0])) - targetWidth) > epsilon || Math.abs((Number(bounds[1]) - Number(bounds[3])) - targetHeight) > epsilon) {
            throw new Error("V2 compose artwork does not match target dimensions");
        }
    }

    function applyOutputTransforms(doc, policy) {
        if (!policy || policy.outline_text !== true) return;
        var outlines = outlineCurrentTextFrames(doc, "V2 order column");
        if (policy.pathfinder_merge === true) mergeOverlappingTextOutlines(outlines, "V2 order column");
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
        if (!items.length) return;
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
        var characters = frame.textRange.characters;
        if (!characters || !characters.length) return null;
        var key = null;
        for (var index = 0; index < characters.length; index++) {
            var candidate = characterStyleKey(characters[index].characterAttributes);
            if (candidate === null) return null;
            if (key === null) key = candidate;
            else if (key !== candidate) return null;
        }
        return key + "|opacity=" + safeProperty(frame, "opacity") + "|blend=" + safeProperty(frame, "blendingMode");
    }

    function characterStyleKey(attributes) {
        var font = safeProperty(attributes, "textFont");
        var fill = colorStyleKey(safeProperty(attributes, "fillColor"));
        var stroke = colorStyleKey(safeProperty(attributes, "strokeColor"));
        if (fill === null || stroke === null) return null;
        return [
            fill, stroke,
            safeProperty(attributes, "filled"), safeProperty(attributes, "stroked"),
            safeProperty(attributes, "strokeWeight"), safeProperty(attributes, "size"),
            safeProperty(attributes, "horizontalScale"), safeProperty(attributes, "verticalScale"),
            safeProperty(attributes, "baselineShift"), safeProperty(attributes, "tracking"),
            safeProperty(attributes, "overprintFill"), safeProperty(attributes, "overprintStroke"),
            font ? safeProperty(font, "name") : ""
        ].join("|");
    }

    function safeProperty(object, name) {
        try { return object ? object[name] : ""; } catch (ignored) { return ""; }
    }

    function colorStyleKey(color) {
        if (!color) return "none";
        var type = safeProperty(color, "typename");
        if (type === "CMYKColor") return "CMYK:" + safeProperty(color, "cyan") + "," + safeProperty(color, "magenta") + "," + safeProperty(color, "yellow") + "," + safeProperty(color, "black");
        if (type === "RGBColor") return "RGB:" + safeProperty(color, "red") + "," + safeProperty(color, "green") + "," + safeProperty(color, "blue");
        if (type === "GrayColor") return "Gray:" + safeProperty(color, "gray");
        if (type === "LabColor") return "Lab:" + safeProperty(color, "l") + "," + safeProperty(color, "a") + "," + safeProperty(color, "b");
        if (type === "NoColor") return "NoColor";
        if (type === "SpotColor") {
            var spot = safeProperty(color, "spot");
            return "Spot:" + safeProperty(spot, "name") + "," + safeProperty(color, "tint");
        }
        // Gradient and pattern transforms are object-level state.  Without a
        // complete, stable signature they must never enter a cross-frame merge.
        return null;
    }

    function orderBucketFor(input, inputIndex) {
        var orderNo = String(input.order_no || "").replace(/^\s+|\s+$/g, "");
        var key = orderNo || "__input_" + inputIndex;
        if (!orderBucketByKey[key]) {
            orderBucketByKey[key] = { key: key, orderNo: orderNo, items: [] };
            orderBuckets.push(orderBucketByKey[key]);
        }
        return orderBucketByKey[key];
    }

    function layoutOrderBlocks(layer, buckets, gap) {
        var currentTop = 0;
        var blocks = [];
        for (var orderIndex = 0; orderIndex < buckets.length; orderIndex++) {
            var bucket = buckets[orderIndex];
            for (var itemIndex = 0; itemIndex < bucket.items.length; itemIndex++) {
                bucket.items[itemIndex].name = "ORDER_PACK_ITEM_" + orderIndex + "_" + itemIndex;
            }
            var block = groupPageItems(layer, bucket.items, "ORDER_PACK_BLOCK_" + orderIndex);
            for (var childIndex = 0; childIndex < bucket.items.length; childIndex++) {
                var item = bucket.items[childIndex];
                var bounds = unionBounds([item]);
                translateItems([item], 0 - Number(bounds[0]), currentTop - Number(bounds[1]));
                var placed = unionBounds([item]);
                currentTop = Number(placed[3]) - gap;
            }
            blocks.push(block);
        }
        if (!blocks.length) throw new Error("V2 compose produced no order blocks");
        return blocks;
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
        translateItems(orderBlocks, 0 - Number(bounds[0]), -(totalLabelHeight + labelGap) - Number(bounds[1]));
        var labels = [];
        for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
            var top = -(lineIndex * (labelHeight + labelGap));
            var label = drawLabel(layer, lines[lineIndex], 0, top, width, top - labelHeight, fontSize);
            if (label) labels.push(label);
        }
        return labels;
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
