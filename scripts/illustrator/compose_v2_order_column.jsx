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
    var currentTop = 0;
    var allItems = [];

    try {
        for (var inputIndex = 0; inputIndex < inputs.length; inputIndex++) {
            var sourcePath = String((inputs[inputIndex] || {}).path || "");
            if (!sourcePath) throw new Error("V2 compose input path missing");
            var source = app.open(File(sourcePath));
            try {
                var copied = duplicateVisibleArtwork(source, layer);
                if (!copied.length) throw new Error("V2 compose input has no artwork");
                var block = groupOrderBlock(layer, copied, inputIndex);
                var bounds = unionBounds([block]);
                var dx = 0 - Number(bounds[0]);
                var dy = currentTop - Number(bounds[1]);
                translateItems([block], dx, dy);
                var placed = unionBounds([block]);
                currentTop = Number(placed[3]) - gap;
                allItems.push(block);
            } finally {
                try { source.close(SaveOptions.DONOTSAVECHANGES); } catch (closeSourceError) {}
            }
        }
        fitArtboard(doc, allItems);
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

    function translateItems(items, dx, dy) {
        for (var index = 0; index < items.length; index++) {
            items[index].translate(dx, dy);
        }
    }

    function groupOrderBlock(layer, items, blockIndex) {
        if (!items || !items.length) throw new Error("V2 compose order block has no artwork");
        if (items.length === 1 && items[0].typename === "GroupItem") {
            items[0].name = "ORDER_PACK_BLOCK_" + blockIndex;
            return items[0];
        }
        var doc = app.activeDocument;
        doc.selection = null;
        for (var index = 0; index < items.length; index++) {
            items[index].selected = true;
        }
        app.executeMenuCommand("group");
        var block = doc.selection.length ? doc.selection[0] : null;
        if (!block || block.typename !== "GroupItem") throw new Error("Cannot create V2 compose order block");
        block.name = "ORDER_PACK_BLOCK_" + blockIndex;
        doc.selection = null;
        return block;
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
        return JSON.parse(text);
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
