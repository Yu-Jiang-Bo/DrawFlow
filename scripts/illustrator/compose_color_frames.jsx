#target illustrator

(function () {
    if (typeof __COLOR_FRAME_PACK_TEST__ !== "undefined") {
        if (String(__COLOR_FRAME_PACK_TEST__.mode || "") === "adaptive_grid") {
            __COLOR_FRAME_PACK_TEST__.result = packAdaptiveGrid(
                __COLOR_FRAME_PACK_TEST__.orders,
                __COLOR_FRAME_PACK_TEST__.width,
                __COLOR_FRAME_PACK_TEST__.verticalGap,
                __COLOR_FRAME_PACK_TEST__.columnGap,
                __COLOR_FRAME_PACK_TEST__.labelHeight,
                __COLOR_FRAME_PACK_TEST__.labelGap,
                __COLOR_FRAME_PACK_TEST__.cellPadding,
                __COLOR_FRAME_PACK_TEST__.slackRows,
                __COLOR_FRAME_PACK_TEST__.colorOption,
                __COLOR_FRAME_PACK_TEST__.keepOrderItemsTogether === true
            );
        } else {
            __COLOR_FRAME_PACK_TEST__.result = packColorFrameBlocks(
                __COLOR_FRAME_PACK_TEST__.plans,
                __COLOR_FRAME_PACK_TEST__.width,
                __COLOR_FRAME_PACK_TEST__.gap
            );
        }
        return;
    }

    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(File(taskPath));
    if (task.type !== "compose_color_frames") throw new Error("Unsupported task type");
    if (!task.inputs || task.inputs.length === 0) throw new Error("No color frame inputs");

    var packing = task.master_packing || {};
    var algorithm = String(packing.algorithm || "adaptive_column_grid");
    if (algorithm === "best_fit_decreasing_height") algorithm = "adaptive_column_grid";
    if (algorithm !== "adaptive_column_grid") throw new Error("Unsupported master packing algorithm: " + algorithm);
    if (packing.allow_rotation === true) throw new Error("Adaptive grid master packing does not allow automatic rotation");

    var frameWidth = mmToPt(Number(packing.target_width_mm || 0));
    var itemGap = mmToPt(Number(packing.item_gap_mm || 0));
    var columnGap = mmToPt(Number(packing.column_gap_mm || packing.item_gap_mm || 0));
    var outerMargin = mmToPt(Number(packing.outer_margin_mm || 0));
    var configuredHeaderHeight = mmToPt(Number(packing.header_height_mm || 0));
    var colorGap = mmToPt(Number(packing.color_gap_mm || 0));
    var labelHeight = mmToPt(Number(packing.label_height_mm || 4));
    var labelGap = mmToPt(Number(packing.label_gap_mm || 0.8));
    var cellWidthPadding = mmToPt(Number(packing.cell_width_padding_mm || 0.8));
    var rowSlack = Math.max(Math.floor(Number(packing.row_slack || 1)), 0);
    var labelFontSize = Number(packing.label_font_size_pt || 6);
    var colorHeaderFontSize = Number(packing.color_header_font_size_pt || 7);
    var keepOrderItemsTogether = packing.keep_order_items_together === true;
    var showColorHeader = task.show_color_header === true;
    var headerHeight = showColorHeader ? configuredHeaderHeight : 0;
    var colorFrameBoundary = showColorHeader || task.show_color_frame_boundary === true || packing.show_color_frame_boundary === true;
    if (frameWidth <= 0) throw new Error("Missing adaptive grid target width");
    if (outerMargin * 2 >= frameWidth) throw new Error("Adaptive grid margins leave no usable width");

    var usableWidth = frameWidth - outerMargin * 2;
    var plans = [];
    for (var inputIndex = 0; inputIndex < task.inputs.length; inputIndex++) {
        var input = task.inputs[inputIndex];
        var orders = readOrderMetrics(input);
        var packed = packAdaptiveGrid(
            orders,
            usableWidth,
            itemGap,
            columnGap,
            labelHeight,
            labelGap,
            cellWidthPadding,
            rowSlack,
            String(input.color_option || ""),
            keepOrderItemsTogether
        );
        var frameHeight = outerMargin + headerHeight + packed.height + outerMargin;
        var plan = {
            input: input,
            colorOption: String(input.color_option || ""),
            placements: packed.placements,
            columns: packed.columns,
            orderBlockCount: orders.length,
            subItemCount: packed.subItemCount,
            frameHeight: frameHeight,
            contentHeight: packed.height,
            maxColumns: packed.maxColumns,
            idealRows: packed.idealRows,
            hardRows: packed.hardRows,
            cellWidth: packed.cellWidth,
            slotPitch: packed.slotPitch,
            frameLeft: 0,
            frameY: 0,
            frameColumn: 0
        };
        plans.push(plan);
    }
    var frameLayout = packColorFrameBlocks(plans, frameWidth, colorGap);
    var docWidth = frameLayout.width;
    var finalHeight = frameLayout.height;
    if (finalHeight <= 0) throw new Error("Adaptive grid master has no visible content");

    var doc = app.documents.add(DocumentColorSpace.CMYK, docWidth, finalHeight);
    var layer = doc.layers[0];
    layer.name = "COLOR_FRAME_OUTPUT";
    var composedComponentContracts = [];

    for (var planIndex = 0; planIndex < plans.length; planIndex++) {
        composePlan(layer, plans[planIndex], finalHeight, frameWidth, outerMargin, headerHeight, composedComponentContracts);
    }

    var outputPolicy = task.output || {};
    if (!task.output || outputPolicy.outline_text !== false) {
        outlineAllTextFrames(doc, outputPolicy.pathfinder_merge === true);
        assertNoTextFrames(doc, "V2 color frame output");
    }
    writeDebug(task, plans, docWidth, finalHeight, frameWidth, usableWidth, algorithm, frameLayout);
    var output = File(String(task.output_ai));
    ensureFolder(output.parent);
    if (output.exists) output.remove();
    var options = new IllustratorSaveOptions();
    var targetCompatibility = String(task.compatibility || "Illustrator 8").toLowerCase();
    if (targetCompatibility === "cs5") {
        options.compatibility = Compatibility.ILLUSTRATOR15;
    } else if (targetCompatibility !== "ai_standard" && targetCompatibility !== "standard" && targetCompatibility !== "current") {
        options.compatibility = Compatibility.ILLUSTRATOR8;
    }
    options.pdfCompatible = false;
    options.compressed = false;
    doc.saveAs(output, options);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    return output.fsName;

    function composePlan(layer, plan, docHeight, width, margin, labelBandHeight, contracts) {
        var frameTop = docHeight - plan.frameY;
        var boundary = layer.pathItems.rectangle(frameTop, plan.frameLeft, width, plan.frameHeight);
        boundary.name = "COLOR_FRAME_" + safeName(plan.colorOption || "MASTER") + "_" + roundMm(width) + "mm_GRID";
        boundary.filled = false;
        boundary.stroked = colorFrameBoundary;
        if (colorFrameBoundary) {
            boundary.strokeWidth = 0.35;
            boundary.strokeColor = redColor();
        }
        if (showColorHeader) {
            drawLabel(
                layer,
                plan.colorOption || "Unspecified",
                plan.frameLeft + margin,
                frameTop - margin,
                plan.frameLeft + width - margin,
                frameTop - margin - labelBandHeight,
                colorHeaderFontSize
            );
        }

        var source = app.open(File(String(plan.input.path)));
        try {
            var sourceOrders = collectOrderBlocks(source);
            var componentFrames = readComponentFrameMap(plan.input);
            assertSourceOrderCount(plan.input, sourceOrders);
            for (var placementIndex = 0; placementIndex < plan.placements.length; placementIndex++) {
                var placement = plan.placements[placementIndex];
                var sourceOrder = sourceOrders[placement.sourceIndex];
                if (!sourceOrder) throw new Error("Missing source order block " + placement.sourceIndex);
                var sourceSubItems = sourceOrder.subItems && sourceOrder.subItems.length
                    ? sourceOrder.subItems
                    : (sourceOrder.item ? collectOrderSubItems(sourceOrder.item) : []);
                if (!sourceSubItems.length && sourceOrder.item) sourceSubItems.push({ item: sourceOrder.item, sourceChildIndex: -1 });
                if (!sourceSubItems.length) throw new Error("Missing source order artwork for " + placement.orderNo);

                var labelLeft = plan.frameLeft + margin + placement.x;
                var labelTop = frameTop - margin - labelBandHeight - placement.y;
                drawLabel(layer, placement.orderNo, labelLeft, labelTop, labelLeft + placement.width, labelTop - labelHeight, labelFontSize);

                for (var itemIndex = 0; itemIndex < placement.items.length; itemIndex++) {
                    var item = placement.items[itemIndex];
                    var sourceItem = item.sourceChildIndex < 0 ? sourceOrder.item : sourceSubItems[item.sourceChildIndex];
                    if (!sourceItem) throw new Error("Missing source order sub-item " + item.sourceChildIndex);
                    var copy = sourceItem.item ? sourceItem.item.duplicate(layer, ElementPlacement.PLACEATEND) : sourceItem.duplicate(layer, ElementPlacement.PLACEATEND);
                    var componentFrame = componentFrameForItem(sourceItem.item || sourceItem, componentFrames, sourceOrder.sourceIndex, item.sourceChildIndex);
                    validateRequestedDimensions(componentFrame, item.target_dimensions || {});
                    verifyTranslatedArtwork(sourceItem.item || sourceItem, componentFrame.artwork_bounds_after, 0, 0, "color frame source");
                    var destinationLeft = plan.frameLeft + margin + placement.x + item.x;
                    var destinationTop = frameTop - margin - labelBandHeight - placement.y - item.y;
                    if (destinationLeft < plan.frameLeft + margin - 0.01 || destinationLeft + item.width > plan.frameLeft + width - margin + 0.01) {
                        throw new Error("Packed order sub-item exceeds target width: " + plan.colorOption + " / " + placement.orderNo);
                    }
                    var dx = destinationLeft - componentFrame.frame_bounds[0];
                    var dy = destinationTop - componentFrame.frame_bounds[1];
                    var copyCoordinateTranslation = placeArtworkAtExpected(copy, componentFrame.artwork_bounds_after, dx, dy, "color frame placement");
                    var actualArtworkBounds = verifyTranslatedArtwork(copy, componentFrame.artwork_bounds_after, dx, dy, "color frame placement");
                    contracts.push({
                        key: String(componentFrame.key || ""),
                        source_frame_bounds: copyBounds(componentFrame.frame_bounds),
                        frame_bounds: translateBounds(componentFrame.frame_bounds, dx, dy),
                        compose_translation: {x: dx, y: dy},
                        copy_coordinate_translation: copyCoordinateTranslation,
                        source_artwork_bounds: copyBounds(componentFrame.artwork_bounds_after),
                        artwork_bounds_after: actualArtworkBounds,
                        tracked_slots: translateTrackedSlots(componentFrame.tracked_slots || [], dx, dy),
                        source: "compose_color_frames"
                    });
                }
            }
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function packColorFrameBlocks(plans, width, gap) {
        if (!plans.length) throw new Error("No color frames to pack");
        var targetHeight = 0;
        for (var planIndex = 0; planIndex < plans.length; planIndex++) {
            targetHeight = Math.max(targetHeight, plans[planIndex].frameHeight);
        }
        if (targetHeight <= 0) throw new Error("Color frame packing target height is empty");

        var columns = [];
        var current = newColorFrameColumn(0);
        columns.push(current);
        for (var index = 0; index < plans.length; index++) {
            var plan = plans[index];
            current = findBestColorFrameColumn(columns, plan.frameHeight, targetHeight, gap);
            if (!current) {
                current = newColorFrameColumn(columns.length);
                columns.push(current);
            }
            var needsGap = current.plans.length ? gap : 0;
            plan.frameColumn = current.index;
            plan.frameY = current.height + needsGap;
            plan.frameLeft = current.index * (width + gap);
            current.plans.push(plan);
            current.height = plan.frameY + plan.frameHeight;
        }

        var docHeight = 0;
        for (var columnIndex = 0; columnIndex < columns.length; columnIndex++) {
            docHeight = Math.max(docHeight, columns[columnIndex].height);
        }
        return {
            width: columns.length * width + Math.max(columns.length - 1, 0) * gap,
            height: docHeight,
            targetHeight: targetHeight,
            columns: columns
        };
    }

    function newColorFrameColumn(index) {
        return { index: index, height: 0, plans: [] };
    }

    function findBestColorFrameColumn(columns, frameHeight, targetHeight, gap) {
        var best = null;
        var bestRemaining = null;
        for (var index = 0; index < columns.length; index++) {
            var column = columns[index];
            var nextHeight = column.height + (column.plans.length ? gap : 0) + frameHeight;
            if (nextHeight > targetHeight + 0.01) continue;
            var remaining = targetHeight - nextHeight;
            if (best === null || remaining < bestRemaining - 0.01 || (Math.abs(remaining - bestRemaining) <= 0.01 && column.index < best.index)) {
                best = column;
                bestRemaining = remaining;
            }
        }
        return best;
    }

    function readOrderMetrics(input) {
        var source = app.open(File(String(input.path)));
        try {
            var sourceOrders = collectOrderBlocks(source);
            var componentFrames = readComponentFrameMap(input);
            assertSourceOrderCount(input, sourceOrders);
            var orderNos = input.order_nos || [];
            var targetDimensions = input.order_dimensions || [];
            var dimensionCursor = 0;
            var orders = [];
            for (var orderIndex = 0; orderIndex < sourceOrders.length; orderIndex++) {
                var sourceOrder = sourceOrders[orderIndex];
                var sourceSubItems = sourceOrder.subItems && sourceOrder.subItems.length
                    ? sourceOrder.subItems
                    : (sourceOrder.item ? collectOrderSubItems(sourceOrder.item) : []);
                if (!sourceSubItems.length && sourceOrder.item) sourceSubItems.push({ item: sourceOrder.item, sourceChildIndex: -1 });
                if (!sourceSubItems.length) throw new Error("Missing source order artwork for " + sourceOrder.sourceIndex);
                var orderItems = [];
                for (var childIndex = 0; childIndex < sourceSubItems.length; childIndex++) {
                    var sourceItem = sourceSubItems[childIndex].item;
                    var componentFrame = componentFrameForItem(sourceItem, componentFrames, sourceOrder.sourceIndex, childIndex);
                    var requestedDimensions = targetDimensions[dimensionCursor + childIndex] || input.target_dimensions;
                    var target = requestedDimensions || {};
                    if (hasDimensionFields(requestedDimensions) && (!target.width_mm || !target.height_mm)) throw new Error("V2 color frame target dimensions missing");
                    validateRequestedDimensions(componentFrame, target);
                    var itemWidth = Number(componentFrame.frame_bounds[2]) - Number(componentFrame.frame_bounds[0]);
                    var itemHeight = Number(componentFrame.frame_bounds[1]) - Number(componentFrame.frame_bounds[3]);
                    if (itemWidth <= 0 || itemHeight <= 0) throw new Error("Order sub-item has empty component frame");
                    orderItems.push({
                        sourceChildIndex: sourceSubItems[childIndex].sourceChildIndex,
                        width: itemWidth,
                        height: itemHeight,
                        target_dimensions: target,
                        sourceOrder: orderIndex
                    });
                }
                orders.push({
                    sourceIndex: orderIndex,
                    orderNo: String(orderNos[orderIndex] || "ORDER_" + (orderIndex + 1)),
                    items: orderItems
                });
                dimensionCursor += sourceSubItems.length;
            }
            return orders;
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function hasDimensionFields(dimensions) {
        if (!dimensions) return false;
        for (var key in dimensions) {
            if (Object.prototype.hasOwnProperty.call(dimensions, key)) return true;
        }
        return false;
    }

    function packAdaptiveGrid(orders, width, verticalGap, minColumnGap, segmentLabelHeight, segmentLabelGap, cellPadding, slackRows, colorOption, keepOrderItemsTogether) {
        var subItemCount = 0;
        var cellWidth = 0;
        for (var orderIndex = 0; orderIndex < orders.length; orderIndex++) {
            var order = orders[orderIndex];
            subItemCount += order.items.length;
            cellWidth = Math.max(cellWidth, estimateLabelWidth(order.orderNo, labelFontSize));
            for (var itemIndex = 0; itemIndex < order.items.length; itemIndex++) {
                cellWidth = Math.max(cellWidth, order.items[itemIndex].width);
            }
        }
        if (subItemCount <= 0) throw new Error("Color component has no order artwork: " + colorOption);
        cellWidth = Math.min(width, cellWidth + cellPadding);
        if (cellWidth <= 0) throw new Error("Cannot derive adaptive grid cell width: " + colorOption);

        var maxColumns = Math.floor((width + minColumnGap) / (cellWidth + minColumnGap));
        maxColumns = Math.max(maxColumns, 1);
        while (maxColumns > 1 && maxColumns * cellWidth + (maxColumns - 1) * minColumnGap > width + 0.01) {
            maxColumns -= 1;
        }
        if (maxColumns < 1) throw new Error("Adaptive grid cannot fit one column in target width: " + colorOption);

        var idealRows = Math.max(1, Math.ceil(subItemCount / maxColumns));
        var hardRows = Math.max(idealRows, idealRows + slackRows);
        var columns = [];
        for (var columnIndex = 0; columnIndex < maxColumns; columnIndex++) {
            columns.push({ index: columnIndex, segments: [], itemCount: 0, height: 0 });
        }

        var sortedOrders = orders.slice(0);
        if (keepOrderItemsTogether !== true) {
            sortedOrders.sort(function (left, right) {
                if (right.items.length !== left.items.length) return right.items.length - left.items.length;
                return left.sourceIndex - right.sourceIndex;
            });
        }
        for (var sortedIndex = 0; sortedIndex < sortedOrders.length; sortedIndex++) {
            if (keepOrderItemsTogether === true) {
                placeWholeOrderIntoColumn(sortedOrders[sortedIndex], columns, idealRows, hardRows);
            } else {
                placeOrderIntoColumns(sortedOrders[sortedIndex], columns, idealRows, hardRows);
            }
        }

        var slotPitch = maxColumns > 1 ? (width - cellWidth) / (maxColumns - 1) : 0;
        var placements = [];
        var contentHeight = 0;
        for (var colIndex = 0; colIndex < columns.length; colIndex++) {
            var column = columns[colIndex];
            var columnY = 0;
            for (var segmentIndex = 0; segmentIndex < column.segments.length; segmentIndex++) {
                var segment = column.segments[segmentIndex];
                finalizeSegment(segment, colIndex * slotPitch, columnY, cellWidth, verticalGap, segmentLabelHeight, segmentLabelGap);
                placements.push(segment);
                columnY += segment.height + verticalGap;
            }
            column.height = columnY > 0 ? columnY - verticalGap : 0;
            contentHeight = Math.max(contentHeight, column.height);
        }
        updateFragmentMetadata(placements);
        return {
            placements: placements,
            columns: columns,
            height: contentHeight,
            subItemCount: subItemCount,
            maxColumns: maxColumns,
            idealRows: idealRows,
            hardRows: hardRows,
            cellWidth: cellWidth,
            slotPitch: slotPitch
        };
    }

    function placeWholeOrderIntoColumn(order, columns, idealRows, hardRows) {
        var startColumn = findBestColumnWindow(columns, 1, idealRows, hardRows);
        addSegment(columns[startColumn], order, 0, order.items.length);
    }

    function placeOrderIntoColumns(order, columns, idealRows, hardRows) {
        var nextItem = 0;
        var guard = 0;
        while (nextItem < order.items.length) {
            guard += 1;
            if (guard > order.items.length + columns.length + 20) throw new Error("Adaptive grid failed to place order: " + order.orderNo);
            var remaining = order.items.length - nextItem;
            var desiredColumns = Math.min(columns.length, Math.max(1, Math.ceil(remaining / idealRows)));
            var startColumn = findBestColumnWindow(columns, desiredColumns, idealRows, hardRows);
            var placed = 0;
            for (var offset = 0; offset < desiredColumns && nextItem < order.items.length; offset++) {
                var column = columns[startColumn + offset];
                var idealCapacity = Math.max(0, idealRows - column.itemCount);
                var hardCapacity = Math.max(0, hardRows - column.itemCount);
                var capacity = idealCapacity > 0 ? idealCapacity : hardCapacity;
                if (capacity <= 0) capacity = 1;
                var chunkSize = Math.min(order.items.length - nextItem, capacity);
                addSegment(column, order, nextItem, chunkSize);
                nextItem += chunkSize;
                placed += chunkSize;
            }
            if (placed <= 0) {
                var fallback = lowestColumn(columns);
                addSegment(fallback, order, nextItem, 1);
                nextItem += 1;
            }
        }
    }

    function findBestColumnWindow(columns, length, idealRows, hardRows) {
        var bestStart = 0;
        var bestScore = null;
        for (var start = 0; start <= columns.length - length; start++) {
            var maxCount = 0;
            var totalCount = 0;
            var overIdeal = 0;
            var overHard = 0;
            for (var offset = 0; offset < length; offset++) {
                var count = columns[start + offset].itemCount;
                maxCount = Math.max(maxCount, count);
                totalCount += count;
                overIdeal += Math.max(0, count - idealRows);
                overHard += Math.max(0, count - hardRows);
            }
            var score = overHard * 100000 + overIdeal * 1000 + maxCount * 20 + totalCount + start * 0.01;
            if (bestScore === null || score < bestScore - 0.01) {
                bestScore = score;
                bestStart = start;
            }
        }
        return bestStart;
    }

    function lowestColumn(columns) {
        var best = columns[0];
        for (var index = 1; index < columns.length; index++) {
            if (columns[index].itemCount < best.itemCount) best = columns[index];
        }
        return best;
    }

    function addSegment(column, order, start, count) {
        var previous = column.segments.length ? column.segments[column.segments.length - 1] : null;
        var segment = previous && previous.orderNo === order.orderNo ? previous : null;
        if (!segment) {
            segment = {
                sourceIndex: order.sourceIndex,
                orderNo: order.orderNo,
                parentBlockId: "order-" + order.sourceIndex,
                fragmentId: "order-" + order.sourceIndex + "-column-" + column.index + "-segment-" + column.segments.length,
                fragmentIndex: 0,
                fragmentCount: 1,
                split: false,
                columnIndex: column.index,
                itemCount: 0,
                width: 0,
                height: 0,
                x: 0,
                y: 0,
                items: []
            };
            column.segments.push(segment);
        }
        for (var index = 0; index < count; index++) {
            var item = order.items[start + index];
            segment.items.push({
                sourceChildIndex: item.sourceChildIndex,
                width: item.width,
                height: item.height,
                target_dimensions: item.target_dimensions || {},
                x: 0,
                y: 0,
                label_required: false
            });
        }
        segment.itemCount += count;
        column.itemCount += count;
    }

    function updateFragmentMetadata(placements) {
        var counts = {};
        var nextIndexes = {};
        for (var countIndex = 0; countIndex < placements.length; countIndex++) {
            var key = placements[countIndex].parentBlockId;
            counts[key] = (counts[key] || 0) + 1;
        }
        for (var placementIndex = 0; placementIndex < placements.length; placementIndex++) {
            var placement = placements[placementIndex];
            var placementKey = placement.parentBlockId;
            var nextIndex = nextIndexes[placementKey] || 0;
            var total = counts[placementKey] || 1;
            placement.fragmentIndex = nextIndex;
            placement.fragmentCount = total;
            placement.split = total > 1;
            placement.fragmentId = placementKey + "-fragment-" + nextIndex;
            nextIndexes[placementKey] = nextIndex + 1;
        }
    }

    function finalizeSegment(segment, x, y, width, verticalGap, segmentLabelHeight, segmentLabelGap) {
        segment.x = x;
        segment.y = y;
        segment.width = width;
        var cursor = segmentLabelHeight + segmentLabelGap;
        for (var itemIndex = 0; itemIndex < segment.items.length; itemIndex++) {
            var item = segment.items[itemIndex];
            item.x = Math.max((width - item.width) / 2, 0);
            item.y = cursor;
            cursor += item.height;
            if (itemIndex < segment.items.length - 1) cursor += verticalGap;
        }
        segment.height = cursor;
    }

    function assertSourceOrderCount(input, sourceOrders) {
        var expected = input.order_nos || [];
        if (expected.length && sourceOrders.length !== expected.length) {
            throw new Error("Color component order block count changed while composing");
        }
        if (!sourceOrders.length) throw new Error("Color component has no order groups");
    }

    function collectOrderBlocks(source) {
        var byIndex = {};
        var foundNamed = false;
        for (var layerIndex = 0; layerIndex < source.layers.length; layerIndex++) {
            var sourceLayer = source.layers[layerIndex];
            for (var itemIndex = 0; itemIndex < sourceLayer.pageItems.length; itemIndex++) {
                var sourceItem = sourceLayer.pageItems[itemIndex];
                if (sourceItem.parent !== sourceLayer) continue;
                collectNamedPackItemsByOrder(sourceItem, byIndex);
            }
        }
        var result = [];
        for (var key in byIndex) {
            if (!byIndex.hasOwnProperty(key)) continue;
            foundNamed = true;
            var entry = byIndex[key];
            entry.subItems = sortByStablePackIndex(entry.subItems || []);
            for (var subIndex = 0; subIndex < entry.subItems.length; subIndex++) {
                entry.subItems[subIndex].sourceChildIndex = subIndex;
            }
            result.push({
                item: entry.block || null,
                subItems: entry.subItems,
                sourceLayerIndex: 0,
                originalIndex: Number(key),
                sortIndex: Number(key),
                sourceIndex: Number(key)
            });
        }
        if (foundNamed) return sortByStablePackIndex(result);

        for (var fallbackLayerIndex = 0; fallbackLayerIndex < source.layers.length; fallbackLayerIndex++) {
            var fallbackLayer = source.layers[fallbackLayerIndex];
            for (var fallbackIndex = 0; fallbackIndex < fallbackLayer.pageItems.length; fallbackIndex++) {
                var fallbackItem = fallbackLayer.pageItems[fallbackIndex];
                if (fallbackItem.parent !== fallbackLayer) continue;
                if (fallbackItem.typename !== "GroupItem") continue;
                result.push({
                    item: fallbackItem,
                    subItems: [],
                    sourceLayerIndex: fallbackLayerIndex,
                    originalIndex: result.length,
                    sortIndex: parseOrderBlockIndex(fallbackItem.name),
                    sourceIndex: result.length
                });
            }
        }
        return sortByStablePackIndex(result);
    }

    function collectNamedPackItemsByOrder(item, byIndex) {
        if (!item || item.typename !== "GroupItem") return;
        var blockIndex = parseOrderBlockIndex(item.name);
        if (blockIndex >= 0) {
            ensureOrderEntry(byIndex, blockIndex).block = item;
        }
        var itemIndex = parseOrderItemName(item.name);
        if (itemIndex) {
            ensureOrderEntry(byIndex, itemIndex.orderIndex).subItems.push({
                item: item,
                sourceChildIndex: itemIndex.itemIndex,
                originalIndex: itemIndex.itemIndex,
                sortIndex: itemIndex.itemIndex
            });
        }
        for (var childIndex = 0; childIndex < item.groupItems.length; childIndex++) {
            collectNamedPackItemsByOrder(item.groupItems[childIndex], byIndex);
        }
    }

    function ensureOrderEntry(byIndex, index) {
        var key = String(index);
        if (!byIndex[key]) byIndex[key] = { block: null, subItems: [] };
        return byIndex[key];
    }

    function collectOrderSubItems(orderItem) {
        var result = [];
        for (var itemIndex = 0; itemIndex < orderItem.groupItems.length; itemIndex++) {
            var item = orderItem.groupItems[itemIndex];
            if (item.parent !== orderItem) continue;
            result.push({
                item: item,
                sourceChildIndex: result.length,
                originalIndex: result.length,
                sortIndex: parseOrderItemIndex(item.name)
            });
        }
        var namedItems = namedPackItems(result);
        if (namedItems.length) {
            result = namedItems;
        } else if (parseOrderBlockIndex(orderItem.name) >= 0) {
            if (result.length > 1) return sortByStablePackIndex(result);
            return [];
        }
        result = sortByStablePackIndex(result);
        for (var sortedIndex = 0; sortedIndex < result.length; sortedIndex++) {
            result[sortedIndex].sourceChildIndex = sortedIndex;
        }
        return result;
    }

    function parseOrderBlockIndex(name) {
        var match = /^ORDER_PACK_BLOCK_(\d+)$/.exec(String(name || ""));
        return match ? Number(match[1]) : -1;
    }

    function parseOrderItemIndex(name) {
        var parsed = parseOrderItemName(name);
        return parsed ? parsed.itemIndex : -1;
    }

    function parseOrderItemName(name) {
        var match = /^ORDER_PACK_ITEM_(\d+)_(\d+)$/.exec(String(name || ""));
        return match ? { orderIndex: Number(match[1]), itemIndex: Number(match[2]) } : null;
    }

    function sortByStablePackIndex(items) {
        items.sort(function (left, right) {
            var leftNamed = left.sortIndex >= 0;
            var rightNamed = right.sortIndex >= 0;
            if (leftNamed && rightNamed && left.sortIndex !== right.sortIndex) return left.sortIndex - right.sortIndex;
            if (leftNamed !== rightNamed) return leftNamed ? -1 : 1;
            return left.originalIndex - right.originalIndex;
        });
        return items;
    }

    function namedPackItems(items) {
        var named = [];
        for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
            if (items[itemIndex].sortIndex >= 0) named.push(items[itemIndex]);
        }
        return named;
    }

    function readComponentFrameMap(input) {
        var path = String(input.component_contract_file || "");
        if (!path) throw new Error("V2 color frame component contract path missing");
        var contract = readJSON(File(path));
        if (Number(contract.component_contract_version || 0) !== 1) throw new Error("Unsupported V2 color frame component contract");
        var frames = contract.component_frames || [];
        if (!frames.length) throw new Error("V2 color frame component contract has no frames");
        var byKey = {};
        for (var index = 0; index < frames.length; index++) {
            var frame = frames[index] || {};
            var key = String(frame.key || "");
            if (!key || !validBounds(frame.frame_bounds)) throw new Error("V2 color frame component contract is invalid");
            if (!validBounds(frame.artwork_bounds_after)) throw new Error("V2 color frame artwork audit bounds missing");
            byKey[key] = {
                key: key,
                frame_bounds: copyBounds(frame.frame_bounds),
                artwork_bounds_after: copyBounds(frame.artwork_bounds_after),
                tracked_slots: frame.tracked_slots || []
            };
        }
        return byKey;
    }

    function componentFrameForItem(item, frames, orderIndex, childIndex) {
        var key = String(item && item.name || "");
        var frame = frames[key];
        // AI8 save/outline may erase a nested GroupItem name.  The order/item
        // indexes are emitted by this composer contract and remain stable.
        if (!frame && Number(orderIndex) >= 0 && Number(childIndex) >= 0) {
            key = "ORDER_PACK_ITEM_" + Number(orderIndex) + "_" + Number(childIndex);
            frame = frames[key];
        }
        if (!frame) throw new Error("V2 color frame component frame missing for " + key);
        return frame;
    }

    function validateRequestedDimensions(frame, dimensions) {
        var requestedWidth = mmToPt(Number(dimensions.width_mm || 0));
        var requestedHeight = mmToPt(Number(dimensions.height_mm || 0));
        if (requestedWidth <= 0 && requestedHeight <= 0) return;
        if (requestedWidth <= 0 || requestedHeight <= 0) throw new Error("V2 color frame target dimensions missing");
        var width = Number(frame.frame_bounds[2]) - Number(frame.frame_bounds[0]);
        var height = Number(frame.frame_bounds[1]) - Number(frame.frame_bounds[3]);
        var epsilon = mmToPt(0.01);
        if (Math.abs(width - requestedWidth) > epsilon || Math.abs(height - requestedHeight) > epsilon) {
            throw new Error("V2 component frame does not match requested dimensions; refusing resize");
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
        var actual = pageItemBounds(item);
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
        var actual = pageItemBounds(item);
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

    function validBounds(bounds) {
        return bounds && bounds.length >= 4
            && isFinite(Number(bounds[0])) && isFinite(Number(bounds[1]))
            && isFinite(Number(bounds[2])) && isFinite(Number(bounds[3]));
    }

    function pageItemBounds(item) {
        var bounds = null;
        try { bounds = item.visibleBounds; } catch (e0) {}
        if (!bounds || bounds.length !== 4) {
            try { bounds = item.geometricBounds; } catch (e1) {}
        }
        if (!bounds || bounds.length !== 4) throw new Error("Cannot read order sub-item bounds");
        return [Number(bounds[0]), Number(bounds[1]), Number(bounds[2]), Number(bounds[3])];
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
            var bounds = pageItemBounds(frame);
            var width = Math.max(bounds[2] - bounds[0], 0.01);
            var height = Math.max(bounds[1] - bounds[3], 0.01);
            if ((width <= rectWidth + 0.01 && height <= rectHeight + 0.01) || size <= minSize) break;
            size = Math.max(minSize, size * Math.min(rectWidth / width, rectHeight / height, 0.92));
        }
        var finalBounds = pageItemBounds(frame);
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
        } catch (e0) {}
    }

    function outlineAllTextFrames(doc, pathfinderMerge) {
        var frames = [];
        for (var layerIndex = 0; layerIndex < doc.layers.length; layerIndex++) collectTextFrames(doc.layers[layerIndex], frames);
        for (var frameIndex = frames.length - 1; frameIndex >= 0; frameIndex--) {
            var outline = frames[frameIndex].createOutline();
            if (!outline) throw new Error("V2 color frame text outline failed");
            if (pathfinderMerge) {
                outline.selected = true;
                app.executeMenuCommand("Live Pathfinder Add");
                app.executeMenuCommand("expandStyle");
                outline.selected = false;
            }
        }
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

    function estimateLabelWidth(text, size) {
        return Math.max(String(text || "").length * Number(size || 6) * 0.55, mmToPt(8));
    }

    function writeDebug(task, plans, docWidth, docHeight, frameWidth, usableWidth, algorithm, frameLayout, componentContracts) {
        if (!task.debug || !task.debug.report_path) throw new Error("V2 color frame audit report path missing");
            var frames = [];
            for (var planIndex = 0; planIndex < plans.length; planIndex++) {
                var plan = plans[planIndex];
                frames.push({
                    color_option: plan.colorOption,
                    frame_left_mm: roundMm(plan.frameLeft),
                    frame_y_mm: roundMm(plan.frameY),
                    frame_column: plan.frameColumn,
                    frame_width_mm: roundMm(frameWidth),
                    frame_height_mm: roundMm(plan.frameHeight),
                    frame_boundary_stroked: colorFrameBoundary,
                    content_height_mm: roundMm(plan.contentHeight),
                    max_columns: plan.maxColumns,
                    ideal_rows: plan.idealRows,
                    hard_rows: plan.hardRows,
                    cell_width_mm: roundMm(plan.cellWidth),
                    slot_pitch_mm: roundMm(plan.slotPitch),
                    label_scope: "order_segment",
                    order_block_count: plan.orderBlockCount,
                    fragment_count: plan.placements.length,
                    sub_item_count: plan.subItemCount,
                    horizontal_overflow: false,
                    columns: auditColumns(plan.columns),
                    fragments: auditFragments(plan.placements)
                });
            }
            var file = File(String(task.debug.report_path));
            ensureFolder(file.parent);
            file.encoding = "UTF-8";
            if (!file.open("w")) throw new Error("Cannot write V2 color frame audit report: " + file.fsName);
            file.write(toJson({
                algorithm: algorithm,
                coordinate_unit: "mm",
                target_width_mm: roundMm(frameWidth),
                usable_width_mm: roundMm(usableWidth),
                artboard_width_mm: roundMm(docWidth),
                artboard_height_mm: roundMm(docHeight),
                color_frame_layout: auditColorFrameLayout(frameLayout),
                frames: frames,
                component_contract_version: 1,
                component_frames: componentContracts || []
            }));
            file.close();
    }

    function auditColorFrameLayout(frameLayout) {
        var columns = [];
        var layoutColumns = frameLayout.columns || [];
        for (var columnIndex = 0; columnIndex < layoutColumns.length; columnIndex++) {
            var column = layoutColumns[columnIndex];
            var colorOptions = [];
            for (var planIndex = 0; planIndex < column.plans.length; planIndex++) {
                colorOptions.push(column.plans[planIndex].colorOption);
            }
            columns.push({
                index: column.index,
                height_mm: roundMm(column.height),
                colors: colorOptions
            });
        }
        return {
            algorithm: "best_fit_color_frame_columns",
            target_height_mm: roundMm(frameLayout.targetHeight),
            column_count: columns.length,
            columns: columns
        };
    }

    function auditColumns(columns) {
        var result = [];
        for (var columnIndex = 0; columnIndex < columns.length; columnIndex++) {
            var column = columns[columnIndex];
            var segments = [];
            for (var segmentIndex = 0; segmentIndex < column.segments.length; segmentIndex++) {
                var segment = column.segments[segmentIndex];
                segments.push({
                    order_no: segment.orderNo,
                    item_count: segment.items.length,
                    y_mm: roundMm(segment.y),
                    height_mm: roundMm(segment.height)
                });
            }
            result.push({
                index: column.index,
                item_count: column.itemCount,
                height_mm: roundMm(column.height),
                segments: segments
            });
        }
        return result;
    }

    function auditFragments(placements) {
        var result = [];
        for (var placementIndex = 0; placementIndex < placements.length; placementIndex++) {
            var placement = placements[placementIndex];
            var items = [];
            for (var itemIndex = 0; itemIndex < placement.items.length; itemIndex++) {
                var item = placement.items[itemIndex];
                items.push({
                    source_child_index: item.sourceChildIndex,
                    x_mm: roundMm(placement.x + item.x),
                    y_mm: roundMm(placement.y + item.y),
                    width_mm: roundMm(item.width),
                    height_mm: roundMm(item.height),
                    label_required: false
                });
            }
            result.push({
                order_no: placement.orderNo,
                parent_block_id: placement.parentBlockId,
                fragment_id: placement.fragmentId,
                fragment_index: placement.fragmentIndex,
                fragment_count: placement.fragmentCount,
                split: placement.split === true,
                column_index: placement.columnIndex,
                label_required: true,
                item_count: placement.items.length,
                x_mm: roundMm(placement.x),
                y_mm: roundMm(placement.y),
                width_mm: roundMm(placement.width),
                height_mm: roundMm(placement.height),
                items: items
            });
        }
        return result;
    }

    function redColor() {
        var color = new RGBColor();
        color.red = 255;
        color.green = 0;
        color.blue = 0;
        return color;
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
        if (kind === "string") return "\"" + value.replace(/\\/g, "\\\\").replace(/\"/g, "\\\"").replace(/\n/g, "\\n") + "\"";
        if (value instanceof Array) {
            var arrayValues = [];
            for (var arrayIndex = 0; arrayIndex < value.length; arrayIndex++) arrayValues.push(toJson(value[arrayIndex]));
            return "[" + arrayValues.join(",") + "]";
        }
        var values = [];
        for (var key in value) if (value.hasOwnProperty(key)) values.push(toJson(String(key)) + ":" + toJson(value[key]));
        return "{" + values.join(",") + "}";
    }
}());
