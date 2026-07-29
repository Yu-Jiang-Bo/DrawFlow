#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "compose_png_master_pages") throw new Error("Unsupported task type: " + task.type);
    var items = task.items || [];
    if (!items.length) throw new Error("No PNG items to compose");

    var frameWidth = mmToPt(Number(task.frame_width_mm || 580));
    var frameHeightLimit = mmToPt(Number(task.frame_height_mm || 2000));
    var margin = mmToPt(Number(task.margin_mm || 2));
    var columnGap = mmToPt(Number(task.column_gap_mm || 2));
    var rowGap = mmToPt(Number(task.row_gap_mm || 2));
    var labelHeight = mmToPt(Number(task.label_height_mm || 6));
    var labelWidth = mmToPt(Number(task.label_width_mm || 42));
    var labelGap = mmToPt(Number(task.label_gap_mm || 0.8));

    try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e0) {}

    var rows = planRows(items);
    var pages = paginateRows(rows);
    var outputFiles = [];
    for (var pageIndex = 0; pageIndex < pages.length; pageIndex++) {
        outputFiles.push(composePage(pages[pageIndex], pageIndex, pages.length));
    }

    writeDebug(task, {
        items: items.length,
        frame_width_mm: ptToMm(frameWidth),
        frame_height_limit_mm: ptToMm(frameHeightLimit),
        scale: 1,
        overflow: hasOverflow(pages),
        row_count: rows.length,
        page_count: pages.length,
        outputs: outputFiles,
        pages: pageDebug(pages)
    });

    return outputFiles.join("\n");

    function planRows(items) {
        var rows = [];
        var row = newRow();
        var x = margin;
        var maxRight = frameWidth - margin;
        for (var i = 0; i < items.length; i++) {
            var imageWidth = Number(items[i].width_pt || 1);
            var imageHeight = Number(items[i].height_pt || 1);
            var labelEmbedded = items[i].label_embedded === true;
            var blockWidth = Math.max(imageWidth, labelWidth);
            var blockHeight = labelEmbedded ? imageHeight : labelHeight + labelGap + imageHeight;
            if (row.placements.length && x + blockWidth > maxRight + 0.01) {
                rows.push(row);
                row = newRow();
                x = margin;
            }
            row.placements.push({
                index: i,
                x: x,
                y: 0,
                width: blockWidth,
                imageWidth: imageWidth,
                imageHeight: imageHeight,
                height: blockHeight,
                labelEmbedded: labelEmbedded
            });
            row.height = Math.max(row.height, blockHeight);
            x += blockWidth + columnGap;
        }
        if (row.placements.length) rows.push(row);
        return rows;
    }

    function newRow() {
        return { placements: [], height: 0 };
    }

    function paginateRows(rows) {
        var pages = [];
        var page = newPage();
        var cursorY = margin;
        for (var r = 0; r < rows.length; r++) {
            var row = rows[r];
            var wouldUse = cursorY + row.height + margin;
            if (page.rows.length && wouldUse > frameHeightLimit + 0.01) {
                finishPage(page, cursorY - rowGap + margin);
                pages.push(page);
                page = newPage();
                cursorY = margin;
            }
            if (cursorY + row.height + margin > frameHeightLimit + 0.01) {
                page.overflow = true;
            }
            page.rows.push(row);
            for (var p = 0; p < row.placements.length; p++) {
                var placement = clonePlacement(row.placements[p]);
                placement.y = cursorY;
                page.placements.push(placement);
            }
            cursorY += row.height + rowGap;
        }
        finishPage(page, page.placements.length ? cursorY - rowGap + margin : margin * 2);
        pages.push(page);
        return pages;
    }

    function newPage() {
        return { rows: [], placements: [], usedHeight: 0, overflow: false };
    }

    function finishPage(page, usedHeight) {
        page.usedHeight = Math.max(Math.min(usedHeight, frameHeightLimit), margin * 2 + 1);
    }

    function clonePlacement(source) {
        return {
            index: source.index,
            x: source.x,
            y: source.y,
            width: source.width,
            imageWidth: source.imageWidth,
            imageHeight: source.imageHeight,
            height: source.height,
            labelEmbedded: source.labelEmbedded
        };
    }

    function composePage(page, pageIndex, pageCount) {
        var pageHeight = page.usedHeight;
        var doc = app.documents.add(DocumentColorSpace.CMYK, frameWidth, pageHeight);
        var layer = doc.layers[0];
        layer.name = "PNG_MASTER_" + pad(pageIndex + 1, 2);
        drawWhiteBackground(layer, 0, pageHeight, frameWidth, pageHeight);

        for (var i = 0; i < page.placements.length; i++) {
            var placement = page.placements[i];
            var item = items[placement.index];
            var placed = layer.placedItems.add();
            placed.file = File(String(item.png_path));
            placed.width = placement.imageWidth;
            placed.height = placement.imageHeight;
            placed.left = placement.x + (placement.width - placement.imageWidth) / 2;
            placed.top = placement.labelEmbedded
                ? pageHeight - placement.y
                : pageHeight - placement.y - labelHeight - labelGap;
        }
        for (var l = 0; l < page.placements.length; l++) {
            if (!page.placements[l].labelEmbedded) {
                drawLabel(layer, String(items[page.placements[l].index].order_no || ""), page.placements[l], pageHeight);
            }
        }
        drawFrame(layer, 0, pageHeight, frameWidth, pageHeight);

        var aiFile = numberedFile(String(task.output_ai), pageIndex, pageCount);
        ensureFolder(aiFile.parent);
        if (aiFile.exists) aiFile.remove();
        saveAsAI8(doc, aiFile);
        doc.close(SaveOptions.DONOTSAVECHANGES);
        return aiFile.fsName;
    }

    function drawLabel(layer, text, placement, pageHeight) {
        var tf = layer.textFrames.pointText([placement.x, pageHeight - placement.y - mmToPt(0.5)]);
        tf.contents = String(text || "");
        try { tf.textRange.contents = String(text || ""); } catch (e0) {}
        tf.textRange.characterAttributes.size = 8;
        var color = new CMYKColor();
        color.cyan = 0; color.magenta = 0; color.yellow = 0; color.black = 100;
        tf.textRange.characterAttributes.fillColor = color;
        fitTextToRect(tf, [
            placement.x,
            pageHeight - placement.y,
            placement.x + placement.width,
            pageHeight - placement.y - labelHeight
        ], 5, 8);
        return tf;
    }

    function fitTextToRect(tf, rect, minSize, maxSize) {
        var left = rect[0], top = rect[1], right = rect[2], bottom = rect[3];
        var maxW = right - left;
        var maxH = top - bottom;
        var size = maxSize;
        tf.textRange.characterAttributes.size = size;
        for (var i = 0; i < 8; i++) {
            try { app.redraw(); } catch (e0) {}
            var b = tf.visibleBounds;
            var w = Math.abs(b[2] - b[0]);
            var h = Math.abs(b[1] - b[3]);
            if (w <= 0 || h <= 0) break;
            var next = Math.min(Math.max(size * Math.min(maxW / w, maxH / h) * 0.96, minSize), maxSize);
            if (Math.abs(next - size) < 0.05) break;
            size = next;
            tf.textRange.characterAttributes.size = size;
        }
        try { app.redraw(); } catch (e1) {}
        var bounds = tf.visibleBounds;
        tf.translate((left + right) / 2 - (bounds[0] + bounds[2]) / 2, (top + bottom) / 2 - (bounds[1] + bounds[3]) / 2);
    }

    function drawWhiteBackground(layer, left, top, width, height) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.filled = true;
        rect.stroked = false;
        var color = new CMYKColor();
        color.cyan = 0; color.magenta = 0; color.yellow = 0; color.black = 0;
        rect.fillColor = color;
        try { rect.zOrder(ZOrderMethod.SENDTOBACK); } catch (e0) {}
    }

    function drawFrame(layer, left, top, width, height) {
        var rect = layer.pathItems.rectangle(top, left, width, height);
        rect.filled = false;
        rect.stroked = true;
        rect.strokeWidth = 0.35;
        var color = new CMYKColor();
        color.cyan = 0; color.magenta = 0; color.yellow = 0; color.black = 100;
        rect.strokeColor = color;
    }

    function saveAsAI8(doc, file) {
        var opts = new IllustratorSaveOptions();
        opts.compatibility = Compatibility.ILLUSTRATOR8;
        opts.pdfCompatible = false;
        opts.compressed = false;
        doc.saveAs(file, opts);
    }

    function numberedFile(path, pageIndex, pageCount) {
        if (!path) throw new Error("Output path missing");
        if (pageCount <= 1) return File(path);
        var dot = path.lastIndexOf(".");
        var prefix = dot >= 0 ? path.substring(0, dot) : path;
        var ext = dot >= 0 ? path.substring(dot) : "";
        return File(prefix + "-" + pad(pageIndex + 1, 2) + ext);
    }

    function pad(value, width) {
        var text = String(value);
        while (text.length < width) text = "0" + text;
        return text;
    }

    function hasOverflow(pages) {
        for (var i = 0; i < pages.length; i++) {
            if (pages[i].overflow) return true;
        }
        return false;
    }

    function pageDebug(pages) {
        var result = [];
        for (var i = 0; i < pages.length; i++) {
            result.push({
                page: i + 1,
                items: pages[i].placements.length,
                rows: pages[i].rows.length,
                artboard_height_mm: ptToMm(pages[i].usedHeight),
                overflow: pages[i].overflow
            });
        }
        return result;
    }

    function writeDebug(task, payload) {
        var reportPath = task.debug && task.debug.report_path ? String(task.debug.report_path) : "";
        if (!reportPath) return;
        var file = File(reportPath);
        ensureFolder(file.parent);
        file.encoding = "UTF-8";
        if (file.open("w")) {
            file.write(toJson(payload));
            file.close();
        }
    }

    function readJSON(path) {
        var file = File(path);
        if (!file.exists) throw new Error("JSON file not found: " + path);
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot open JSON file: " + path);
        var text = file.read();
        file.close();
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        return eval("(" + text + ")");
    }

    function toJson(value) {
        if (value === null) return "null";
        var type = typeof value;
        if (type === "number" || type === "boolean") return String(value);
        if (type === "string") return "\"" + String(value).replace(/\\/g, "\\\\").replace(/"/g, "\\\"").replace(/\n/g, "\\n") + "\"";
        if (value instanceof Array) {
            var arr = [];
            for (var i = 0; i < value.length; i++) arr.push(toJson(value[i]));
            return "[" + arr.join(",") + "]";
        }
        var props = [];
        for (var key in value) {
            if (value.hasOwnProperty(key)) props.push(toJson(key) + ":" + toJson(value[key]));
        }
        return "{" + props.join(",") + "}";
    }

    function ensureFolder(folder) {
        if (!folder.exists) {
            ensureFolder(folder.parent);
            folder.create();
        }
    }

    function mmToPt(mm) {
        return mm * 72 / 25.4;
    }

    function ptToMm(pt) {
        return pt * 25.4 / 72;
    }
}());
