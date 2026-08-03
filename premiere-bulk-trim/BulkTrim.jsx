/*
 * BulkTrim.jsx
 *
 * Bulk video trimming script for Adobe Premiere Pro.
 *
 * Reads a CSV file describing a batch of source clips and in/out points,
 * trims each clip, and exports it to disk using a chosen Premiere export
 * preset (.epr). Runs entirely inside Premiere's ExtendScript engine --
 * no Adobe Media Encoder queue involved, so it works synchronously and
 * needs no extra setup beyond a preset file.
 *
 * ---------------------------------------------------------------------
 * CSV FORMAT (no header row required, but a header row is skipped if the
 * first cell doesn't parse as a real file path):
 *
 *   sourcePath,inPoint,outPoint,outputName
 *
 *   sourcePath   Absolute path to the source video file.
 *   inPoint      Start of the trim. Either seconds (e.g. 12.5) or
 *                timecode HH:MM:SS:FF / HH:MM:SS (frames assume FRAME_RATE
 *                below unless the row overrides it -- see note).
 *   outPoint     End of the trim, same format as inPoint.
 *   outputName   Filename (no extension) for the exported clip. The
 *                extension/container comes from the export preset.
 *
 * Example row:
 *   C:\footage\interview_01.mp4,00:01:12:00,00:02:45:00,interview_01_clip
 *
 * ---------------------------------------------------------------------
 * SETUP
 *
 * 1. Edit the CONFIG block below, or leave paths blank to be prompted
 *    with file picker dialogs when the script runs.
 * 2. In Premiere: File > Export > Media, configure settings the way you
 *    want your trimmed clips exported, then click "Save Preset" and note
 *    where the .epr file is saved. Point PRESET_PATH at it.
 * 3. Run via File > Scripts > Browse... and select this file (Premiere
 *    2021+), or place it in Premiere's Scripts folder to have it appear
 *    directly under File > Scripts.
 *
 * LIMITATIONS
 * - Timecode-with-frames parsing assumes a constant frame rate
 *   (FRAME_RATE below). If your sources have mixed frame rates, use
 *   plain seconds (e.g. "72.5") in the CSV instead of HH:MM:SS:FF.
 * - Each row creates a temporary sequence named "BulkTrim_<outputName>"
 *   in the project; these are left in the project after the run so you
 *   can inspect them, and can be deleted safely afterward.
 * - Source files must already be reachable on disk (no proxy/relinking
 *   handled).
 * ---------------------------------------------------------------------
 */

(function () {
    // ----------------------------- CONFIG -----------------------------
    var CONFIG = {
        // Leave blank ("") to be prompted with a file picker instead.
        csvPath: "",
        presetPath: "",
        outputFolder: "",

        // Used only for timecode strings like HH:MM:SS:FF.
        frameRate: 30
    };
    // --------------------------------------------------------------

    var WORK_AREA_ENTIRE_SEQUENCE = 1;

    function main() {
        if (!app.project) {
            alert("Open a Premiere Pro project before running BulkTrim.");
            return;
        }

        var csvPath = CONFIG.csvPath || pickFile("Choose the CSV file listing clips to trim", "CSV files:*.csv");
        if (!csvPath) return;

        var presetPath = CONFIG.presetPath || pickFile("Choose an export preset (.epr)", "Export presets:*.epr");
        if (!presetPath) return;

        var outputFolder = CONFIG.outputFolder || pickFolder("Choose the output folder for trimmed clips");
        if (!outputFolder) return;

        var rows = readCsv(csvPath);
        if (rows.length === 0) {
            alert("No rows found in CSV: " + csvPath);
            return;
        }

        var results = { success: [], failed: [] };

        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            try {
                processRow(row, presetPath, outputFolder);
                results.success.push(row.outputName + " (" + row.sourcePath + ")");
            } catch (e) {
                results.failed.push(row.outputName + " (" + row.sourcePath + "): " + e.message);
            }
        }

        writeLog(outputFolder, results);
        alert(
            "BulkTrim finished.\n" +
            "Succeeded: " + results.success.length + "\n" +
            "Failed: " + results.failed.length +
            (results.failed.length ? "\n\nSee bulktrim_log.txt in the output folder for details." : "")
        );
    }

    function processRow(row, presetPath, outputFolder) {
        var file = new File(row.sourcePath);
        if (!file.exists) {
            throw new Error("Source file not found");
        }

        var importResult = app.project.importFiles(
            [row.sourcePath],
            true,   // suppressUI
            app.project.rootItem,
            false   // importAsNumberedStills
        );
        if (!importResult) {
            throw new Error("Import failed");
        }

        var projectItem = findImportedItem(row.sourcePath);
        if (!projectItem) {
            throw new Error("Could not locate imported project item");
        }

        // mediaType 4 = video + audio, per Premiere Pro scripting API.
        projectItem.setInPoint(row.inSeconds, 4);
        projectItem.setOutPoint(row.outSeconds, 4);

        var sequenceName = "BulkTrim_" + row.outputName;
        var sequence = app.project.createNewSequence(sequenceName, projectItem.nodeId);
        if (!sequence) {
            throw new Error("Could not create sequence");
        }

        sequence.videoTracks[0].insertClip(projectItem, 0);

        var outputPath = joinPath(outputFolder, row.outputName);
        var exported = sequence.exportAsMediaDirect(outputPath, presetPath, WORK_AREA_ENTIRE_SEQUENCE);
        if (!exported) {
            throw new Error("Export call returned failure");
        }
    }

    function findImportedItem(sourcePath) {
        var targetName = sourcePath.replace(/\\/g, "/").split("/").pop();
        return searchBin(app.project.rootItem, targetName);
    }

    function searchBin(bin, targetName) {
        for (var i = 0; i < bin.children.numItems; i++) {
            var item = bin.children[i];
            if (item.name === targetName) {
                return item;
            }
            if (item.type === ProjectItemType.BIN) {
                var found = searchBin(item, targetName);
                if (found) return found;
            }
        }
        return null;
    }

    function readCsv(csvPath) {
        var f = new File(csvPath);
        if (!f.exists) {
            throw new Error("CSV not found: " + csvPath);
        }
        f.open("r");
        var content = f.read();
        f.close();

        var lines = content.split(/\r\n|\r|\n/);
        var rows = [];

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            if (!line || line.replace(/\s/g, "") === "") continue;

            var cells = splitCsvLine(line);
            if (cells.length < 4) continue;

            var sourcePath = cells[0].replace(/^"|"$/g, "").replace(/\s+$/, "");

            // Skip an obvious header row.
            if (i === 0 && !new File(sourcePath).exists && /source|path|file/i.test(sourcePath)) {
                continue;
            }

            rows.push({
                sourcePath: sourcePath,
                inSeconds: parseTimeValue(cells[1], CONFIG.frameRate),
                outSeconds: parseTimeValue(cells[2], CONFIG.frameRate),
                outputName: cells[3].replace(/^"|"$/g, "").replace(/\s+$/, "")
            });
        }

        return rows;
    }

    function splitCsvLine(line) {
        var cells = [];
        var current = "";
        var inQuotes = false;

        for (var i = 0; i < line.length; i++) {
            var ch = line.charAt(i);
            if (ch === '"') {
                inQuotes = !inQuotes;
            } else if (ch === "," && !inQuotes) {
                cells.push(current);
                current = "";
            } else {
                current += ch;
            }
        }
        cells.push(current);
        return cells;
    }

    function parseTimeValue(value, frameRate) {
        value = value.replace(/^\s+|\s+$/g, "");

        if (/^\d+(\.\d+)?$/.test(value)) {
            return parseFloat(value);
        }

        var parts = value.split(":");
        if (parts.length === 3) {
            // HH:MM:SS
            return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2]);
        }
        if (parts.length === 4) {
            // HH:MM:SS:FF
            var seconds = (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2]);
            return seconds + (+parts[3]) / frameRate;
        }

        throw new Error("Unrecognized time value: " + value);
    }

    function joinPath(folder, name) {
        folder = folder.replace(/[\\\/]+$/, "");
        return folder + "/" + name;
    }

    function pickFile(prompt, filter) {
        var f = File.openDialog(prompt, filter);
        return f ? f.fsName : null;
    }

    function pickFolder(prompt) {
        var f = Folder.selectDialog(prompt);
        return f ? f.fsName : null;
    }

    function writeLog(outputFolder, results) {
        var logFile = new File(joinPath(outputFolder, "bulktrim_log.txt"));
        logFile.open("w");
        logFile.writeln("BulkTrim run: " + new Date().toString());
        logFile.writeln("");
        logFile.writeln("Succeeded (" + results.success.length + "):");
        for (var i = 0; i < results.success.length; i++) {
            logFile.writeln("  OK  " + results.success[i]);
        }
        logFile.writeln("");
        logFile.writeln("Failed (" + results.failed.length + "):");
        for (var j = 0; j < results.failed.length; j++) {
            logFile.writeln("  FAIL  " + results.failed[j]);
        }
        logFile.close();
    }

    main();
})();
