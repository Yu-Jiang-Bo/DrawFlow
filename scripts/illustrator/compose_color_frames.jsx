#target illustrator

(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");
    var task = readJSON(taskPath);
    if (task.type !== "compose_color_frames") throw new Error("Unsupported task type");
    if (!task.inputs || task.inputs.length === 0) throw new Error("No color frame inputs");

    var width = mmToPt(Number(task.frame_width_mm || 0));
    var height = mmToPt(Number(task.frame_height_mm || 0));
    var gutter = mmToPt(Number(task.label_gutter_mm || 24));
    if (width <= 0 || height <= 0) throw new Error("Missing color frame dimensions");

    var doc = app.documents.add(DocumentColorSpace.CMYK, (width + gutter) * task.inputs.length, height);
    var layer = doc.layers[0];
    layer.name = "COLOR_FRAME_OUTPUT";
    for (var i = 0; i < task.inputs.length; i++) {
        var input = task.inputs[i];
        var frameLeft = gutter + i * (width + gutter);
        // AI8 has one document artboard.  Keep every color's exact production
        // frame as an invisible named boundary inside the one overall AI8 file.
        var boundary = layer.pathItems.rectangle(height, frameLeft, width, height);
        boundary.name = "COLOR_FRAME_" + String(input.color_option || "Unspecified") + "_" + task.frame_width_mm + "x" + task.frame_height_mm + "mm";
        boundary.filled = false;
        boundary.stroked = false;

        var source = app.open(File(String(input.path)));
        var sourceArtboard = source.artboards[0].artboardRect;
        var copies = [];
        var sourceItems = [];
        for (var sourceLayerIndex = 0; sourceLayerIndex < source.layers.length; sourceLayerIndex++) {
            var sourceLayer = source.layers[sourceLayerIndex];
            for (var itemIndex = sourceLayer.pageItems.length - 1; itemIndex >= 0; itemIndex--) {
                var sourceItem = sourceLayer.pageItems[itemIndex];
                if (sourceItem.parent !== sourceLayer) continue;
                // Document.pageItems is recursive. Copy only direct order
                // groups so their children are not duplicated as artwork.
                sourceItems.push(sourceItem);
                var copy = sourceItem.duplicate(layer, ElementPlacement.PLACEATEND);
                copies.push(copy);
            }
        }
        var sourceContentBounds = combinedVisibleBounds(sourceItems);
        source.close(SaveOptions.DONOTSAVECHANGES);

        var copiedBounds = combinedVisibleBounds(copies);
        // A valid component keeps its artwork inside the source artboard. Some
        // AI8 components instead retain artwork at document origin while the
        // artboard has a negative x offset; use document origin in that case.
        var artworkInsideArtboard = (
            sourceContentBounds[0] >= sourceArtboard[0] &&
            sourceContentBounds[2] <= sourceArtboard[2]
        );
        var sourceLeft = artworkInsideArtboard ? sourceArtboard[0] : 0;
        var sourceLeftInset = sourceContentBounds[0] - sourceLeft;
        var sourceTopInset = sourceArtboard[1] - sourceContentBounds[1];
        var destinationLeft = frameLeft + sourceLeftInset;
        var destinationTop = height - sourceTopInset;
        // Illustrator can add a document-origin offset while copying across
        // files. Normalize from the copied bounds rather than assuming the
        // copied coordinates equal the source coordinates.
        var deltaX = destinationLeft - copiedBounds[0];
        var deltaY = destinationTop - copiedBounds[1];
        for (var copyIndex = 0; copyIndex < copies.length; copyIndex++) {
            copies[copyIndex].translate(deltaX, deltaY);
        }

        drawLabel(layer, String(input.color_option || "Unspecified"), destinationLeft, height);
    }

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

    function drawLabel(layer, text, left, top) {
        var frame = layer.textFrames.add();
        frame.contents = text;
        frame.textRange.characterAttributes.size = 12;
        frame.position = [left, top - mmToPt(4)];
        return frame;
    }
    function combinedVisibleBounds(items) {
        if (!items || items.length === 0) throw new Error("Color component has no artwork");
        var first = items[0].visibleBounds;
        var left = first[0];
        var top = first[1];
        var right = first[2];
        var bottom = first[3];
        for (var itemIndex = 1; itemIndex < items.length; itemIndex++) {
            var bounds = items[itemIndex].visibleBounds;
            left = Math.min(left, bounds[0]);
            top = Math.max(top, bounds[1]);
            right = Math.max(right, bounds[2]);
            bottom = Math.min(bottom, bounds[3]);
        }
        return [left, top, right, bottom];
    }
    function mmToPt(mm) { return Number(mm || 0) * 72 / 25.4; }
    function readJSON(path) {
        var file = File(path);
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
}());
