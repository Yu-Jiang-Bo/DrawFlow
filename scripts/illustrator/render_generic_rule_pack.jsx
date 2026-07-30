#target illustrator

(function () {
    var EXACT_BOX_MAX_DELTA_PT = 0.02;
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "generic_template_rules") throw new Error("Unsupported task type: " + task.type);
    if (!task.orders || !task.orders.length) throw new Error("Generic task has no orders");
    var layoutAudit = createLayoutAudit(task);
    var exactBoxTargets = [];
    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var outputs = [];
    writeProgress(task, 0, task.orders.length, "正在渲染条目");
    if (usesNameColumnsLayout(task) && String(task.render_layout.output_mode || "") === "single_file") {
        trace(task, "name_columns:start");
        var sheet = createNameColumnsSheet(task);
        try {
            var sheetOutput = File(String(task.output_ai));
            ensureFolder(sheetOutput.parent);
            if (sheetOutput.exists) sheetOutput.remove();
            trace(task, "name_columns:before_save");
            applyOutputSettings(sheet, task.output || {}, []);
            finalizeExactBoxTargets(sheet);
            flushLayoutAudit();
            writeProgress(task, task.orders.length, task.orders.length, "正在保存 AI 文件");
            saveAsNativeAI(sheet, sheetOutput, task.output && task.output.compatibility);
            trace(task, "name_columns:after_save");
            outputs.push(sheetOutput.fsName);
        } finally {
            writeProgress(task, task.orders.length, task.orders.length, "正在关闭 Illustrator 文档");
            sheet.close(SaveOptions.DONOTSAVECHANGES);
        }
        return outputs.join("\n");
    }
    for (var orderIndex = 0; orderIndex < task.orders.length; orderIndex++) {
        var order = task.orders[orderIndex];
        writeProgress(task, orderIndex, task.orders.length, "正在打开模板");
        var doc = usesNameColumnsLayout(task) ? createNameColumnsDocument(task, order) : app.open(File(String(task.template_ai)));
        try {
            writeProgress(task, orderIndex, task.orders.length, "正在渲染条目");
            if (!usesNameColumnsLayout(task)) {
                applyOptionGroups(doc, task.option_groups || [], order.selections || {});
                applyVariables(doc, order.variables || [], task.dimensions || {}, task.text_policies || {}, order.selections || {}, task.allow_unnamed_name_fallback === true);
                applyAssets(doc, order.assets || []);
                applyTransforms(doc, order.transforms || task.transforms || {}, order.variables || []);
                if (task.output && task.output.outline_text) {
                    writeProgress(task, orderIndex, task.orders.length, "正在转曲文字");
                }
                applyOutputSettings(doc, task.output || {}, order.variables || []);
                finalizeExactBoxTargets(doc);
                flushLayoutAudit();
            } else {
                applyOutputSettings(doc, task.output || {}, []);
                finalizeExactBoxTargets(doc);
                flushLayoutAudit();
            }
            var output = File(String(order.output_ai));
            if (String(task.output && task.output.format || "").toLowerCase() === "png") {
                var pngOutput = File(String(order.output_png || order.output_ai));
                ensureFolder(pngOutput.parent);
                if (pngOutput.exists) pngOutput.remove();
                writeProgress(task, orderIndex, task.orders.length, "正在保存 PNG 文件");
                exportPng(doc, pngOutput, Number(task.output && task.output.dpi || 300));
                outputs.push(pngOutput.fsName);
                writeProgress(task, orderIndex + 1, task.orders.length, "已保存 PNG 文件");
                continue;
            }
            ensureFolder(output.parent);
            if (output.exists) output.remove();
            writeProgress(task, orderIndex, task.orders.length, "正在保存 AI 文件");
            saveAsNativeAI(doc, output, task.output && task.output.compatibility);
            outputs.push(output.fsName);
            writeProgress(task, orderIndex + 1, task.orders.length, "已保存 AI 文件");
        } finally {
            writeProgress(task, Math.min(orderIndex + 1, task.orders.length), task.orders.length, "正在关闭 Illustrator 文档");
            doc.close(SaveOptions.DONOTSAVECHANGES);
        }
    }
    return outputs.join("\n");

    function applyOptionGroups(doc, groups, selections) {
        for (var i = 0; i < groups.length; i++) {
            var group = groups[i] || {};
            var role = String(group.role || "");
            var selected = selectionForRole(role, selections);
            var values = group.values || group.options || [];
            for (var j = 0; j < values.length; j++) {
                var name = String(values[j]);
                var item = findPageItemByName(doc, name);
                if (!item) continue;
                try { item.hidden = Boolean(selected && name !== selected); } catch (e1) {}
                try { item.locked = false; } catch (e2) {}
            }
        }
    }

    function selectionForRole(role, selections) {
        if (role === "font_options") return String(selections.font || "");
        if (role === "design_options") return String(selections.design || "");
        if (role === "style_options") return String(selections.style || "");
        return "";
    }

    function usesNameColumnsLayout(task) {
        return task.render_layout && String(task.render_layout.type || "") === "name_columns";
    }

    function createNameColumnsSheet(task) {
        var layout = task.render_layout || {};
        var dimensions = task.dimensions || {};
        var cellWidth = mmToPt(Number(layout.width_mm || 100));
        var cellHeight = mmToPt(Number(layout.height_mm || 220));
        var requestedColumns = Math.max(1, Number(task.layout && task.layout.columns || 4));
        var columns = requestedColumns;
        var pageRows = Math.max(1, Number(layout.page_rows || 6));
        var masonry = String(layout.packing || "") === "masonry";
        var pageHeight = masonry ? mmToPt(Number(layout.page_height_mm || 1320)) : cellHeight * pageRows;
        var plan = masonry ? planNameColumnsMasonry(task.orders, layout, columns, cellWidth, pageHeight, dimensions) : planNameColumnsGrid(task.orders, columns, cellWidth, cellHeight, pageRows);
        if (masonry && String(layout.artboard_mode || "") === "single") {
            var maxArtboardSize = mmToPt(Number(layout.max_artboard_size_mm || 5750));
            var singlePlan = planNameColumnsSingleArtboard(task.orders, layout, requestedColumns, cellWidth, maxArtboardSize, dimensions);
            if (singlePlan) {
                plan = singlePlan;
                columns = singlePlan.columns;
                pageHeight = singlePlan.height;
            }
        }
        var pages = plan.pages;
        var pageWidth = cellWidth * columns;
        var height = pageHeight;
        trace(task, "name_columns:planned items=" + plan.items.length + " pages=" + pages + " columns=" + columns + " height_mm=" + (height * 25.4 / 72));
        trace(task, "name_columns:before_open_source");
        var source = app.open(File(String(task.template_ai)));
        trace(task, "name_columns:after_open_source");
        try {
            // Create the first artboard at page width; append any subsequent pages explicitly.
            var doc = app.documents.add(DocumentColorSpace.RGB, pageWidth, height);
            for (var pageIndex = 1; pageIndex < pages; pageIndex++) {
                doc.artboards.add([pageIndex * pageWidth, height, (pageIndex + 1) * pageWidth, 0]);
            }
            trace(task, "name_columns:doc_ready");
            var fontCache = {};
            var declaredFontStyles = task.font_option_styles || {};
            for (var index = 0; index < plan.items.length; index++) {
                var item = plan.items[index];
                var order = item.order;
                var selected = String(order.selections && order.selections.font || "");
                var fontStyle = fontStyleForSelection(source, doc, fontCache, selected, declaredFontStyles);
                drawNameColumns(doc, order, layout, fontStyle, {
                    left: item.page * pageWidth + item.column * cellWidth,
                    top: height - item.y,
                    width: cellWidth,
                    height: item.height
                }, dimensions);
                writeProgress(task, index + 1, plan.items.length, "正在渲染条目");
                if ((index + 1) % 25 === 0 || index + 1 === plan.items.length) {
                    trace(task, "name_columns:drawn " + (index + 1) + "/" + plan.items.length);
                }
            }
            removeFontPrototypes(fontCache);
            return doc;
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function planNameColumnsGrid(orders, columns, cellWidth, cellHeight, pageRows) {
        var pageSize = columns * pageRows;
        var items = [];
        for (var index = 0; index < orders.length; index++) {
            var page = Math.floor(index / pageSize);
            var pageItemIndex = index % pageSize;
            items.push({
                order: orders[index],
                page: page,
                column: pageItemIndex % columns,
                y: Math.floor(pageItemIndex / columns) * cellHeight,
                height: cellHeight
            });
        }
        return {items: items, pages: Math.max(1, Math.ceil(orders.length / pageSize))};
    }

    function planNameColumnsMasonry(orders, layout, columns, cellWidth, pageHeight, dimensions) {
        var gap = mmToPt(Number(layout.card_gap_mm || 8));
        var items = [];
        var page = 0;
        var columnHeights = emptyColumnHeights(columns);
        for (var index = 0; index < orders.length; index++) {
            var blockHeight = nameColumnsBlockHeight(orders[index], layout, dimensions);
            var column = shortestColumnIndex(columnHeights);
            if (columnHeights[column] > 0 && columnHeights[column] + blockHeight > pageHeight) {
                page++;
                columnHeights = emptyColumnHeights(columns);
                column = 0;
            }
            items.push({
                order: orders[index],
                page: page,
                column: column,
                y: columnHeights[column],
                height: blockHeight
            });
            columnHeights[column] += blockHeight + gap;
        }
        return {items: items, pages: Math.max(1, page + 1)};
    }

    function planNameColumnsSingleArtboard(orders, layout, requestedColumns, cellWidth, maxArtboardSize, dimensions) {
        var maxColumns = Math.floor(maxArtboardSize / cellWidth);
        for (var columns = requestedColumns; columns <= maxColumns; columns++) {
            var plan = planNameColumnsMasonryUnbounded(orders, layout, columns, dimensions);
            if (plan.height <= maxArtboardSize && columns * cellWidth <= maxArtboardSize) return plan;
        }
        return null;
    }

    function planNameColumnsMasonryUnbounded(orders, layout, columns, dimensions) {
        var gap = mmToPt(Number(layout.card_gap_mm || 8));
        var items = [];
        var columnHeights = emptyColumnHeights(columns);
        for (var index = 0; index < orders.length; index++) {
            var blockHeight = nameColumnsBlockHeight(orders[index], layout, dimensions);
            var column = shortestColumnIndex(columnHeights);
            items.push({
                order: orders[index],
                page: 0,
                column: column,
                y: columnHeights[column],
                height: blockHeight
            });
            columnHeights[column] += blockHeight + gap;
        }
        return {
            items: items,
            pages: 1,
            columns: columns,
            height: Math.max(1, largestValue(columnHeights) - gap)
        };
    }

    function nameColumnsBlockHeight(order, layout, dimensions) {
        var mode = order.layout_mode || layout.default || {};
        var members = order.layout_members || [order];
        var name = layout.name || {};
        var nameSize = Number(name.font_size_pt || 72);
        var segmentBox = configuredNameSegmentBox(layout, dimensions);
        var lineGap = mmToPt(Number(name.line_gap_mm || 8));
        var maxLines = 1;
        for (var index = 0; index < members.length; index++) {
            var variable = findNameVariable(members[index].variables || []);
            if (variable) maxLines = Math.max(maxLines, (segmentBox ? splitBoxedNameParts(variable.value, name) : splitNameParts(variable.value, String(name.delimiter || "|"))).length);
        }
        var header = mode.header_fields && mode.header_fields.length ? mmToPt(Number(layout.header_height_mm || 24)) : 0;
        var footer = shouldDrawLayoutFooter(order, mode, layout) ? mmToPt(Number(layout.footer_height_mm || 12)) : 0;
        var margin = mmToPt(Number(layout.margin_mm || 10));
        var lineHeight = segmentBox ? mmToPt(segmentBox.height_mm) : nameSize;
        return margin * 2 + header + footer + maxLines * lineHeight + Math.max(0, maxLines - 1) * lineGap;
    }

    function emptyColumnHeights(columns) {
        var values = [];
        for (var index = 0; index < columns; index++) values.push(0);
        return values;
    }

    function shortestColumnIndex(values) {
        var shortest = 0;
        for (var index = 1; index < values.length; index++) {
            if (values[index] < values[shortest]) shortest = index;
        }
        return shortest;
    }

    function largestValue(values) {
        var largest = values.length ? values[0] : 0;
        for (var index = 1; index < values.length; index++) {
            if (values[index] > largest) largest = values[index];
        }
        return largest;
    }

    function createNameColumnsDocument(task, order) {
        var layout = task.render_layout || {};
        var width = mmToPt(Number(layout.width_mm || 100));
        var height = mmToPt(Number(layout.height_mm || 220));
        var source = app.open(File(String(task.template_ai)));
        var fontSource = null;
        try {
            var doc = app.documents.add(DocumentColorSpace.RGB, width, height);
            var fontCache = {};
            var selected = String(order.selections && order.selections.font || "");
            if (selected) fontSource = fontStyleForSelection(source, doc, fontCache, selected, task.font_option_styles || {});
            drawNameColumns(doc, order, layout, fontSource, null, task.dimensions || {});
            removeFontPrototypes(fontCache);
            flushLayoutAudit();
            return doc;
        } finally {
            source.close(SaveOptions.DONOTSAVECHANGES);
        }
    }

    function drawNameColumns(doc, order, layout, fontSource, cell, dimensions) {
        var mode = order.layout_mode || layout.default || {};
        var members = order.layout_members || [order];
        var margin = mmToPt(Number(layout.margin_mm || 10));
        var headerHeight = mmToPt(Number(layout.header_height_mm || 24));
        var footerHeight = mmToPt(Number(layout.footer_height_mm || 12));
        var name = layout.name || {};
        var nameSize = Number(name.font_size_pt || 72);
        var segmentBox = configuredNameSegmentBox(layout, dimensions);
        var lineGap = mmToPt(Number(name.line_gap_mm || 8));
        var columnGap = mmToPt(Number(name.column_gap_mm || 12));
        var bounds = doc.artboards[0].artboardRect;
        var width = cell ? cell.width : bounds[2] - bounds[0];
        var height = cell ? cell.height : bounds[1] - bounds[3];
        var left = cell ? cell.left : 0;
        var cardTop = cell ? cell.top : height;
        var cardBottom = cardTop - height;
        var innerTop = cardTop - margin;
        var cardBackground = rgbColor(String(layout.background_color || ""));
        if (cardBackground && !(task.output && task.output.transparent_background === true && String(task.output.format || "").toLowerCase() === "png")) drawCardBackground(doc, left, cardTop, width, height, cardBackground);
        var headerFields = mode.header_fields || [];
        if (headerFields.length) {
            addLayoutText(doc, joinFields(members[0], headerFields), left + width / 2, innerTop, Number(layout.header_font_size_pt || 16), rgbColor(layout.header_color || "#000000"), null, true);
        }
        var availableWidth = width - margin * 2;
        var columnWidth = (availableWidth - Math.max(0, members.length - 1) * columnGap) / Math.max(1, members.length);
        var footerField = String(mode.footer_field || "");
        var footerText = footerField ? fieldValue(members[0], footerField) : "";
        var drawFooter = shouldDrawLayoutFooter(order, mode, layout);
        var nameTop = innerTop - (headerFields.length ? headerHeight : 0);
        var nameBottom = cardBottom + margin + (drawFooter ? footerHeight : 0);
        var minimumNameHeight = segmentBox ? mmToPt(segmentBox.height_mm) : nameSize;
        var availableHeight = Math.max(minimumNameHeight, nameTop - nameBottom);
        var maxNameWidth = columnWidth * Number(name.max_width_ratio || 0.96);
        var minNameSize = Number(name.min_font_size_pt || 18);
        for (var memberIndex = 0; memberIndex < members.length; memberIndex++) {
            var member = members[memberIndex];
            var variable = findNameVariable(member.variables || []);
            if (!variable) throw new Error("Name columns layout requires a Name variable");
            var parts = segmentBox ? splitBoxedNameParts(variable.value, name) : splitNameParts(variable.value, String(name.delimiter || "|"));
            var x = left + margin + memberIndex * (columnWidth + columnGap) + columnWidth / 2;
            var fittedSize = fittedNameSize(parts, nameSize, maxNameWidth, minNameSize);
            var lineHeight = segmentBox ? mmToPt(segmentBox.height_mm) : fittedSize;
            var blockHeight = parts.length * lineHeight + Math.max(0, parts.length - 1) * lineGap;
            var startY = nameTop - Math.max(0, (availableHeight - blockHeight) / 2);
            if (segmentBox) {
                for (var partIndex = 0; partIndex < parts.length; partIndex++) {
                    addBoxedNameSegment(
                        doc,
                        parts[partIndex],
                        x,
                        startY - partIndex * (lineHeight + lineGap),
                        lineHeight,
                        nameSize,
                        segmentBox,
                        variable,
                        layout.name_color_cycle || {},
                        partIndex,
                        fontSource,
                        member
                    );
                }
            } else {
                addNameBlockText(
                    doc,
                    parts,
                    x,
                    startY,
                    fittedSize,
                    lineGap,
                    variable.actions || [],
                    layout.name_color_cycle || {},
                    fontSource
                );
            }
        }
        if (drawFooter) {
            var footerFrame = addLayoutText(doc, footerText, left + width / 2, cardBottom + margin + footerHeight, Number(layout.footer_font_size_pt || 20), rgbColor(layout.footer_color || "#FFFFFF"), fontSource, true);
            var footerBox = layout.footer || {};
            var footerTarget = String(footerBox.box_target || "");
            if (footerTarget) {
                var footerVariable = findVariable(members[0].variables || [], footerTarget);
                if (!footerVariable) throw new Error("Name columns footer requires a " + footerTarget + " variable");
                applyNonColorActions(footerFrame, footerVariable.actions || []);
                if (!footerVariable.actions || !footerVariable.actions.length) applyFontBoldness(footerFrame, footerVariable.font_style);
                var footerDimension = configuredDimension(dimensions, footerTarget, "footer");
                var footerAuditName = footerTarget + "Box_" + layoutAuditIdentity(members[0]);
                var footerDiagnosticTarget = footerTarget + " row " + String(members[0].row_index || "unknown");
                if (isEnabled(footerBox.fill_box_exactly)) {
                    var footerWidth = mmToPt(footerDimension.width_mm);
                    var footerHeightExact = mmToPt(footerDimension.height_mm);
                    var footerBoxTop = cardBottom + margin + footerHeight / 2 + footerHeightExact / 2;
                    var footerRect = exactBoxRect(
                        left + width / 2 - footerWidth / 2,
                        footerBoxTop,
                        footerWidth,
                        footerHeightExact
                    );
                    fitPageItemToExactBox(footerFrame, footerRect, footerDiagnosticTarget);
                    registerExactBoxTarget("year", footerAuditName, footerDiagnosticTarget, footerRect);
                } else {
                    fitTextStrict(footerFrame, footerDimension.width_mm, footerDimension.height_mm, footerDiagnosticTarget);
                    centerLayoutTextInBox(footerFrame, left + width / 2, cardBottom + margin + footerHeight, footerHeight);
                    recordLayoutAudit("year", footerAuditName, footerFrame);
                }
                wrapGeneratedText(footerFrame, footerAuditName);
            }
        }
    }

    function drawCardBackground(doc, left, top, width, height, color) {
        var background = doc.pathItems.rectangle(top, left, width, height);
        background.fillColor = color;
        background.stroked = false;
    }

    function addLayoutText(doc, text, x, y, size, color, fontSource, centered) {
        var frame = fontSource && fontSource.prototype
            ? fontSource.prototype.duplicate(doc.layers[0], ElementPlacement.PLACEATEND)
            : doc.textFrames.add();
        try { frame.hidden = false; frame.locked = false; } catch (e0) {}
        frame.contents = String(text || "");
        if (fontSource && !fontSource.prototype) applyLayoutTextStyle(fontSource, frame);
        try { frame.textRange.characterAttributes.size = size; } catch (e1) {}
        if (color) {
            try { frame.textRange.characterAttributes.fillColor = color; } catch (e2) {}
        }
        try { frame.textRange.paragraphAttributes.justification = centered ? Justification.CENTER : Justification.LEFT; } catch (e3) {}
        frame.position = [x, y];
        if (centered) {
            try { frame.left = x - (frame.width / 2); } catch (e4) {}
        }
        return frame;
    }

    function addNameBlockText(doc, parts, x, y, size, lineGap, actions, legacyCycle, fontSource) {
        var frame = addLayoutText(doc, parts.join("\r"), x, y, size, null, fontSource, true);
        try { frame.textRange.characterAttributes.leading = size + lineGap; } catch (e1) {}
        applyNameBlockColors(frame, parts, actions, legacyCycle);
        applyNameBlockBoldness(frame, actions);
        centerLayoutText(frame, x);
        return frame;
    }

    function addBoxedNameSegment(doc, text, x, top, height, size, box, variable, legacyCycle, index, fontSource, member) {
        var frame = addLayoutText(doc, text, x, top, size, null, fontSource, true);
        var color = colorForNamePart(variable.actions || [], index, legacyCycle);
        if (color) {
            try { frame.textRange.characterAttributes.fillColor = color; } catch (e1) {}
        }
        applyNonColorActions(frame, variable.actions || []);
        if (!variable.actions || !variable.actions.length) applyFontBoldness(frame, variable.font_style);
        var boxWidth = mmToPt(box.width_mm);
        var boxHeight = mmToPt(box.height_mm);
        var boxRect = exactBoxRect(x - boxWidth / 2, top, boxWidth, boxHeight);
        if (isEnabled(box.fill_box_exactly)) {
            fitPageItemToExactBox(frame, boxRect, box.target);
        } else {
            fitTextStrict(frame, box.width_mm, box.height_mm, box.target);
            centerLayoutTextInBox(frame, x, top, height);
        }
        var auditName = box.target + "Box_" + layoutAuditIdentity(member) + "_" + String(index + 1);
        if (isEnabled(box.fill_box_exactly)) {
            registerExactBoxTarget("name", auditName, box.target, boxRect);
        } else {
            recordLayoutAudit("name", auditName, frame, null);
        }
        wrapGeneratedText(frame, auditName);
        return frame;
    }

    function fittedNameSize(parts, baseSize, maxWidth, minSize) {
        var widest = 0;
        for (var index = 0; index < parts.length; index++) {
            widest = Math.max(widest, estimatedLayoutTextWidth(String(parts[index] || ""), baseSize));
        }
        if (!widest || widest <= maxWidth) return baseSize;
        return Math.max(minSize, baseSize * Math.max(0.5, Math.min(0.95, maxWidth / widest)));
    }

    function applyNameBlockColors(frame, parts, actions, legacyCycle) {
        try {
            var lines = frame.lines;
            if (lines && lines.length >= parts.length) {
                for (var lineIndex = 0; lineIndex < parts.length; lineIndex++) {
                    var lineColor = colorForNamePart(actions, lineIndex, legacyCycle);
                    if (lineColor) lines[lineIndex].characterAttributes.fillColor = lineColor;
                }
                return;
            }
        } catch (e1) {}
        var cursor = 0;
        for (var partIndex = 0; partIndex < parts.length; partIndex++) {
            var color = colorForNamePart(actions, partIndex, legacyCycle);
            if (color) applyCharacterRangeColor(frame, cursor, String(parts[partIndex]).length, color);
            cursor += String(parts[partIndex]).length + (partIndex < parts.length - 1 ? 1 : 0);
        }
    }

    function applyCharacterRangeColor(frame, start, length, color) {
        try {
            var characters = frame.characters;
            for (var index = 0; index < length; index++) {
                characters[start + index].characterAttributes.fillColor = color;
            }
        } catch (e1) {}
    }

    function applyNameBlockBoldness(frame, actions) {
        for (var actionIndex = 0; actionIndex < actions.length; actionIndex++) {
            var action = actions[actionIndex] || {};
            if (String(action.type || "") !== "stroke_width") continue;
            if (!applyLineBoldness(frame, action.value)) applyCharactersBoldness(frame, action.value);
        }
    }

    function applyLineBoldness(frame, value) {
        var boldness = Number(value);
        if (isNaN(boldness) || boldness <= 0) return true;
        try {
            var lines = frame.lines;
            for (var index = 0; index < lines.length; index++) {
                applyBoldnessToAttributes(lines[index].characterAttributes, boldness);
            }
            return true;
        } catch (e1) {}
        return false;
    }

    function applyCharactersBoldness(frame, value) {
        var boldness = Number(value);
        if (isNaN(boldness) || boldness <= 0) return;
        try {
            var characters = frame.characters;
            for (var index = 0; index < characters.length; index++) {
                applyBoldnessToAttributes(characters[index].characterAttributes, boldness);
            }
            if (characters.length) return;
        } catch (e1) {}
        applyFrameBoldness(frame, boldness);
    }

    function fitLayoutTextWidth(frame, maxWidth, minSize) {
        maxWidth = Number(maxWidth);
        minSize = Number(minSize || 18);
        if (isNaN(maxWidth) || maxWidth <= 0) return;
        var attributes = frame.textRange.characterAttributes;
        var size = Number(attributes.size || 0);
        if (!size || size <= minSize) return false;
        var width = estimatedLayoutTextWidth(String(frame.contents || ""), size);
        if (!width || width <= maxWidth) return false;
        var nextSize = Math.max(minSize, size * Math.max(0.5, Math.min(0.95, maxWidth / width)));
        if (Math.abs(nextSize - size) < 0.1) return false;
        try { attributes.size = nextSize; return true; } catch (e1) {}
        return false;
    }

    function estimatedLayoutTextWidth(text, size) {
        var units = 0;
        for (var index = 0; index < text.length; index++) {
            var code = text.charCodeAt(index);
            units += code > 255 ? 1 : 0.55;
        }
        return units * size;
    }

    function centerLayoutText(frame, x) {
        try {
            frame.left = x - frame.width / 2;
            return;
        } catch (e1) {}
        try {
            var bounds = frame.visibleBounds;
            frame.translate(x - (Number(bounds[0]) + Number(bounds[2])) / 2, 0);
        } catch (e2) {}
    }

    function centerLayoutTextInBox(frame, x, top, height) {
        try {
            var bounds = frame.visibleBounds;
            var centerX = (Number(bounds[0]) + Number(bounds[2])) / 2;
            var centerY = (Number(bounds[1]) + Number(bounds[3])) / 2;
            frame.translate(x - centerX, top - height / 2 - centerY);
        } catch (e1) {
            centerLayoutText(frame, x);
        }
    }

    function wrapGeneratedText(frame, name) {
        try {
            var parent = frame.parent;
            var holder = parent.groupItems.add();
            frame.move(holder, ElementPlacement.PLACEATEND);
            holder.name = name;
            return holder;
        } catch (e1) {
            try { frame.name = name; } catch (e2) {}
            return frame;
        }
    }

    function exactBoxRect(left, top, width, height) {
        return {
            left: Number(left),
            top: Number(top),
            right: Number(left) + Number(width),
            bottom: Number(top) - Number(height)
        };
    }

    function registerExactBoxTarget(kind, name, target, rect) {
        exactBoxTargets.push({
            kind: String(kind || ""),
            name: String(name || ""),
            target: String(target || ""),
            rect: {
                left: Number(rect.left),
                top: Number(rect.top),
                right: Number(rect.right),
                bottom: Number(rect.bottom)
            }
        });
    }

    function finalizeExactBoxTargets(doc) {
        for (var index = 0; index < exactBoxTargets.length; index++) {
            var entry = exactBoxTargets[index];
            var item = findPageItemByName(doc, entry.name);
            if (!item) throw new Error("Exact text box target missing after final rendering: " + entry.name);
            fitPageItemToExactBox(item, entry.rect, entry.target || entry.name);
            recordLayoutAudit(entry.kind, entry.name, item, entry.rect);
        }
        exactBoxTargets = [];
    }

    function createLayoutAudit(task) {
        var path = String(task.layout_audit_file || "");
        return path ? {file: File(path), lines: ["kind\tname\tleft_pt\ttop_pt\tright_pt\tbottom_pt\twidth_mm\theight_mm\tfill\texpected_left_pt\texpected_top_pt\texpected_right_pt\texpected_bottom_pt\tleft_delta_pt\ttop_delta_pt\tright_delta_pt\tbottom_delta_pt"]} : null;
    }

    function recordLayoutAudit(kind, name, frame, expected) {
        if (!layoutAudit) return;
        try {
            var bounds = measuredBounds(frame);
            var left = Number(bounds[0]);
            var top = Number(bounds[1]);
            var right = Number(bounds[2]);
            var bottom = Number(bounds[3]);
            layoutAudit.lines.push([
                String(kind),
                String(name),
                left,
                top,
                right,
                bottom,
                Math.abs(right - left) * 25.4 / 72,
                Math.abs(top - bottom) * 25.4 / 72,
                auditFillColor(frame),
                expected ? expected.left : "",
                expected ? expected.top : "",
                expected ? expected.right : "",
                expected ? expected.bottom : "",
                expected ? left - expected.left : "",
                expected ? top - expected.top : "",
                expected ? right - expected.right : "",
                expected ? bottom - expected.bottom : ""
            ].join("\t"));
        } catch (e1) {
            throw new Error("Cannot audit layout text: " + name);
        }
    }

    function layoutAuditIdentity(order) {
        var row = String(order.row_index || "row");
        var copy = order.quantity_index;
        return copy === undefined || copy === null || copy === "" ? row : row + "_copy_" + String(copy);
    }

    function auditFillColor(frame) {
        try {
            var color = frame.textRange.characterAttributes.fillColor;
            if (String(color.typename || "") === "RGBColor") {
                return [Math.round(Number(color.red)), Math.round(Number(color.green)), Math.round(Number(color.blue))].join(",");
            }
            if (String(color.typename || "") === "CMYKColor") {
                return [Number(color.cyan), Number(color.magenta), Number(color.yellow), Number(color.black)].join(",");
            }
        } catch (e1) {}
        return "";
    }

    function flushLayoutAudit() {
        if (!layoutAudit) return;
        var file = layoutAudit.file;
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write layout audit: " + file.fsName);
        file.write(layoutAudit.lines.join("\r\n"));
        file.close();
    }

    function fontStyleForSelection(source, targetDoc, cache, selected, declaredStyles) {
        var key = String(selected || "");
        if (!key) return null;
        if (cache[key] !== undefined) return cache[key];
        if (declaredStyles && declaredStyles[key]) {
            cache[key] = {fontConfig: declaredStyles[key]};
            return cache[key];
        }
        var sourceFrame = firstTextFrame(findPageItemByName(source, key));
        cache[key] = createFontPrototype(sourceFrame, targetDoc) || sourceFrame;
        return cache[key];
    }

    function createFontPrototype(sourceFrame, targetDoc) {
        if (!sourceFrame || !targetDoc) return null;
        try {
            var prototype = sourceFrame.duplicate(targetDoc.layers[0], ElementPlacement.PLACEATEND);
            prototype.contents = "";
            prototype.hidden = true;
            prototype.locked = false;
            return {prototype: prototype};
        } catch (e1) {}
        return null;
    }

    function removeFontPrototypes(cache) {
        for (var key in cache) {
            if (!cache.hasOwnProperty(key)) continue;
            var item = cache[key];
            if (item && item.prototype) {
                try { item.prototype.remove(); } catch (e1) {}
            }
        }
    }

    function splitNameParts(value, delimiter) {
        var text = String(value || "");
        var parts = delimiter ? text.split(delimiter) : [text];
        var result = [];
        for (var i = 0; i < parts.length; i++) {
            var part = trimText(parts[i]);
            if (part) result.push(part);
        }
        return result.length ? result : [text];
    }

    function splitBoxedNameParts(value, name) {
        var delimiter = String(name.delimiter || "|");
        if (!delimiter) throw new Error("Name segment boxes require a delimiter");
        var rawParts = String(value || "").split(delimiter);
        var parts = [];
        for (var index = 0; index < rawParts.length; index++) {
            var part = trimText(rawParts[index]);
            if (!part) throw new Error("Name segment boxes do not allow empty name segments");
            parts.push(part);
        }
        var minimum = positiveLayoutInteger(name.min_parts, 1);
        var maximum = positiveLayoutInteger(name.max_parts, 0);
        if (parts.length < minimum || (maximum && parts.length > maximum)) {
            throw new Error("Name segment count is outside the configured range");
        }
        return parts;
    }

    function positiveLayoutInteger(value, fallback) {
        var parsed = Number(value);
        return !isNaN(parsed) && parsed > 0 && Math.floor(parsed) === parsed ? parsed : fallback;
    }

    function configuredNameSegmentBox(layout, dimensions) {
        var name = layout.name || {};
        var target = String(name.segment_box_target || "");
        if (!target) return null;
        var box = configuredDimension(dimensions, target, "name segment");
        box.fill_box_exactly = isEnabled(name.fill_box_exactly);
        return box;
    }

    function configuredDimension(dimensions, target, label) {
        var dimension = (dimensions || {})[target];
        var width = Number(dimension && dimension.width_mm || 0);
        var height = Number(dimension && dimension.height_mm || 0);
        if (!dimension || width <= 0 || height <= 0) {
            throw new Error("Configured " + label + " dimension is missing or invalid: " + target);
        }
        return {target: target, width_mm: width, height_mm: height};
    }

    function isEnabled(value) {
        if (value === true) return true;
        var text = String(value || "").replace(/^\s+|\s+$/g, "").toLowerCase();
        return text === "1" || text === "true" || text === "yes" || text === "on";
    }

    function shouldDrawLayoutFooter(order, mode, layout) {
        var field = String(mode.footer_field || "");
        if (!field) return false;
        var footer = layout.footer || {};
        var value = fieldValue(order, field);
        if (String(footer.box_target || "") && footer.optional === true) {
            return Boolean(trimText(value));
        }
        return hasLayoutTextValue(value);
    }

    function findNameVariable(variables) {
        return findVariable(variables, "Name");
    }

    function findVariable(variables, target) {
        for (var i = 0; i < variables.length; i++) {
            if (String(variables[i].target || "") === String(target || "")) return variables[i];
        }
        return null;
    }

    function colorForNamePart(actions, index, legacyCycle) {
        for (var i = 0; i < actions.length; i++) {
            var action = actions[i] || {};
            var selector = action.selector || {};
            if (String(action.type || "") === "fill_color" && String(selector.type || "") === "segments") {
                var values = action.values || [];
                if (values.length) return rgbColor(values[index % values.length]);
            }
        }
        var legacyColors = legacyCycle.colors || [];
        return legacyColors.length ? rgbColor(legacyColors[index % legacyColors.length]) : null;
    }

    function applyNonColorActions(frame, actions) {
        for (var i = 0; i < actions.length; i++) {
            var action = actions[i] || {};
            if (String(action.type || "") === "stroke_width") applyFrameBoldness(frame, action.value);
        }
    }

    function applyFrameBoldness(frame, value) {
        var boldness = Number(value);
        if (isNaN(boldness) || boldness <= 0) return;
        applyBoldnessToAttributes(frame.textRange.characterAttributes, boldness);
    }

    function fieldValue(order, field) {
        var values = order.values || {};
        var selections = order.selections || {};
        if (field === "order_no") return String(order.order_no || values.order_no || "");
        return String(values[field] || selections[field] || "");
    }

    function hasLayoutTextValue(value) {
        return String(value == null ? "" : value).replace(/^\s+|\s+$/g, "") !== "";
    }

    function joinFields(order, fields) {
        var values = [];
        for (var i = 0; i < fields.length; i++) {
            var value = fieldValue(order, String(fields[i]));
            if (value) values.push(value);
        }
        return values.join("\r");
    }

    function applyVariables(doc, variables, dimensions, policies, selections, allowUnnamedNameFallback) {
        var selectedFont = String(selections.font || "");
        var fontSource = selectedFont ? firstTextFrame(findPageItemByName(doc, selectedFont)) : null;
        for (var i = 0; i < variables.length; i++) {
            var variable = variables[i];
            var items = resolveVariableTargets(doc, variable, allowUnnamedNameFallback);
            if (!items.length) throw new Error("Text target not found: " + variable.target);
            var dimension = dimensions[String(variable.target || "")];
            if (!dimension) dimension = dimensions[String(variable.target || "") + "_ANCHOR"];
            if (!dimension && selections.style) dimension = dimensions[String(selections.style)];
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                var frame = firstTextFrame(items[itemIndex]);
                if (!frame) throw new Error("Target has no editable text: " + variable.target);
                try { frame.locked = false; frame.hidden = false; } catch (e1) {}
                frame.contents = String(variable.value || "");
                if (fontSource) copyTextStyle(fontSource, frame);
                applyTextColor(frame, String(selections.color || ""));
                if (variable.actions && variable.actions.length) {
                    applyRuleActions(frame, variable.actions);
                } else {
                    applyNameColorCycle(frame, variable);
                    applyFontBoldness(frame, variable.font_style);
                }
                if (dimension && String(policies.fit || "") !== "none") {
                    fitText(frame, Number(dimension.width_mm || 0), Number(dimension.height_mm || 0));
                }
            }
        }
    }

    function applyAssets(doc, assets) {
        for (var i = 0; i < assets.length; i++) {
            var entry = assets[i];
            var target = findPageItemByName(doc, String(entry.target || ""));
            if (!target) throw new Error("Asset target not found: " + entry.target);
            var targetBounds = target.visibleBounds;
            var assetDoc = app.open(File(String(entry.asset)));
            try {
                var holder = target.typename === "GroupItem" ? target : target.parent.groupItems.add();
                for (var p = assetDoc.pageItems.length - 1; p >= 0; p--) {
                    assetDoc.pageItems[p].duplicate(holder, ElementPlacement.PLACEATEND);
                }
                centerItem(holder, targetBounds);
            } finally {
                assetDoc.close(SaveOptions.DONOTSAVECHANGES);
            }
        }
    }

    function applyTransforms(doc, transforms, variables) {
        var targets = transforms.targets || [];
        for (var t = 0; t < targets.length; t++) {
            var settings = targets[t] || {};
            var items = findPageItemsByName(doc, String(settings.target || ""));
            for (var itemIndex = 0; itemIndex < items.length; itemIndex++) {
                var targetItem = items[itemIndex];
                if (Number(settings.rotation_deg || 0)) {
                    try { targetItem.rotate(Number(settings.rotation_deg)); } catch (e1) {}
                }
                if (Number(settings.scale_percent || 0)) {
                    try { targetItem.resize(Number(settings.scale_percent), Number(settings.scale_percent)); } catch (e2) {}
                }
                var offsetX = mmToPt(Number(settings.offset_x_mm || 0));
                var offsetY = mmToPt(Number(settings.offset_y_mm || 0));
                if (offsetX || offsetY) {
                    try { targetItem.translate(offsetX, offsetY); } catch (e3) {}
                }
            }
        }
        if (transforms.outline_text) outlineAllTextFrames(doc, transforms.pathfinder_merge === true);
    }

    function applyOutputSettings(doc, output, variables) {
        var mode = String(output.color_mode || "").toUpperCase();
        try {
            if (mode === "CMYK") app.executeMenuCommand("doc-color-cmyk");
            if (mode === "RGB") app.executeMenuCommand("doc-color-rgb");
        } catch (e1) {}
        if (output.outline_text) {
            applyTransforms(doc, {
                outline_text: true,
                pathfinder_merge: output.pathfinder_merge !== false
            }, variables);
        }
    }

    function outlineAllTextFrames(doc, pathfinderMerge) {
        var frames = [];
        for (var l = 0; l < doc.layers.length; l++) collectTextFrames(doc.layers[l], frames);
        for (var i = frames.length - 1; i >= 0; i--) {
            try {
                var outline = frames[i].createOutline();
                if (pathfinderMerge) cleanupOutline(outline);
            } catch (e1) {}
        }
    }

    function cleanupOutline(item) {
        if (!item) return;
        try { app.executeMenuCommand("deselectall"); } catch (e0) {}
        try {
            item.selected = true;
            app.executeMenuCommand("Live Pathfinder Add");
            app.executeMenuCommand("expandStyle");
            item.selected = false;
        } catch (e1) {
            try { item.selected = false; } catch (e2) {}
        }
    }

    function fitText(frame, widthMm, heightMm) {
        if (widthMm <= 0 || heightMm <= 0) return;
        var maxW = mmToPt(widthMm);
        var maxH = mmToPt(heightMm);
        for (var i = 0; i < 100; i++) {
            var bounds = frame.visibleBounds;
            var width = Math.abs(bounds[2] - bounds[0]);
            var height = Math.abs(bounds[1] - bounds[3]);
            if (width <= maxW && height <= maxH) break;
            var attrs = frame.textRange.characterAttributes;
            var size = Number(attrs.size || 12);
            if (size <= 4) break;
            attrs.size = Math.max(4, size * Math.min(maxW / width, maxH / height) * 0.96);
        }
    }

    function fitTextStrict(frame, widthMm, heightMm, target) {
        if (widthMm <= 0 || heightMm <= 0) throw new Error("Invalid strict text dimensions: " + target);
        var maxW = mmToPt(widthMm);
        var maxH = mmToPt(heightMm);
        for (var i = 0; i < 200; i++) {
            var bounds = frame.visibleBounds;
            var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
            var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
            if (width <= maxW && height <= maxH) return;
            if (!width || !height) break;
            var attrs = frame.textRange.characterAttributes;
            var size = Number(attrs.size || 12);
            if (size <= 0.1) break;
            attrs.size = Math.max(0.1, size * Math.min(maxW / width, maxH / height) * 0.98);
        }
        var finalBounds = frame.visibleBounds;
        var finalWidth = Math.abs(Number(finalBounds[2]) - Number(finalBounds[0]));
        var finalHeight = Math.abs(Number(finalBounds[1]) - Number(finalBounds[3]));
        if (finalWidth > maxW || finalHeight > maxH) {
            throw new Error("Text cannot fit the configured dimension: " + target);
        }
    }

    function fitPageItemToExactBox(item, rect, target) {
        var targetWidth = Number(rect.right) - Number(rect.left);
        var targetHeight = Number(rect.top) - Number(rect.bottom);
        if (targetWidth <= 0 || targetHeight <= 0) throw new Error("Invalid exact text dimensions: " + target);
        for (var index = 0; index < 12; index++) {
            var bounds = measuredBounds(item);
            var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
            var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
            if (!width || !height) throw new Error("Text has no visible bounds for exact box: " + target);
            if (!boxExactFitMatches(width, height, targetWidth, targetHeight)) {
                var horizontalScale = targetWidth / width;
                var verticalScale = targetHeight / height;
                if (
                    !isFinite(horizontalScale) ||
                    !isFinite(verticalScale) ||
                    horizontalScale <= 0 ||
                    verticalScale <= 0
                ) {
                    throw new Error("Invalid exact text scale: " + target);
                }
                resizePageItemToExactBox(item, horizontalScale * 100, verticalScale * 100);
            }
            centerPageItemInExactBox(item, rect);
            if (boxExactFitMatchesSize(item, targetWidth, targetHeight)) {
                validateExactBox(item, rect, target);
                return;
            }
        }
        validateExactBox(item, rect, target);
    }

    function resizePageItemToExactBox(item, horizontalPercent, verticalPercent) {
        try {
            item.resize(horizontalPercent, verticalPercent, true, true, true, true, 100, Transformation.CENTER);
            return;
        } catch (e1) {}
        try {
            item.resize(horizontalPercent, verticalPercent, true, true, true, true, 100);
            return;
        } catch (e2) {}
        try {
            item.resize(horizontalPercent, verticalPercent);
            return;
        } catch (e3) {}
        throw new Error("Cannot independently scale text to exact bounds");
    }

    function centerPageItemInExactBox(item, rect) {
        var bounds = measuredBounds(item);
        var targetCenterX = (Number(rect.left) + Number(rect.right)) / 2;
        var targetCenterY = (Number(rect.top) + Number(rect.bottom)) / 2;
        var ownCenterX = (Number(bounds[0]) + Number(bounds[2])) / 2;
        var ownCenterY = (Number(bounds[1]) + Number(bounds[3])) / 2;
        item.translate(targetCenterX - ownCenterX, targetCenterY - ownCenterY);
    }

    function boxExactFitMatchesSize(item, targetWidth, targetHeight) {
        var bounds = measuredBounds(item);
        return boxExactFitMatches(
            Math.abs(Number(bounds[2]) - Number(bounds[0])),
            Math.abs(Number(bounds[1]) - Number(bounds[3])),
            targetWidth,
            targetHeight
        );
    }

    function boxExactFitMatches(width, height, targetWidth, targetHeight) {
        return (
            Math.abs(targetWidth - width) <= EXACT_BOX_MAX_DELTA_PT &&
            Math.abs(targetHeight - height) <= EXACT_BOX_MAX_DELTA_PT
        );
    }

    function validateExactBox(item, rect, target) {
        var bounds = measuredBounds(item);
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        var targetWidth = Number(rect.right) - Number(rect.left);
        var targetHeight = Number(rect.top) - Number(rect.bottom);
        if (!boxExactFitMatches(width, height, targetWidth, targetHeight)) {
            throw new Error(
                "Text cannot exactly fill the configured dimension: " + target +
                " (actual=" + width + "x" + height + ", target=" + targetWidth + "x" + targetHeight + ")"
            );
        }
        var centerX = (Number(bounds[0]) + Number(bounds[2])) / 2;
        var centerY = (Number(bounds[1]) + Number(bounds[3])) / 2;
        var targetCenterX = (Number(rect.left) + Number(rect.right)) / 2;
        var targetCenterY = (Number(rect.top) + Number(rect.bottom)) / 2;
        if (
            Math.abs(centerX - targetCenterX) > EXACT_BOX_MAX_DELTA_PT ||
            Math.abs(centerY - targetCenterY) > EXACT_BOX_MAX_DELTA_PT
        ) {
            throw new Error("Text cannot center in the configured dimension: " + target);
        }
    }

    function measuredBounds(item) {
        try {
            var visible = item.visibleBounds;
            if (validBounds(visible)) return visible;
        } catch (e1) {}
        try {
            var geometric = item.geometricBounds;
            if (validBounds(geometric)) return geometric;
        } catch (e2) {}
        throw new Error("Cannot measure item bounds");
    }

    function validBounds(bounds) {
        return bounds && bounds.length >= 4 && isFinite(Number(bounds[0])) && isFinite(Number(bounds[1])) && isFinite(Number(bounds[2])) && isFinite(Number(bounds[3]));
    }

    function applyTextColor(frame, name) {
        if (!name) return;
        var rgb = colorValue(name);
        if (!rgb) return;
        var color = new RGBColor();
        color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
        try { frame.textRange.characterAttributes.fillColor = color; } catch (e1) {}
    }

    function applyNameColorCycle(frame, variable) {
        if (String(variable.target || "") !== "Name") return;
        var cycle = variable.name_color_cycle || {};
        var delimiter = String(cycle.delimiter || "");
        var colors = cycle.colors || [];
        if (!delimiter || typeof colors.length !== "number" || colors.length < 2) return;
        var text = String(frame.contents || "");
        if (text.indexOf(delimiter) < 0) return;
        var parts = text.split(delimiter);
        if (parts.length < 2) return;
        var cursor = 0;
        for (var partIndex = 0; partIndex < parts.length; partIndex++) {
            var rgb = hexColor(colors[partIndex % colors.length]);
            var part = parts[partIndex];
            if (rgb) {
                var color = new RGBColor();
                color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
                for (var charIndex = 0; charIndex < part.length; charIndex++) {
                    frame.characters[cursor + charIndex].characterAttributes.fillColor = color;
                }
            }
            cursor += part.length + (partIndex < parts.length - 1 ? delimiter.length : 0);
        }
    }

    function applyRuleActions(frame, actions) {
        for (var actionIndex = 0; actionIndex < actions.length; actionIndex++) {
            var action = actions[actionIndex] || {};
            if (String(action.type || "") === "fill_color") {
                applyFillColorAction(frame, action);
            } else if (String(action.type || "") === "stroke_width") {
                applyFontBoldness(frame, {boldness: action.value});
            } else {
                throw new Error("Unsupported compiled rule action: " + action.type);
            }
        }
    }

    function applyFillColorAction(frame, action) {
        var values = action.values || [];
        if (!values.length) return;
        var selector = action.selector || {};
        if (String(selector.type || "whole") !== "segments") {
            var wholeRgb = hexColor(values[0]);
            if (!wholeRgb) return;
            var wholeColor = new RGBColor();
            wholeColor.red = wholeRgb[0]; wholeColor.green = wholeRgb[1]; wholeColor.blue = wholeRgb[2];
            try { frame.textRange.characterAttributes.fillColor = wholeColor; } catch (e1) {}
            return;
        }
        var delimiter = String(selector.delimiter || "");
        var parts = String(frame.contents || "").split(delimiter);
        if (!delimiter || parts.length < 2) return;
        var cursor = 0;
        for (var partIndex = 0; partIndex < parts.length; partIndex++) {
            var rgb = hexColor(values[partIndex % values.length]);
            if (rgb) {
                var color = new RGBColor();
                color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
                for (var charIndex = 0; charIndex < parts[partIndex].length; charIndex++) {
                    frame.characters[cursor + charIndex].characterAttributes.fillColor = color;
                }
            }
            cursor += parts[partIndex].length + (partIndex < parts.length - 1 ? delimiter.length : 0);
        }
    }

    function applyFontBoldness(frame, style) {
        var boldness = Number(style && style.boldness);
        if (isNaN(boldness) || boldness <= 0) return;
        try {
            var characters = frame.characters;
            for (var index = 0; index < characters.length; index++) {
                applyBoldnessToAttributes(characters[index].characterAttributes, boldness);
            }
            if (characters.length) return;
        } catch (e1) {}
        applyBoldnessToAttributes(frame.textRange.characterAttributes, boldness);
    }

    function applyBoldnessToAttributes(attributes, boldness) {
        if (!attributes) return;
        try { attributes.strokeColor = attributes.fillColor; } catch (e1) {}
        try { attributes.strokeWeight = boldness; } catch (e2) {
            try { attributes.strokeWidth = boldness; } catch (e3) {}
        }
    }

    function hexColor(value) {
        var match = String(value || "").match(/^#([0-9a-f]{6})$/i);
        if (!match) return null;
        var hex = match[1];
        return [
            parseInt(hex.substring(0, 2), 16),
            parseInt(hex.substring(2, 4), 16),
            parseInt(hex.substring(4, 6), 16)
        ];
    }

    function rgbColor(value) {
        var rgb = hexColor(value) || colorValue(value);
        if (!rgb) return null;
        var color = new RGBColor();
        color.red = rgb[0]; color.green = rgb[1]; color.blue = rgb[2];
        return color;
    }

    function colorValue(name) {
        var map = {
            "black": [0, 0, 0], "white": [255, 255, 255], "red": [255, 0, 0],
            "blue": [0, 102, 204], "gold": [212, 175, 55],
            "黑色": [0, 0, 0], "白色": [255, 255, 255], "红色": [255, 0, 0],
            "蓝色": [0, 102, 204], "金色": [212, 175, 55]
        };
        return map[String(name).toLowerCase()] || null;
    }

    function findPageItemByName(doc, name) {
        for (var l = 0; l < doc.layers.length; l++) {
            var found = findInContainer(doc.layers[l], name);
            if (found) return found;
        }
        return null;
    }

    function findPageItemsByName(doc, name) {
        var result = [];
        for (var l = 0; l < doc.layers.length; l++) collectInContainer(doc.layers[l], name, result);
        return result;
    }

    function resolveVariableTargets(doc, variable, allowUnnamedNameFallback) {
        var target = String(variable.target || "");
        var items = findPageItemsByName(doc, target);
        if (items.length) return items;
        if (target === "Name" && allowUnnamedNameFallback) return findFallbackNameTextFrames(doc);
        return items;
    }

    function findFallbackNameTextFrames(doc) {
        var frames = [];
        for (var l = 0; l < doc.layers.length; l++) collectTextFrames(doc.layers[l], frames);
        var candidates = [];
        for (var i = 0; i < frames.length; i++) {
            var frame = frames[i];
            if (hasAncestorNamed(frame, "Font")) continue;
            if (String(frame.name || "").match(/^F\d+$/i)) continue;
            if (trimText(frame.contents).length) continue;
            var area = itemArea(frame);
            if (area <= 1) continue;
            candidates.push({frame: frame, area: area});
        }
        candidates.sort(function (a, b) { return b.area - a.area; });
        return candidates.length ? [candidates[0].frame] : [];
    }

    function collectInContainer(container, name, result) {
        if (!container || !container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.name === name) result.push(item);
            if (item.typename === "GroupItem" || item.typename === "Layer") {
                collectInContainer(item, name, result);
            }
        }
    }

    function collectTextFrames(container, result) {
        if (!container || !container.pageItems) return;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.typename === "TextFrame") result.push(item);
            if (item.typename === "GroupItem" || item.typename === "Layer") {
                collectTextFrames(item, result);
            }
        }
    }

    function findInContainer(container, name) {
        if (!container || !container.pageItems) return null;
        for (var i = 0; i < container.pageItems.length; i++) {
            var item = container.pageItems[i];
            if (item.name === name) return item;
            if (item.typename === "GroupItem" || item.typename === "Layer") {
                var found = findInContainer(item, name);
                if (found) return found;
            }
        }
        return null;
    }

    function hasAncestorNamed(item, name) {
        var current = item ? item.parent : null;
        while (current) {
            if (String(current.name || "") === name) return true;
            if (current.typename === "Document") break;
            current = current.parent;
        }
        return false;
    }

    function itemArea(item) {
        try {
            var bounds = item.visibleBounds;
            return Math.abs(Number(bounds[2]) - Number(bounds[0])) * Math.abs(Number(bounds[1]) - Number(bounds[3]));
        } catch (e1) {
            return 0;
        }
    }

    function trimText(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "");
    }

    function firstTextFrame(item) {
        if (!item) return null;
        if (item.typename === "TextFrame") return item;
        if (!item.pageItems) return null;
        for (var i = 0; i < item.pageItems.length; i++) {
            var found = firstTextFrame(item.pageItems[i]);
            if (found) return found;
        }
        return null;
    }

    function applyLayoutTextStyle(style, target) {
        if (!style) return;
        if (style.fontConfig) {
            applyConfiguredFontStyle(style.fontConfig, target);
            return;
        }
        if (style.typename === "TextFrame") {
            copyTextStyle(style, target);
            return;
        }
    }

    function applyConfiguredFontStyle(config, target) {
        var attributes = target.textRange.characterAttributes;
        try { if (config.tracking !== undefined) attributes.tracking = Number(config.tracking || 0); } catch (e1) {}
        try { if (config.horizontal_scale !== undefined) attributes.horizontalScale = Number(config.horizontal_scale || 100); } catch (e2) {}
        try { if (config.vertical_scale !== undefined) attributes.verticalScale = Number(config.vertical_scale || 100); } catch (e3) {}
        applyFontByName(target, String(config.font_name || config.font_family || ""));
    }

    function applyFontByName(target, fontName) {
        if (!fontName) return;
        try {
            for (var index = 0; index < app.textFonts.length; index++) {
                var font = app.textFonts[index];
                if (font.name === fontName || font.family === fontName) {
                    target.textRange.characterAttributes.textFont = font;
                    return;
                }
            }
        } catch (e1) {}
    }

    function copyTextStyle(source, target) {
        var src = source.textRange.characterAttributes;
        var dst = target.textRange.characterAttributes;
        try { dst.textFont = src.textFont; } catch (e1) {}
        try { dst.size = src.size; } catch (e2) {}
        try { dst.tracking = src.tracking; } catch (e3) {}
        try { dst.horizontalScale = src.horizontalScale; } catch (e4) {}
        try { dst.verticalScale = src.verticalScale; } catch (e5) {}
        try { dst.fillColor = src.fillColor; } catch (e6) {}
        try { target.textRange.paragraphAttributes.justification = source.textRange.paragraphAttributes.justification; } catch (e7) {}
    }

    function centerItem(item, bounds) {
        var own = item.visibleBounds;
        item.translate(
            (Number(bounds[0]) + Number(bounds[2]) - Number(own[0]) - Number(own[2])) / 2,
            (Number(bounds[1]) + Number(bounds[3]) - Number(own[1]) - Number(own[3])) / 2
        );
    }

    function saveAsNativeAI(doc, file, compatibility) {
        var options = new IllustratorSaveOptions();
        var targetCompatibility = String(compatibility || "Illustrator 8").toLowerCase();
        if (targetCompatibility === "cs5") {
            options.compatibility = Compatibility.ILLUSTRATOR15;
        } else if (targetCompatibility !== "ai_standard" && targetCompatibility !== "standard" && targetCompatibility !== "current") {
            options.compatibility = Compatibility.ILLUSTRATOR8;
        }
        options.pdfCompatible = false;
        options.compressed = false;
        doc.saveAs(file, options);
    }

    function exportPng(doc, file, dpi) {
        var opts = new ExportOptionsPNG24();
        var scale = Math.max(1, Number(dpi || 300) / 72 * 100 + 0.02);
        opts.antiAliasing = true;
        opts.artBoardClipping = true;
        opts.transparency = true;
        opts.horizontalScale = scale;
        opts.verticalScale = scale;
        doc.exportFile(file, ExportType.PNG24, opts);
    }

    function ensureFolder(folder) {
        if (!folder.exists) {
            ensureFolder(folder.parent);
            folder.create();
        }
    }

    function trace(task, message) {
        if (!task || !task.trace_file) return;
        var file = File(String(task.trace_file));
        try {
            ensureFolder(file.parent);
            file.encoding = "UTF-8";
            file.open("a");
            file.write(String(new Date().getTime()) + " " + message + "\n");
            file.close();
        } catch (e1) {}
    }

    function writeProgress(task, current, total, stage) {
        var progress = task.progress || {};
        if (!progress.file) return;
        var offset = Number(progress.offset || 0);
        var grandTotal = Number(progress.total || total || 0);
        var file = File(String(progress.file));
        var existing = readProgressFile(file);
        if (existing) {
            var previousTotal = Number(existing.total || 0);
            if (!isNaN(previousTotal) && previousTotal > grandTotal) grandTotal = previousTotal;
        }
        var nextCurrent = Math.min(offset + current, grandTotal);
        if (existing) {
            var previousCurrent = Number(existing.current || 0);
            if (!isNaN(previousCurrent) && previousCurrent > nextCurrent) {
                nextCurrent = grandTotal ? Math.min(previousCurrent, grandTotal) : previousCurrent;
            }
        }
        var payload = {
            current: nextCurrent,
            total: grandTotal,
            stage: String(stage || progress.stage || "")
        };
        try {
            ensureFolder(file.parent);
            file.encoding = "UTF-8";
            file.open("w");
            file.write(progressJson(payload));
            file.close();
        } catch (e1) {}
    }

    function readProgressFile(file) {
        try {
            if (!file.exists) return null;
            file.encoding = "UTF-8";
            if (!file.open("r")) return null;
            var text = file.read();
            file.close();
            if (!text) return null;
            if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
            return eval("(" + text + ")");
        } catch (e1) {
            try { file.close(); } catch (ignored) {}
            return null;
        }
    }

    function progressJson(value) {
        if (value === null) return "null";
        var type = typeof value;
        if (type === "number" || type === "boolean") return String(value);
        if (type === "string") return "\"" + String(value).replace(/\\/g, "\\\\").replace(/"/g, "\\\"").replace(/\r/g, "\\r").replace(/\n/g, "\\n") + "\"";
        var props = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) props.push(progressJson(key) + ":" + progressJson(value[key]));
        }
        return "{" + props.join(",") + "}";
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("Task file not found: " + path);
        file.encoding = "UTF-8";
        file.open("r");
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }

    function mmToPt(value) { return value * 72 / 25.4; }
}());
