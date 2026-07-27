#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(File(taskPath));
    if (task.type !== "compose_color_frames") throw new Error("Unsupported task type");
    if (!task.inputs || task.inputs.length === 0) throw new Error("No color frame inputs");

    var packing = task.master_packing || {};
    var algorithm = String(packing.algorithm || "best_fit_decreasing_height");
    if (algorithm !== "best_fit_decreasing_height") throw new Error("Unsupported master packing algorithm: " + algorithm);
    if (packing.allow_rotation === true) throw new Error("Compact master packing does not allow automatic rotation");

    var frameWidth = mmToPt(Number(packing.target_width_mm || 0));
    var itemGap = mmToPt(Number(packing.item_gap_mm || 0));
    var outerMargin = mmToPt(Number(packing.outer_margin_mm || 0));
    var configuredHeaderHeight = mmToPt(Number(packing.header_height_mm || 0));
    var colorGap = mmToPt(Number(packing.color_gap_mm || 0));
    var showColorHeader = task.show_color_header === true;
    var headerHeight = showColorHeader ? configuredHeaderHeight : 0;
    if (frameWidth <= 0) throw new Error("Missing compact master target width");
    if (outerMargin * 2 >= frameWidth) throw new Error("Compact master margins leave no usable width");

    var usableWidth = frameWidth - outerMargin * 2;
    var plans = [];
    var finalHeight = 0;
    for (var inputIndex = 0; inputIndex < task.inputs.length; inputIndex++) {
        var input = task.inputs[inputIndex];
        var blocks = readBlockMetrics(input);
        var packed = packBlocks(blocks, usableWidth, itemGap, String(input.color_option || ""));
        var frameHeight = outerMargin + headerHeight + packed.height + outerMargin;
        var plan = {
            input: input,
            colorOption: String(input.color_option || ""),
            blocks: packed.blocks,
            frameHeight: frameHeight,
            contentHeight: packed.height,
            frameLeft: inputIndex * (frameWidth + colorGap)
        };
        plans.push(plan);
        if (frameHeight > finalHeight) finalHeight = frameHeight;
    }
    if (finalHeight <= 0) throw new Error("Compact master has no visible content");

    var docWidth = frameWidth * plans.length + colorGap * Math.max(plans.length - 1, 0);
    var doc = app.documents.add(DocumentColorSpace.CMYK, docWidth, finalHeight);
    var layer = doc.layers[0];
    layer.name = "COLOR_FRAME_OUTPUT";

    for (var planIndex = 0; planIndex < plans.length; planIndex++) {
        composePlan(doc, layer, plans[planIndex], finalHeight, frameWidth, outerMargin, headerHeight, usableWidth);
    }

    writeDebug(task, plans, docWidth, finalHeight, frameWidth, usableWidth, algorithm);
    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    var options = new IllustratorSaveOptions();
    options.compatibility = Compatibility.ILLUSTRATOR8;
    options.pdfCompatible = false;
    options.compressed = false;
    doc.saveAs(output, options);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function composePlan(doc, layer, plan, docHeight, width, margin, labelHeight, availableWidth) {
        var boundary = layer.pathItems.rectangle(docHeight, plan.frameLeft, width, plan.frameHeight);
        boundary.name = "COLOR_FRAME_" + safeName(plan.colorOption || "MASTER") + "_" + roundMm(width) + "mm_DYNAMIC";
        boundary.filled = false;
        boundary.stroked = false;
        if (showColorHeader) drawLabel(layer, plan.colorOption || "Unspecified", plan.frameLeft + margin, docHeight - margin, labelHeight);

        var source = app.open(File(String(plan.input.path)));
        try {
            var sourceBlocks = collectOrderBlocks(source);
            if (sourceBlocks.length !== plan.blocks.length) {
                throw new Error("Color component order block count changed while composing: " + plan.colorOption);
            }
            for (var blockIndex = 0; blockIndex < plan.blocks.length; blockIndex++) {
                var block = plan.blocks[blockIndex];
                var sourceBlock = sourceBlocks[block.sourceIndex];
                if (!sourceBlock) throw new Error("Missing order pack block " + block.sourceIndex + " for " + plan.colorOption);
                var copy = sourceBlock.item.duplicate(layer, ElementPlacement.PLACEATEND);
                var copiedBounds = pageItemBounds(copy);
                var destinationLeft = plan.frameLeft + margin + block.x;
                var destinationTop = docHeight - margin - labelHeight - block.y;
                if (destinationLeft < plan.frameLeft - 0.01 || destinationLeft + block.width > plan.frameLeft + width + 0.01) {
                    throw new Error("Packed order block exceeds target width: " + plan.colorOption);
                }
                copy.translate(destinationLeft - copiedBounds[0], destinationTop - copiedBounds[1]);
            }
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function readBlockMetrics(input) {
        var source = app.open(File(String(input.path)));
        try {
            var sourceBlocks = collectOrderBlocks(source);
            if (!sourceBlocks.length) throw new Error("Color component has no ORDER_PACK_BLOCK groups: " + String(input.color_option || ""));
            var metrics = [];
            for (var i = 0; i < sourceBlocks.length; i++) {
                var bounds = pageItemBounds(sourceBlocks[i].item);
                var width = bounds[2] - bounds[0];
                var height = bounds[1] - bounds[3];
                if (width <= 0 || height <= 0) throw new Error("Order pack block has empty visible bounds: " + sourceBlocks[i].item.name);
                metrics.push({
                    sourceIndex: i,
                    name: String(sourceBlocks[i].item.name || ""),
                    width: width,
                    height: height,
                    x: 0,
                    y: 0
                });
            }
            return metrics;
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function collectOrderBlocks(source) {
        var result = [];
        for (var layerIndex = 0; layerIndex < source.layers.length; layerIndex++) {
            var sourceLayer = source.layers[layerIndex];
            for (var itemIndex = 0; itemIndex < sourceLayer.pageItems.length; itemIndex++) {
                var sourceItem = sourceLayer.pageItems[itemIndex];
                if (sourceItem.parent !== sourceLayer) continue;
                if (sourceItem.typename !== "GroupItem") continue;
                // Illustrator 8 does not reliably preserve a newly created
                // GroupItem name. The component contract is therefore one
                // direct layer group per production order.
                result.push({ item: sourceItem, sourceLayerIndex: layerIndex });
            }
        }
        return result;
    }

    function packBlocks(blocks, width, gap, colorOption) {
        var ordered = blocks.slice(0);
        ordered.sort(function (left, right) {
            if (Math.abs(right.height - left.height) > 0.01) return right.height - left.height;
            if (Math.abs(right.width - left.width) > 0.01) return right.width - left.width;
            return left.sourceIndex - right.sourceIndex;
        });
        var shelves = [];
        var usedHeight = 0;
        for (var blockIndex = 0; blockIndex < ordered.length; blockIndex++) {
            var block = ordered[blockIndex];
            if (block.width > width + 0.01) {
                throw new Error("Order pack block is wider than " + roundMm(width) + "mm: " + colorOption + " / " + block.name);
            }
            var bestShelf = -1;
            var bestScore = null;
            for (var shelfIndex = 0; shelfIndex < shelves.length; shelfIndex++) {
                var shelf = shelves[shelfIndex];
                var candidateX = shelf.usedWidth > 0 ? shelf.usedWidth + gap : 0;
                if (candidateX + block.width > width + 0.01 || block.height > shelf.height + 0.01) continue;
                var residualWidth = width - candidateX - block.width;
                var residualHeight = shelf.height - block.height;
                var score = residualWidth + residualHeight * 0.2;
                if (bestScore === null || score < bestScore - 0.01 || (Math.abs(score - bestScore) <= 0.01 && shelfIndex < bestShelf)) {
                    bestShelf = shelfIndex;
                    bestScore = score;
                }
            }
            if (bestShelf >= 0) {
                var targetShelf = shelves[bestShelf];
                block.x = targetShelf.usedWidth > 0 ? targetShelf.usedWidth + gap : 0;
                block.y = targetShelf.y;
                targetShelf.usedWidth = block.x + block.width;
                continue;
            }
            var y = shelves.length ? usedHeight + gap : 0;
            block.x = 0;
            block.y = y;
            shelves.push({ y: y, height: block.height, usedWidth: block.width });
            usedHeight = y + block.height;
        }
        return { blocks: ordered, height: usedHeight };
    }

    function pageItemBounds(item) {
        var bounds = null;
        try { bounds = item.visibleBounds; } catch (e0) {}
        if (!bounds || bounds.length !== 4) {
            try { bounds = item.geometricBounds; } catch (e1) {}
        }
        if (!bounds || bounds.length !== 4) throw new Error("Cannot read order pack block bounds");
        return [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
    }

    function drawLabel(layer, text, left, top, height) {
        if (height <= 0) return null;
        var frame = layer.textFrames.add();
        frame.contents = text;
        frame.textRange.characterAttributes.size = 12;
        frame.position = [left, top - Math.min(mmToPt(2), Math.max(height - mmToPt(4), 0))];
        return frame;
    }

    function writeDebug(task, plans, docWidth, docHeight, frameWidth, usableWidth, algorithm) {
        try {
            if (!task.debug || !task.debug.report_path) return;
            var frames = [];
            for (var i = 0; i < plans.length; i++) {
                var plan = plans[i];
                frames.push({
                    color_option: plan.colorOption,
                    frame_width_mm: roundMm(frameWidth),
                    frame_height_mm: roundMm(plan.frameHeight),
                    content_height_mm: roundMm(plan.contentHeight),
                    frame_left_mm: roundMm(plan.frameLeft),
                    order_block_count: plan.blocks.length,
                    horizontal_overflow: false,
                    blocks: auditBlocks(plan.blocks)
                });
            }
            var file = File(String(task.debug.report_path));
            ensureFolder(file.parent);
            file.encoding = "UTF-8";
            if (!file.open("w")) return;
            file.write(toJson({
                algorithm: algorithm,
                target_width_mm: roundMm(frameWidth),
                usable_width_mm: roundMm(usableWidth),
                artboard_width_mm: roundMm(docWidth),
                artboard_height_mm: roundMm(docHeight),
                coordinate_unit: "mm",
                frames: frames
            }));
            file.close();
        } catch (e) {}
    }

    function auditBlocks(blocks) {
        var result = [];
        for (var i = 0; i < blocks.length; i++) {
            var block = blocks[i];
            result.push({
                source_index: block.sourceIndex,
                width_mm: roundMm(block.width),
                height_mm: roundMm(block.height),
                x_mm: roundMm(block.x),
                y_mm: roundMm(block.y)
            });
        }
        return result;
    }

    function safeName(value) { return String(value).replace(/[^A-Za-z0-9_]+/g, "_"); }
    function roundMm(points) { return Math.round((points * 25.4 / 72) * 1000) / 1000; }
    function mmToPt(mm) { return Number(mm || 0) * 72 / 25.4; }
    function readJSON(file) {
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open task JSON");
        var value = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(value);
        return eval("(" + value + ")");
    }
    function ensureFolder(folder) {
        if (!folder.exists) { ensureFolder(folder.parent); folder.create(); }
    }
    function toJson(value) {
        if (value === null) return "null";
        var kind = typeof value;
        if (kind === "number" || kind === "boolean") return String(value);
        if (kind === "string") return "\"" + value.replace(/\\\\/g, "\\\\\\\\").replace(/\"/g, "\\\\\"").replace(/\n/g, "\\n") + "\"";
        if (value instanceof Array) {
            var arrayValues = [];
            for (var i = 0; i < value.length; i++) arrayValues.push(toJson(value[i]));
            return "[" + arrayValues.join(",") + "]";
        }
        var values = [];
        for (var key in value) if (value.hasOwnProperty(key)) values.push(toJson(String(key)) + ":" + toJson(value[key]));
        return "{" + values.join(",") + "}";
    }
}());
