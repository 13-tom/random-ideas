# BulkTrim — Bulk video trimming for Adobe Premiere Pro

An ExtendScript (`.jsx`) tool that batch-trims a folder of source videos
according to a CSV of in/out points, exporting each trimmed clip directly
to disk. No Adobe Media Encoder queue, no plugin install — it runs from
Premiere's own Scripts menu.

## What it does

For each row in your CSV, the script:

1. Imports the source file into the current Premiere project.
2. Sets its source in/out points to the timecodes you specify.
3. Drops it into a small throwaway sequence.
4. Exports that sequence to disk using an export preset you provide.

## Setup

1. **Get an export preset.** In Premiere: `File > Export > Media`, dial in
   the codec/settings you want your trimmed clips exported with, then
   click **Save Preset** and remember where the `.epr` file lands.
2. **Prepare your CSV** (see `sample.csv`):

   ```
   sourcePath,inPoint,outPoint,outputName
   C:\footage\interview_01.mp4,00:01:12:00,00:02:45:00,interview_01_clip
   ```

   - `sourcePath` — absolute path to the source file.
   - `inPoint` / `outPoint` — `HH:MM:SS:FF`, `HH:MM:SS`, or plain seconds
     (e.g. `72.5`).
   - `outputName` — filename with no extension; the extension comes from
     your export preset.

   One source file can appear in multiple rows to produce multiple
   trimmed clips from it.

3. **Run the script:**
   - `File > Scripts > Browse...` and select `BulkTrim.jsx` (Premiere
     2021+), or
   - Copy `BulkTrim.jsx` into Premiere's Scripts folder so it shows up
     directly under `File > Scripts`.

   You'll be prompted to pick the CSV, the `.epr` preset, and an output
   folder (unless you hard-code paths in the `CONFIG` block at the top of
   the script).

4. Check `bulktrim_log.txt` in your output folder afterward — it lists
   which rows succeeded and which failed (with the error message).

## Notes / limitations

- Timecode with frames (`HH:MM:SS:FF`) assumes a constant frame rate,
  set via `CONFIG.frameRate` (default 30). If your sources have mixed
  frame rates, use plain seconds in the CSV instead.
- Each row leaves behind a temporary sequence (`BulkTrim_<outputName>`)
  in your project for inspection; delete them afterward if you don't
  need them.
- Source files must already be reachable on disk.
- Tested against the Premiere Pro ExtendScript API (2021+). If a call
  like `exportAsMediaDirect` behaves differently on your version, check
  Adobe's Premiere Pro Scripting Guide for that release.
