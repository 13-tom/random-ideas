# FFmpeg Bulk Cutter

Cut many clips out of one video from a CSV list of timestamps. Works on
Windows, Mac, and Linux — it just needs Python 3 and `ffmpeg` on your PATH.

## Setup

Install ffmpeg if you don't have it:
- Mac: `brew install ffmpeg`
- Windows: `winget install ffmpeg` (or download from ffmpeg.org and add to PATH)
- Linux: `sudo apt install ffmpeg`

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
