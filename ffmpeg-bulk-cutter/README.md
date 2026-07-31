# FFmpeg Bulk Cutter

Cut many clips out of one video from a CSV list of timestamps, then generate
free local subtitles for them. Works on Windows, Mac, and Linux — no GPU
required, everything runs on CPU.

## Setup

Install ffmpeg if you don't have it:
- Mac: `brew install ffmpeg`
- Windows: `winget install ffmpeg` (or download from ffmpeg.org and add to PATH)
- Linux: `sudo apt install ffmpeg`

Install the Python subtitle dependency:
```
pip install -r requirements.txt
```

## CSV format

One clip per row, no header: `start,end` or `start,end,label`.

```
00:00:01,00:00:03,intro
00:00:05,00:00:08,highlight
00:00:09,00:00:10
```

Timestamps accept `HH:MM:SS`, `HH:MM:SS.mmm`, `MM:SS`, or plain seconds.
`label` is optional — if omitted, clips are named `clip_001`, `clip_002`, etc.

## Usage

```
python cut_clips.py input.mp4 timestamps.csv -o clips
```

By default it uses fast lossless stream-copy cuts. If a clip starts a beat
early/late or shows a black flash (common right after a keyframe), add
`--reencode` for frame-accurate cuts at the cost of re-encoding speed:

```
python cut_clips.py input.mp4 timestamps.csv -o clips --reencode
```

See `timestamps.example.csv` for a sample you can copy and edit.

## Subtitles

Generate free, local subtitles for one video or a whole folder of clips
(no internet needed after the model downloads once, no GPU required):

```
python add_subtitles.py clips/intro.mp4
python add_subtitles.py clips -o subtitled --burn
```

- `--burn` also outputs a copy of each video with captions burned in
  (without it, you just get `.srt` files you can load in Premiere/Resolve)
- `--language en` / `--language hi` forces a language; default `auto` detects
  it per clip. Note: `hi` transcribes Hindi words in Devanagari script with
  English words kept in Latin script — this is Whisper's normal Hindi
  behavior, not Romanized "Hinglish" text.
- `--model` controls accuracy vs. speed on CPU: `tiny`/`base` are fastest,
  `small` (default) is the best balance, `medium`/`large-v3` are slower but
  more accurate. On a CPU-only laptop (no dedicated GPU), `small` is
  recommended for most clips.
