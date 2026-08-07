#target illustrator

(function () {
    var SCAN_PROTOCOL_VERSION = "v2-template-scan/1.0";
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    var outputFile = File(String(task.output_json || ""));
    if (!String(task.input_ai || "")) throw new Error("Task missing input_ai");
    if (!String(task.output_json || "")) throw new Error("Task missing output_json");

    var sourceFile = File(String(task.input_ai));
    var doc = null;
    var result = baseResult(task, sourceFile);

    try {
        try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (ignored0) {}
        doc = app.open(sourceFile);
        result.document = documentFacts(doc, sourceFile, task);
        scanDocument(doc, result);
    } catch (error) {
        result.scan_errors.push(scanError("$", "scan_failed", error));
    } finally {
        if (doc) {
            try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (ignored1) {}
        }
    }

    result.status = resultStatus(result);
    result.ok = result.status === "completed";
    writeText(outputFile, toJson(result));
    return result.ok ? "SCAN_V2_TEMPLATE_OK" : "SCAN_V2_TEMPLATE_" + result.status.toUpperCase();

    function scanDocument(document, output) {
        var roots = findNamedGroups(document, "template");
        if (roots.length === 0) {
            addIssue(output, "blocking", "template_missing", "$.template", "未找到唯一 Template 根组。", { fatal: true });
            return;
        }
        if (roots.length > 1) {
            addIssue(output, "blocking", "template_multiple", "$.template", "发现多个 Template 根组，扫描范围不唯一。", {
                fatal: true,
                candidates: pathsOf(roots)
            });
            return;
        }
        scanTemplate(roots[0], output);
    }

    function scanTemplate(root, output) {
        var rootPath = itemPath(root);
        var children = directItems(root);
        var outputs = [];
        var colorsGroups = [];
        var ignoredDirect = 0;

        for (var i = 0; i < children.length; i++) {
            var child = children[i];
            var name = trimName(safeString(child, "name", ""));
            var normalized = normalizeName(name);
            if (safeString(child, "typename", "") === "GroupItem" && normalized === "colors") {
                colorsGroups.push(child);
            } else if (safeString(child, "typename", "") === "GroupItem" && outputKey(name)) {
                outputs.push(child);
            } else {
                ignoredDirect += 1;
                if (name && lowerStartsWith(normalized, "output")) {
                    addIssue(output, "blocking", "invalid_output_name", "$.template.outputs", "Output 组名称必须是 Output_main 或 Output_SideA/B/C。", {
                        layer_path: itemPath(child),
                        name: name
                    });
                }
            }
        }

        output.template = addRelative(objectFacts(root), rootPath);
        output.template.key = "Template";
        output.template.output_count = outputs.length;
        output.template.has_colors = colorsGroups.length > 0;
        output.template.ignored_direct_child_count = ignoredDirect;
        output.items = collectEvidenceItems(root, rootPath);

        if (colorsGroups.length > 1) {
            addIssue(output, "blocking", "colors_multiple", "$.colors", "Template 下只能有一个 Colors 组。", {
                paths: pathsOf(colorsGroups)
            });
        }
        if (colorsGroups.length > 0) output.colors = scanColors(colorsGroups[0], output, rootPath);

        outputs = sortOutputGroups(outputs);
        output.outputs = scanOutputs(outputs, output, rootPath);
        validateOutputKeys(output);
    }

    function scanOutputs(groups, output, rootPath) {
        var records = [];
        if (groups.length === 0) {
            addIssue(output, "blocking", "output_missing", "$.outputs", "Template 下至少需要一个 Output 组。", {});
            return records;
        }
        for (var i = 0; i < groups.length; i++) {
            var group = groups[i];
            var key = outputKey(trimName(safeString(group, "name", "")));
            var record = addRelative(objectFacts(group), rootPath);
            record.key = key;
            record.order = i + 1;
            record.style = scanSection(group, "style", output, rootPath);
            record.styles = record.style ? record.style.options : [];
            record.design = scanOptionSection(group, "design", output, rootPath);
            record.designs = record.design ? record.design.options : [];
            record.font = scanOptionSection(group, "font", output, rootPath);
            record.fonts = record.font ? record.font.options : [];
            record.summary = {
                styles: record.styles.length,
                designs: record.designs.length,
                fonts: record.fonts.length,
                slots: countNested(record.designs, "slots") + countNested(record.fonts, "slots"),
                anchors: countNested(record.designs, "anchors") + countNested(record.fonts, "anchors"),
                tails: countNested(record.designs, "tails") + countNested(record.fonts, "tails"),
                assets: countNested(record.designs, "assets") + countNested(record.fonts, "assets"),
                fixed_objects: sumFixed(record.designs) + sumFixed(record.fonts)
            };
            records.push(record);
        }
        return records;
    }

    function scanSection(outputGroup, sectionName, output, rootPath) {
        var groups = directGroupsByName(outputGroup, sectionName);
        if (groups.length === 0) return null;
        if (groups.length > 1) {
            addIssue(output, "blocking", sectionName + "_multiple", "$.outputs", canonicalName(sectionName) + " 容器在同一 Output 下重复。", {
                paths: pathsOf(groups)
            });
        }
        var group = groups[0];
        var record = addRelative(objectFacts(group), rootPath);
        record.key = canonicalName(sectionName);
        record.options = scanStyleOptions(group, output, rootPath);
        return record;
    }

    function scanOptionSection(outputGroup, sectionName, output, rootPath) {
        var groups = directGroupsByName(outputGroup, sectionName);
        if (groups.length === 0) return null;
        if (groups.length > 1) {
            addIssue(output, "blocking", sectionName + "_multiple", "$.outputs", canonicalName(sectionName) + " 容器在同一 Output 下重复。", {
                paths: pathsOf(groups)
            });
        }
        var group = groups[0];
        var record = addRelative(objectFacts(group), rootPath);
        record.key = canonicalName(sectionName);
        record.options = scanOptions(group, sectionName, output, rootPath);
        return record;
    }

    function scanStyleOptions(styleGroup, output, rootPath) {
        var children = directItems(styleGroup);
        var options = [];
        var seen = {};
        for (var i = 0; i < children.length; i++) {
            var item = children[i];
            var key = trimName(safeString(item, "name", ""));
            if (!key) {
                addIssue(output, "warning", "style_unnamed", "$.outputs.style.options", "Style 下存在未命名尺寸对象，已忽略。", { layer_path: itemPath(item) });
                continue;
            }
            rememberUnique(output, seen, key, "$.outputs.style.options", "style_duplicate", "同一 Style 容器下存在重名尺寸对象。", item);
            var record = addRelative(objectFacts(item), rootPath);
            record.key = key;
            record.dimensions = dimensionsFromBounds(record.visible_bounds);
            record.closed_dimension_box = isClosedDimensionBox(item);
            if (!record.dimensions || !record.dimensions.width_pt || !record.dimensions.height_pt) {
                addIssue(output, "blocking", "style_unmeasurable", "$.outputs.style.options", "Style 尺寸对象无法读取有效可见边界。", { layer_path: record.layer_path, key: key });
            }
            options.push(record);
        }
        return sortRecords(options);
    }

    function scanOptions(sectionGroup, sectionName, output, rootPath) {
        var children = directItems(sectionGroup);
        var options = [];
        var seen = {};
        for (var i = 0; i < children.length; i++) {
            var item = children[i];
            if (safeString(item, "typename", "") !== "GroupItem") {
                addIssue(output, "warning", sectionName + "_option_not_group", "$.outputs." + sectionName + ".options", canonicalName(sectionName) + " 选项必须是编组，非编组对象已按固定内容忽略。", {
                    layer_path: itemPath(item)
                });
                continue;
            }
            var key = trimName(safeString(item, "name", ""));
            if (!key) {
                addIssue(output, "blocking", sectionName + "_option_unnamed", "$.outputs." + sectionName + ".options", canonicalName(sectionName) + " 选项组必须命名。", {
                    layer_path: itemPath(item)
                });
            }
            rememberUnique(output, seen, key, "$.outputs." + sectionName + ".options", sectionName + "_option_duplicate", "同一 " + canonicalName(sectionName) + " 容器下存在重名选项。", item);
            var option = addRelative(objectFacts(item), rootPath);
            option.key = key;
            option.kind = sectionName;
            option.slots = [];
            option.anchors = [];
            option.tails = [];
            option.assets = [];
            option.fixed_object_count = 0;
            option.fixed_object_type_counts = {};
            option.font_dependencies = [];
            scanOptionTree(item, option, output, rootPath);
            option.slots = sortRecords(option.slots);
            option.anchors = sortRecords(option.anchors);
            option.tails = sortRecords(option.tails);
            option.assets = sortRecords(option.assets);
            option.font_dependencies = uniqueSorted(option.font_dependencies);
            validateOptionMarkers(option, output);
            options.push(option);
        }
        return sortRecords(options);
    }

    function scanOptionTree(optionGroup, option, output, rootPath) {
        var children = directItems(optionGroup);
        for (var i = 0; i < children.length; i++) scanOptionItem(children[i], option, output, rootPath);
    }

    function scanOptionItem(item, option, output, rootPath) {
        var name = trimName(safeString(item, "name", ""));
        var normalized = normalizeName(name);
        if (safeString(item, "typename", "") === "GroupItem" && normalized === "assets") {
            option.assets = option.assets.concat(scanAssets(item, option, output, rootPath));
            return;
        }
        if (lowerStartsWith(normalized, "slot_")) {
            var slot = markerRecord(item, "slot", rootPath);
            option.slots.push(slot);
            pushFonts(option.font_dependencies, slot.font);
            return;
        }
        if (lowerStartsWith(normalized, "anchor_")) {
            option.anchors.push(markerRecord(item, "anchor", rootPath));
            return;
        }
        if (lowerStartsWith(normalized, "tail_")) {
            option.tails.push(tailRecord(item, rootPath));
            return;
        }
        if (hasManagedDescendant(item)) {
            var nested = directItems(item);
            for (var i = 0; i < nested.length; i++) scanOptionItem(nested[i], option, output, rootPath);
            return;
        }
        option.fixed_object_count += 1;
        increment(option.fixed_object_type_counts, safeString(item, "typename", "Unknown"));
    }

    function scanAssets(assetsGroup, option, output, rootPath) {
        var groups = directItems(assetsGroup);
        var assets = [];
        var seen = {};
        for (var i = 0; i < groups.length; i++) {
            var library = groups[i];
            if (safeString(library, "typename", "") !== "GroupItem") {
                addIssue(output, "blocking", "asset_library_not_group", "$.outputs." + option.kind + ".options.assets", "Assets 的直属子项必须是素材库编组。", {
                    layer_path: itemPath(library)
                });
                continue;
            }
            var key = trimName(safeString(library, "name", ""));
            rememberUnique(output, seen, key, "$.outputs." + option.kind + ".options.assets", "asset_key_duplicate", "同一 Assets 下存在重复素材库键。", library);
            var record = addRelative(objectFacts(library), rootPath);
            record.asset_key = key;
            record.key = key;
            record.slot_key = key ? "slot_" + key : "";
            record.values = scanAssetValues(library, output, rootPath);
            record.supported_values = namesOf(record.values);
            assets.push(record);
        }
        return sortRecords(assets);
    }

    function scanAssetValues(library, output, rootPath) {
        var children = directItems(library);
        var values = [];
        var seen = {};
        for (var i = 0; i < children.length; i++) {
            var item = children[i];
            var key = trimName(safeString(item, "name", ""));
            rememberUnique(output, seen, key, "$.outputs.assets.values", "asset_value_duplicate", "同一素材库下存在重复素材值。", item);
            var record = addRelative(objectFacts(item), rootPath);
            record.key = key;
            record.fixed_object_count = countVisualUnits(item);
            values.push(record);
        }
        return sortRecords(values);
    }

    function scanColors(colorsGroup, output, rootPath) {
        var children = directItems(colorsGroup);
        var records = [];
        var seen = {};
        for (var i = 0; i < children.length; i++) {
            var item = children[i];
            var key = trimName(safeString(item, "name", ""));
            rememberUnique(output, seen, key, "$.colors", "color_duplicate", "Colors 下存在重复色块名称。", item);
            var record = addRelative(objectFacts(item), rootPath);
            record.key = key;
            record.color_samples = collectFillColors(item);
            record.fill_color = record.color_samples.length ? record.color_samples[0] : null;
            if (record.color_samples.length > 1) {
                addIssue(output, "blocking", "color_inconsistent", "$.colors", "同一个 Colors 色块内存在多个不同填充色。", { layer_path: record.layer_path, key: key });
            }
            if (record.fill_color && record.fill_color.unsupported) {
                addIssue(output, "blocking", "color_unsupported", "$.colors", "Colors 色块使用了暂不支持的渐变、图案或未知填充。", { layer_path: record.layer_path, key: key, color_type: record.fill_color.type });
            }
            records.push(record);
        }
        return sortRecords(records);
    }

    function markerRecord(item, kind, rootPath) {
        var record = addRelative(objectFacts(item), rootPath);
        record.key = trimName(safeString(item, "name", ""));
        record.marker_kind = kind;
        record.text = textFacts(item);
        record.font = record.text ? record.text.font : null;
        if (kind === "anchor") record.related_slot = relatedSlot(record.key, "anchor_");
        if (kind === "slot") record.asset_key = assetKeyFromSlot(record.key);
        return record;
    }

    function tailRecord(item, rootPath) {
        var record = markerRecord(item, "tail", rootPath);
        var info = tailInfo(record.key);
        record.related_slot = info.slot_key;
        record.position = info.position;
        record.sample = info.sample;
        return record;
    }

    function validateOptionMarkers(option, output) {
        duplicateMarkerIssues(option.slots, option, output, "slot");
        duplicateMarkerIssues(option.anchors, option, output, "anchor");
        duplicateMarkerIssues(option.tails, option, output, "tail");
        var slotKeys = mapKeys(option.slots);
        for (var i = 0; i < option.anchors.length; i++) {
            if (option.anchors[i].related_slot && !slotKeys[normalizeName(option.anchors[i].related_slot)]) {
                addIssue(output, "blocking", "anchor_without_slot", "$.outputs." + option.kind + ".options.anchors", "定位框没有找到对应 slot。", {
                    layer_path: option.anchors[i].layer_path,
                    anchor: option.anchors[i].key,
                    expected_slot: option.anchors[i].related_slot
                });
            }
        }
        for (var t = 0; t < option.tails.length; t++) {
            if (option.tails[t].related_slot && !slotKeys[normalizeName(option.tails[t].related_slot)]) {
                addIssue(output, "blocking", "tail_without_slot", "$.outputs." + option.kind + ".options.tails", "尾巴样本没有找到对应 slot。", {
                    layer_path: option.tails[t].layer_path,
                    tail: option.tails[t].key,
                    expected_slot: option.tails[t].related_slot
                });
            }
        }
        for (var a = 0; a < option.assets.length; a++) {
            if (option.assets[a].slot_key && !slotKeys[normalizeName(option.assets[a].slot_key)]) {
                addIssue(output, "blocking", "asset_without_slot", "$.outputs." + option.kind + ".options.assets", "素材库没有找到对应 slot_<asset_key>。", {
                    layer_path: option.assets[a].layer_path,
                    asset_key: option.assets[a].asset_key,
                    expected_slot: option.assets[a].slot_key
                });
            }
        }
    }

    function validateOutputKeys(output) {
        var records = output.outputs || [];
        var seen = {};
        for (var i = 0; i < records.length; i++) {
            rememberNameIssue(output, seen, records[i].key, "$.outputs", "output_duplicate", "Template 下存在重复 Output。", records[i].layer_path);
        }
        if (records.length === 1 && records[0].key !== "Output_main") {
            addIssue(output, "blocking", "single_output_not_main", "$.outputs[0].key", "单效果图模板必须使用 Output_main。", { key: records[0].key, layer_path: records[0].layer_path });
        }
        var hasMain = false;
        var sideLetters = [];
        for (var r = 0; r < records.length; r++) {
            if (records[r].key === "Output_main") hasMain = true;
            var match = records[r].key.match(/^Output_Side([A-Z])$/);
            if (match) sideLetters.push(match[1]);
        }
        if (records.length > 1 && hasMain) addIssue(output, "blocking", "mixed_output_mode", "$.outputs", "多效果图模板不得混用 Output_main 和 Output_Side*。", {});
        sideLetters.sort();
        for (var s = 0; s < sideLetters.length; s++) {
            var expected = String.fromCharCode(65 + s);
            if (sideLetters[s] !== expected) {
                addIssue(output, "blocking", "output_side_not_continuous", "$.outputs", "多面 Output 必须从 SideA 开始连续排列。", { expected: expected, actual: sideLetters[s] });
                break;
            }
        }
    }

    function objectFacts(item) {
        var type = safeString(item, "typename", "Unknown");
        var bounds = boundsArray(item);
        var record = {
            name: trimName(safeString(item, "name", "")),
            normalized_name: normalizeName(safeString(item, "name", "")),
            object_type: type,
            layer_path: itemPath(item),
            visible_bounds: bounds,
            dimensions: dimensionsFromBounds(bounds),
            hidden: safeBoolean(item, "hidden", false),
            locked: safeBoolean(item, "locked", false),
            opacity: safeNumber(item, "opacity", 100),
            child_count: directItems(item).length
        };
        if (type === "TextFrame") {
            var text = textFacts(item);
            record.text = text ? text.text : "";
            record.text_kind = text ? text.text_kind : "";
            record.font = text ? text.font : null;
            record.fill_color = text ? text.fill_color : null;
        } else {
            record.fill_color = directFillColor(item);
        }
        if (type === "PathItem") {
            record.closed = safeBoolean(item, "closed", false);
            record.path_point_count = safePathPointCount(item);
            record.filled = safeBoolean(item, "filled", false);
            record.stroked = safeBoolean(item, "stroked", false);
            record.closed_dimension_box = isClosedDimensionBox(item);
        }
        return record;
    }

    function textFacts(item) {
        var textFrame = firstTextFrame(item);
        if (!textFrame) return null;
        var record = {
            text: safeString(textFrame, "contents", ""),
            text_kind: textKind(textFrame),
            font: null,
            fill_color: null
        };
        try {
            var attr = textFrame.textRange.characterAttributes;
            var font = attr.textFont;
            record.font = {
                name: font ? String(font.name || "") : "",
                family: font ? String(font.family || "") : "",
                style: font ? String(font.style || "") : "",
                size_pt: numberOr(attr.size, null),
                tracking: numberOr(attr.tracking, null),
                horizontal_scale: numberOr(attr.horizontalScale, null),
                vertical_scale: numberOr(attr.verticalScale, null)
            };
            record.fill_color = colorValue(attr.fillColor);
        } catch (ignored0) {}
        return record;
    }

    function firstTextFrame(item) {
        if (!item) return null;
        if (safeString(item, "typename", "") === "TextFrame") return item;
        var children = directItems(item);
        for (var i = 0; i < children.length; i++) {
            var found = firstTextFrame(children[i]);
            if (found) return found;
        }
        return null;
    }

    function textKind(item) {
        try {
            if (typeof TextType !== "undefined") {
                if (item.kind === TextType.POINTTEXT) return "point_text";
                if (item.kind === TextType.AREATEXT) return "area_text";
                if (item.kind === TextType.PATHTEXT) return "path_text";
            }
        } catch (ignored0) {}
        var raw = "";
        try { raw = String(item.kind || ""); } catch (ignored1) {}
        var lower = raw.toLowerCase();
        if (lower.indexOf("point") >= 0) return "point_text";
        if (lower.indexOf("area") >= 0) return "area_text";
        if (lower.indexOf("path") >= 0) return "path_text";
        return raw || "unknown_text";
    }

    function directFillColor(item) {
        try {
            if (safeString(item, "typename", "") === "PathItem" && item.filled) return colorValue(item.fillColor);
            if (safeString(item, "typename", "") === "CompoundPathItem" && item.pathItems && item.pathItems.length) return directFillColor(item.pathItems[0]);
        } catch (ignored0) {}
        return null;
    }

    function collectFillColors(item) {
        var result = [];
        collectFillColorsInto(item, result, {});
        return result;
    }

    function collectFillColorsInto(item, output, seen) {
        var color = directFillColor(item);
        if (!color && safeString(item, "typename", "") === "TextFrame") {
            var text = textFacts(item);
            color = text ? text.fill_color : null;
        }
        if (color) {
            var key = toJson(color);
            if (!seen[key]) {
                seen[key] = true;
                output.push(color);
            }
        }
        var children = directItems(item);
        for (var i = 0; i < children.length; i++) collectFillColorsInto(children[i], output, seen);
    }

    function colorValue(color) {
        if (!color) return null;
        var type = safeString(color, "typename", "Unknown");
        var value = { type: type, space: type };
        try {
            if (type === "RGBColor") {
                value.space = "RGB";
                value.value = [Number(color.red), Number(color.green), Number(color.blue)];
                value.hex = rgbHex(value.value);
            } else if (type === "CMYKColor") {
                value.space = "CMYK";
                value.value = [Number(color.cyan), Number(color.magenta), Number(color.yellow), Number(color.black)];
            } else if (type === "GrayColor") {
                value.space = "Gray";
                value.value = [Number(color.gray)];
            } else if (type === "SpotColor") {
                value.space = "Spot";
                value.spot = safeString(color.spot, "name", "");
                value.tint = Number(color.tint);
            } else if (type === "NoColor") {
                value.space = "None";
                value.value = [];
            } else {
                value.unsupported = true;
            }
        } catch (ignored0) {
            value.unsupported = true;
        }
        return value;
    }

    function documentFacts(document, file, task) {
        return {
            source_ai: file.fsName,
            name: safeString(document, "name", ""),
            color_space: safeString(document, "documentColorSpace", ""),
            width_pt: numberOr(document.width, 0),
            height_pt: numberOr(document.height, 0),
            artboard_count: safeCollectionLength(document.artboards),
            page_item_count: safeCollectionLength(document.pageItems),
            template_sha256: String(task.input_sha256 || task.template_sha256 || "")
        };
    }

    function baseResult(task, file) {
        return {
            ok: false,
            status: "pending",
            scan_protocol_version: SCAN_PROTOCOL_VERSION,
            scanned_at: utcTimestamp(),
            illustrator_version: safeAppVersion(),
            document: {
                source_ai: file.fsName,
                name: "",
                color_space: "",
                width_pt: 0,
                height_pt: 0,
                artboard_count: 0,
                page_item_count: 0,
                template_sha256: String(task.input_sha256 || task.template_sha256 || "")
            },
            template: null,
            items: [],
            outputs: [],
            colors: [],
            issues: [],
            scan_errors: []
        };
    }

    function resultStatus(result) {
        if (result.scan_errors.length) return "failed";
        for (var i = 0; i < result.issues.length; i++) {
            if (result.issues[i].severity === "blocking") return "blocked";
        }
        return "completed";
    }

    function addIssue(result, severity, code, path, message, details) {
        result.issues.push({
            severity: severity,
            code: code,
            path: path,
            message: message,
            details: details || {}
        });
    }

    function scanError(path, code, error) {
        return {
            path: path,
            code: code,
            message: friendlyScanError(code),
            technical_message: errorText(error),
            line: safeString(error, "line", ""),
            number: safeString(error, "number", "")
        };
    }

    function friendlyScanError(code) {
        if (code === "scan_failed") return "本地 Illustrator 扫描失败，请关闭占用中的窗口后重试；若仍失败，请检查模板是否可以正常打开。";
        return "本地 Illustrator 扫描失败，请检查模板后重试。";
    }

    function collectEvidenceItems(root, rootPath) {
        var records = [];
        collectEvidenceItem(root, rootPath, records);
        return sortRecords(records);
    }

    function collectEvidenceItem(item, rootPath, records) {
        if (shouldEmitEvidenceItem(item)) records.push(addRelative(objectFacts(item), rootPath));
        var children = directItems(item);
        for (var i = 0; i < children.length; i++) collectEvidenceItem(children[i], rootPath, records);
    }

    function shouldEmitEvidenceItem(item) {
        var name = trimName(safeString(item, "name", ""));
        var normalized = normalizeName(name);
        if (normalized === "template" || normalized === "style" || normalized === "design" || normalized === "font" || normalized === "colors" || normalized === "assets") return true;
        if (outputKey(name) || lowerStartsWith(normalized, "slot_") || lowerStartsWith(normalized, "anchor_") || lowerStartsWith(normalized, "tail_")) return true;
        var parentName = parentNormalizedName(item);
        return !!name && (parentName === "style" || parentName === "design" || parentName === "font" || parentName === "assets");
    }

    function parentNormalizedName(item) {
        try { return normalizeName(safeString(item.parent, "name", "")); } catch (ignored0) {}
        return "";
    }

    function duplicateMarkerIssues(items, option, output, kind) {
        var seen = {};
        for (var i = 0; i < items.length; i++) {
            rememberNameIssue(output, seen, items[i].key, "$.outputs." + option.kind + ".options." + kind + "s", kind + "_duplicate", "同一选项内存在重复 " + kind + " 名称。", items[i].layer_path);
        }
    }

    function rememberUnique(result, seen, name, path, code, message, item) {
        rememberNameIssue(result, seen, name, path, code, message, itemPath(item));
    }

    function rememberNameIssue(result, seen, name, path, code, message, layerPath) {
        var normalized = normalizeName(name);
        if (!normalized) return;
        if (!seen[normalized]) {
            seen[normalized] = [layerPath];
            return;
        }
        seen[normalized].push(layerPath);
        addIssue(result, "blocking", code, path, message, { name: name, paths: seen[normalized] });
    }

    function findNamedGroups(document, normalizedName) {
        var groups = [];
        try {
            for (var i = 0; i < document.groupItems.length; i++) {
                var item = document.groupItems[i];
                if (normalizeName(safeString(item, "name", "")) === normalizedName) groups.push(item);
            }
        } catch (error) {
            groups.push();
        }
        return sortGroupsByPath(groups);
    }

    function directGroupsByName(parent, name) {
        var normalized = normalizeName(name);
        var result = [];
        var children = directItems(parent);
        for (var i = 0; i < children.length; i++) {
            if (safeString(children[i], "typename", "") === "GroupItem" && normalizeName(safeString(children[i], "name", "")) === normalized) {
                result.push(children[i]);
            }
        }
        return sortGroupsByPath(result);
    }

    function directItems(parent) {
        var items = [];
        try {
            if (!parent || !parent.pageItems) return items;
            for (var i = 0; i < parent.pageItems.length; i++) {
                var item = parent.pageItems[i];
                try {
                    if (item.parent === parent || item.parent == parent) items.push(item);
                } catch (ignored0) {}
            }
        } catch (ignored1) {}
        return sortItems(items);
    }

    function hasManagedDescendant(item) {
        var children = directItems(item);
        for (var i = 0; i < children.length; i++) {
            var name = normalizeName(safeString(children[i], "name", ""));
            if (name === "assets" || lowerStartsWith(name, "slot_") || lowerStartsWith(name, "anchor_") || lowerStartsWith(name, "tail_")) return true;
            if (hasManagedDescendant(children[i])) return true;
        }
        return false;
    }

    function countVisualUnits(item) {
        var children = directItems(item);
        if (!children.length) return 1;
        var total = 0;
        for (var i = 0; i < children.length; i++) total += countVisualUnits(children[i]);
        return total;
    }

    function itemPath(item) {
        var segments = [];
        var current = item;
        var guard = 0;
        while (current && guard < 100) {
            guard += 1;
            var type = safeString(current, "typename", "");
            if (type === "Document") break;
            var name = trimName(safeString(current, "name", ""));
            if (!name) name = type || "Item";
            segments.push(name);
            try { current = current.parent; } catch (ignored0) { break; }
        }
        segments.reverse();
        return segments.join("/");
    }

    function addRelative(record, rootPath) {
        if (record.layer_path === rootPath) record.template_path = "Template";
        else if (record.layer_path.indexOf(rootPath + "/") === 0) record.template_path = "Template/" + record.layer_path.substring(rootPath.length + 1);
        else record.template_path = record.layer_path;
        return record;
    }

    function boundsArray(item) {
        try {
            var b = item.visibleBounds;
            return [Number(b[0]), Number(b[1]), Number(b[2]), Number(b[3])];
        } catch (ignored0) {
            return null;
        }
    }

    function dimensionsFromBounds(bounds) {
        if (!bounds || bounds.length !== 4) return null;
        var width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
        var height = Math.abs(Number(bounds[1]) - Number(bounds[3]));
        return {
            width_pt: width,
            height_pt: height,
            width_mm: width * 25.4 / 72,
            height_mm: height * 25.4 / 72
        };
    }

    function isClosedDimensionBox(item) {
        if (safeString(item, "typename", "") !== "PathItem") return false;
        return safeBoolean(item, "closed", false) && !!boundsArray(item);
    }

    function outputKey(name) {
        var trimmed = trimName(name);
        var lower = normalizeName(trimmed);
        if (lower === "output_main") return "Output_main";
        var match = lower.match(/^output_side([a-z])$/);
        if (match) return "Output_Side" + match[1].toUpperCase();
        return "";
    }

    function sortOutputGroups(groups) {
        return groups.sort(function (a, b) {
            return compareText(outputSortKey(a), outputSortKey(b));
        });
    }

    function outputSortKey(item) {
        var key = outputKey(trimName(safeString(item, "name", "")));
        if (key === "Output_main") return "00";
        var match = key.match(/^Output_Side([A-Z])$/);
        return match ? "10_" + match[1] : "99_" + key;
    }

    function sortGroupsByPath(groups) {
        return groups.sort(function (a, b) { return compareText(itemPath(a), itemPath(b)); });
    }

    function sortItems(items) {
        return items.sort(function (a, b) {
            var left = normalizeName(safeString(a, "name", "")) + "|" + safeString(a, "typename", "") + "|" + itemPath(a);
            var right = normalizeName(safeString(b, "name", "")) + "|" + safeString(b, "typename", "") + "|" + itemPath(b);
            return compareText(left, right);
        });
    }

    function sortRecords(records) {
        return records.sort(function (a, b) {
            return compareText(String(a.key || a.name || "") + "|" + String(a.layer_path || ""), String(b.key || b.name || "") + "|" + String(b.layer_path || ""));
        });
    }

    function pathsOf(items) {
        var paths = [];
        for (var i = 0; i < items.length; i++) paths.push(itemPath(items[i]));
        paths.sort();
        return paths;
    }

    function namesOf(items) {
        var names = [];
        for (var i = 0; i < items.length; i++) names.push(String(items[i].key || items[i].name || ""));
        names.sort();
        return names;
    }

    function mapKeys(items) {
        var result = {};
        for (var i = 0; i < items.length; i++) result[normalizeName(items[i].key)] = true;
        return result;
    }

    function countNested(items, key) {
        var total = 0;
        for (var i = 0; i < items.length; i++) total += items[i][key] ? items[i][key].length : 0;
        return total;
    }

    function sumFixed(items) {
        var total = 0;
        for (var i = 0; i < items.length; i++) total += Number(items[i].fixed_object_count || 0);
        return total;
    }

    function pushFonts(target, font) {
        if (!font) return;
        if (font.name) target.push(font.name);
        else if (font.family) target.push(font.family);
    }

    function uniqueSorted(values) {
        var seen = {};
        var result = [];
        for (var i = 0; i < values.length; i++) {
            var value = String(values[i] || "");
            if (value && !seen[value]) {
                seen[value] = true;
                result.push(value);
            }
        }
        result.sort();
        return result;
    }

    function relatedSlot(key, prefix) {
        var normalizedPrefix = normalizeName(prefix);
        var normalizedKey = normalizeName(key);
        if (!lowerStartsWith(normalizedKey, normalizedPrefix)) return "";
        return "slot_" + key.substring(prefix.length);
    }

    function assetKeyFromSlot(key) {
        return lowerStartsWith(normalizeName(key), "slot_") ? key.substring(5) : "";
    }

    function tailInfo(key) {
        var body = key.substring(5);
        var lower = body.toLowerCase();
        var pos = lower.indexOf("_first_");
        var position = "";
        if (pos < 0) {
            pos = lower.indexOf("_last_");
            if (pos >= 0) position = "last";
        } else {
            position = "first";
        }
        if (pos < 0) return { slot_key: "slot_" + body, position: "", sample: "" };
        var separator = position === "first" ? "_first_" : "_last_";
        return {
            slot_key: "slot_" + body.substring(0, pos),
            position: position,
            sample: body.substring(pos + separator.length)
        };
    }

    function increment(map, key) {
        map[key] = Number(map[key] || 0) + 1;
    }

    function canonicalName(name) {
        var normalized = normalizeName(name);
        if (normalized === "style") return "Style";
        if (normalized === "design") return "Design";
        if (normalized === "font") return "Font";
        if (normalized === "colors") return "Colors";
        return name;
    }

    function trimName(value) {
        return String(value || "").replace(/^\s+/, "").replace(/\s+$/, "");
    }

    function normalizeName(value) {
        return trimName(value).toLowerCase();
    }

    function lowerStartsWith(value, prefix) {
        return String(value || "").indexOf(prefix) === 0;
    }

    function compareText(a, b) {
        a = String(a || "");
        b = String(b || "");
        if (a < b) return -1;
        if (a > b) return 1;
        return 0;
    }

    function numberOr(value, fallback) {
        var number = Number(value);
        return isNaN(number) ? fallback : number;
    }

    function safeString(item, property, fallback) {
        try {
            if (!item) return fallback || "";
            var value = item[property];
            if (value === null || value === undefined) return fallback || "";
            return String(value);
        } catch (ignored0) {
            return fallback || "";
        }
    }

    function safeNumber(item, property, fallback) {
        try { return numberOr(item[property], fallback); } catch (ignored0) { return fallback; }
    }

    function safeBoolean(item, property, fallback) {
        try {
            var value = item[property];
            return value === true || value === false ? value : fallback;
        } catch (ignored0) {
            return fallback;
        }
    }

    function safePathPointCount(item) {
        try { return item.pathPoints ? item.pathPoints.length : 0; } catch (ignored0) { return 0; }
    }

    function safeCollectionLength(collection) {
        try { return collection ? collection.length : 0; } catch (ignored0) { return 0; }
    }

    function safeAppVersion() {
        try { return String(app.version || ""); } catch (ignored0) { return ""; }
    }

    function errorText(error) {
        try { if (error && error.message) return String(error.message); } catch (ignored0) {}
        try { return String(error); } catch (ignored1) {}
        return "Unknown Illustrator error";
    }

    function utcTimestamp() {
        var date = new Date();
        return date.getUTCFullYear() + "-" + pad2(date.getUTCMonth() + 1) + "-" + pad2(date.getUTCDate()) +
            "T" + pad2(date.getUTCHours()) + ":" + pad2(date.getUTCMinutes()) + ":" + pad2(date.getUTCSeconds()) + "Z";
    }

    function pad2(value) {
        return value < 10 ? "0" + value : String(value);
    }

    function rgbHex(values) {
        return "#" + hex2(values[0]) + hex2(values[1]) + hex2(values[2]);
    }

    function hex2(value) {
        var number = Math.max(0, Math.min(255, Math.round(Number(value || 0))));
        var text = number.toString(16).toUpperCase();
        return text.length === 1 ? "0" + text : text;
    }

    function hex4(value) {
        var text = Number(value || 0).toString(16).toUpperCase();
        while (text.length < 4) text = "0" + text;
        return text;
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

    function writeText(file, text) {
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write output: " + file.fsName);
        file.write(text);
        file.close();
    }

    function ensureFolder(folder) {
        if (!folder || folder.exists) return;
        ensureFolder(folder.parent);
        folder.create();
    }

    function parseJson(text) {
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        var index = 0;
        function fail(message) { throw new Error("Invalid JSON: " + message + " at " + index); }
        function peek() { return text.charAt(index); }
        function next() { return text.charAt(index++); }
        function skipWs() { while (/[\s]/.test(peek())) index += 1; }
        function parseValue() {
            skipWs();
            var ch = peek();
            if (ch === "{") return parseObject();
            if (ch === "[") return parseArray();
            if (ch === "\"") return parseString();
            if (ch === "-" || (ch >= "0" && ch <= "9")) return parseNumber();
            if (text.substring(index, index + 4) === "true") { index += 4; return true; }
            if (text.substring(index, index + 5) === "false") { index += 5; return false; }
            if (text.substring(index, index + 4) === "null") { index += 4; return null; }
            fail("unexpected token");
        }
        function parseObject() {
            var result = {};
            next();
            skipWs();
            if (peek() === "}") { next(); return result; }
            while (true) {
                skipWs();
                if (peek() !== "\"") fail("object key must be string");
                var key = parseString();
                skipWs();
                if (next() !== ":") fail("missing ':'");
                result[key] = parseValue();
                skipWs();
                var ch = next();
                if (ch === "}") break;
                if (ch !== ",") fail("missing ','");
            }
            return result;
        }
        function parseArray() {
            var result = [];
            next();
            skipWs();
            if (peek() === "]") { next(); return result; }
            while (true) {
                result.push(parseValue());
                skipWs();
                var ch = next();
                if (ch === "]") break;
                if (ch !== ",") fail("missing ','");
            }
            return result;
        }
        function parseString() {
            var result = "";
            if (next() !== "\"") fail("string must start with quote");
            while (index < text.length) {
                var ch = next();
                if (ch === "\"") return result;
                if (ch === "\\") {
                    var esc = next();
                    if (esc === "\"" || esc === "\\" || esc === "/") result += esc;
                    else if (esc === "b") result += "\b";
                    else if (esc === "f") result += "\f";
                    else if (esc === "n") result += "\n";
                    else if (esc === "r") result += "\r";
                    else if (esc === "t") result += "\t";
                    else if (esc === "u") {
                        var hex = text.substring(index, index + 4);
                        if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("bad unicode escape");
                        result += String.fromCharCode(parseInt(hex, 16));
                        index += 4;
                    } else {
                        fail("bad escape");
                    }
                } else {
                    result += ch;
                }
            }
            fail("unterminated string");
        }
        function parseNumber() {
            var start = index;
            if (peek() === "-") index += 1;
            if (peek() === "0") index += 1;
            else {
                if (!(peek() >= "1" && peek() <= "9")) fail("bad number");
                while (peek() >= "0" && peek() <= "9") index += 1;
            }
            if (peek() === ".") {
                index += 1;
                if (!(peek() >= "0" && peek() <= "9")) fail("bad decimal");
                while (peek() >= "0" && peek() <= "9") index += 1;
            }
            if (peek() === "e" || peek() === "E") {
                index += 1;
                if (peek() === "+" || peek() === "-") index += 1;
                if (!(peek() >= "0" && peek() <= "9")) fail("bad exponent");
                while (peek() >= "0" && peek() <= "9") index += 1;
            }
            return Number(text.substring(start, index));
        }
        var value = parseValue();
        skipWs();
        if (index !== text.length) fail("trailing characters");
        return value;
    }

    function toJson(value) {
        if (value === null || value === undefined) return "null";
        var type = typeof value;
        if (type === "number") return isNaN(value) || !isFinite(value) ? "null" : String(value);
        if (type === "boolean") return value ? "true" : "false";
        if (type === "string") return quote(value);
        if (value instanceof Array) {
            var items = [];
            for (var i = 0; i < value.length; i++) items.push(toJson(value[i]));
            return "[" + items.join(",") + "]";
        }
        var keys = [];
        for (var key in value) {
            if (value.hasOwnProperty(key) && value[key] !== undefined && typeof value[key] !== "function") keys.push(key);
        }
        keys.sort();
        var props = [];
        for (var k = 0; k < keys.length; k++) props.push(quote(keys[k]) + ":" + toJson(value[keys[k]]));
        return "{" + props.join(",") + "}";
    }

    function quote(value) {
        var text = String(value);
        var result = "\"";
        for (var i = 0; i < text.length; i++) {
            var ch = text.charAt(i);
            var code = text.charCodeAt(i);
            if (ch === "\\") result += "\\\\";
            else if (ch === "\"") result += "\\\"";
            else if (ch === "\r") result += "\\r";
            else if (ch === "\n") result += "\\n";
            else if (ch === "\t") result += "\\t";
            else if (ch === "\f") result += "\\f";
            else if (ch === "\b") result += "\\b";
            else if (code < 32) result += "\\u" + hex4(code);
            else result += ch;
        }
        return result + "\"";
    }
}());
