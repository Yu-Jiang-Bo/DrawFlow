#target illustrator

/*
 * Convert FontTools-generated candidate SVGs through Illustrator before their
 * outlines are compared to a template sample.  Comparing two Illustrator
 * outlines avoids false matches caused by TrueType-vs-CFF curve conversion.
 */
(function () {
    var taskPath = $.getenv("CUSTOM_RENDER_TASK");
    if (!taskPath) throw new Error("CUSTOM_RENDER_TASK missing");

    var task = readJSON(taskPath);
    var outputFile = File(String(task.output_json || ""));
    if (!String(task.output_json || "")) throw new Error("Task missing output_json");
    var result = { candidates: [], errors: [] };
    try {
        try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (ignored0) {}
        var candidates = task.candidates instanceof Array ? task.candidates : [];
        for (var index = 0; index < candidates.length; index++) {
            result.candidates.push(probeCandidate(candidates[index] || {}));
        }
    } catch (error) {
        result.errors.push(errorText(error));
    }

    writeText(outputFile, toJson(result));
    return result.errors.length ? "PROBE_V2_OPENTYPE_TAIL_CANDIDATES_ERROR" : "PROBE_V2_OPENTYPE_TAIL_CANDIDATES_OK";

    function probeCandidate(candidate) {
        var record = { id: String(candidate.id || "") };
        var document = null;
        try {
            var source = File(String(candidate.svg_path || ""));
            if (!source.exists) throw new Error("Candidate SVG missing");
            // A headless Illustrator instance can reject documents.add() with
            // error 248 after scanning an .ai file. Opening the SVG itself is
            // both more reliable and gives the same Illustrator-normalized
            // path geometry used by the renderer.
            document = app.open(source);
            var bounds = documentBounds(document);
            var signature = outlineGeometrySignature(document, bounds);
            if (!signature) throw new Error("Candidate SVG has no outline signature");
            record.outline_signature = signature;
        } catch (error) {
            record.error = errorText(error);
        } finally {
            if (document) {
                try { document.close(SaveOptions.DONOTSAVECHANGES); } catch (ignored0) {}
            }
        }
        return record;
    }

    function documentBounds(document) {
        var pageItems = topLevelDocumentItems(document);
        var left = null, top = null, right = null, bottom = null;
        for (var index = 0; index < pageItems.length; index++) {
            var bounds = pageItems[index].visibleBounds;
            if (!bounds || bounds.length !== 4) continue;
            left = left === null ? Number(bounds[0]) : Math.min(left, Number(bounds[0]));
            top = top === null ? Number(bounds[1]) : Math.max(top, Number(bounds[1]));
            right = right === null ? Number(bounds[2]) : Math.max(right, Number(bounds[2]));
            bottom = bottom === null ? Number(bounds[3]) : Math.min(bottom, Number(bounds[3]));
        }
        return left === null ? null : [left, top, right, bottom];
    }

    function topLevelDocumentItems(document) {
        var roots = [];
        var pageItems = document.pageItems || [];
        // Document.pageItems is a flat collection: it contains both a
        // compound/group and its descendants. Probe only roots, because the
        // recursive outline collector below will visit every descendant once.
        for (var index = 0; index < pageItems.length; index++) {
            var item = pageItems[index];
            var parent = item ? item.parent : null;
            if (parent && parent.typename === "Layer") roots.push(item);
        }
        return roots;
    }

    function outlineGeometrySignature(item, bounds) {
        if (!bounds || bounds.length !== 4) return "";
        var paths = [];
        collectOutlinePathSignatures(item, bounds, paths);
        if (!paths.length) return "";
        paths.sort();
        return uniquePathSignatures(paths).join("|");
    }

    function uniquePathSignatures(paths) {
        var result = [];
        for (var index = 0; index < paths.length; index++) {
            if (!result.length || result[result.length - 1] !== paths[index]) result.push(paths[index]);
        }
        return result;
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
            result += ":" + pointSignature(point.anchor, bounds, width, height);
            result += ":" + pointSignature(point.leftDirection, bounds, width, height);
            result += ":" + pointSignature(point.rightDirection, bounds, width, height);
        }
        return result;
    }

    function pointSignature(point, bounds, width, height) {
        if (!point || point.length < 2) return "?";
        return Math.round((Number(point[0]) - Number(bounds[0])) * 1000 / width)
            + "," + Math.round((Number(point[1]) - Number(bounds[3])) * 1000 / height);
    }

    function errorText(error) {
        try { return String(error.message || error); } catch (ignored0) {}
        return "Unknown Illustrator error";
    }

    function readJSON(path) {
        var file = File(path);
        file.encoding = "UTF-8";
        if (!file.open("r")) throw new Error("Cannot read task");
        var text = file.read();
        file.close();
        return parseJson(text);
    }

    function parseJson(text) {
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(text);
        var index = 0;
        function fail(message) { throw new Error("Invalid JSON: " + message + " at " + index); }
        function peek() { return text.charAt(index); }
        function next() { return text.charAt(index++); }
        function skipWs() { while (/\s/.test(peek())) index += 1; }
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
                    } else fail("bad escape");
                } else result += ch;
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

    function writeText(file, text) {
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Cannot write probe output");
        file.write(text);
        file.close();
    }

    function toJson(value) {
        if (value === null || value === undefined) return "null";
        var type = typeof value;
        if (type === "number") return isNaN(value) || !isFinite(value) ? "null" : String(value);
        if (type === "boolean") return value ? "true" : "false";
        if (type === "string") return quote(value);
        if (value instanceof Array) {
            var values = [];
            for (var index = 0; index < value.length; index++) values.push(toJson(value[index]));
            return "[" + values.join(",") + "]";
        }
        var keys = [];
        for (var key in value) {
            if (value.hasOwnProperty(key) && value[key] !== undefined && typeof value[key] !== "function") keys.push(key);
        }
        keys.sort();
        var props = [];
        for (var keyIndex = 0; keyIndex < keys.length; keyIndex++) {
            var current = keys[keyIndex];
            props.push(quote(current) + ":" + toJson(value[current]));
        }
        return "{" + props.join(",") + "}";
    }

    function quote(value) {
        var text = String(value);
        var result = "\"";
        for (var index = 0; index < text.length; index++) {
            var ch = text.charAt(index);
            var code = text.charCodeAt(index);
            if (ch === "\\") result += "\\\\";
            else if (ch === "\"") result += "\\\"";
            else if (ch === "\r") result += "\\r";
            else if (ch === "\n") result += "\\n";
            else if (ch === "\t") result += "\\t";
            else if (code < 32) result += "\\u" + ("000" + code.toString(16)).slice(-4);
            else result += ch;
        }
        return result + "\"";
    }
}());
