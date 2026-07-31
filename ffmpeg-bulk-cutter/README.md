# FFmpeg Bulk Cutter

Cut many clips out of one video from a CSV list of timestamps, then generate
free local subtitles for them. Works on Windows, Mac, and Linux, and on any
hardware: it runs on CPU by default, and automatically speeds up using an
NVIDIA GPU (CUDA/NVENC) if one is detected — no setup needed either way, and
it safely falls back to CPU if GPU encoding fails for any reason (e.g. a
missing/outdated driver).

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
- `--language hinglish` uses a model fine-tuned specifically for Hindi+English
  code-switched speech ([Oriserve/Whisper-Hindi2Hinglish-Swift](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift))
  and outputs fully in Roman script — true Hinglish text like `mujhe office
  jana hai lekin traffic bahut zyada hai`, not Devanagari. This needs torch +
  transformers (`pip install -r requirements.txt` pulls the CPU build of
  torch, a few hundred MB). `--model` is ignored in this mode — it's a fixed,
  small (Whisper-base-sized, ~73M params) model, so it's still CPU-friendly.
- `--model` controls accuracy vs. speed for `en`/`hi`/`auto` modes:
  `tiny`/`base` are fastest, `small` (default) is the best balance on CPU,
  `medium`/`large-v3` are slower on CPU but more accurate. If you have an
  NVIDIA GPU, `medium` is a great default (fits comfortably even on 4GB
  VRAM cards like a GTX 1650); `large-v3` is best reserved for GPUs with
  more VRAM.

## GPU support

If an NVIDIA GPU is detected (`nvidia-smi` works and ffmpeg has
`h264_nvenc`), all three scripts automatically use it:
- `cut_clips.py --reencode` and `add_subtitles.py --burn` encode with
  `h264_nvenc` instead of CPU `libx264`
- `add_subtitles.py` and `run_pipeline.py` load Whisper/Hinglish models on
  CUDA (float16) instead of CPU (int8)

Pass `--no-gpu` to any script to force CPU. If GPU encoding fails at
runtime for any reason, it automatically retries on CPU and prints a
message — it won't silently produce a broken file.

Note: `pip install -r requirements.txt` installs the standard torch build
(supports GPU or CPU). If you don't have an NVIDIA GPU and want a smaller
download, see the comment in `requirements.txt` for the CPU-only build.

## Full pipeline (one command)

`run_pipeline.py` chains cutting and subtitling together — raw video in,
captioned clips out:

```
python run_pipeline.py raw_video.mp4 timestamps.csv -o output --reencode --language hinglish
```

This writes:
- `output/clips/` — the cut clips (no captions)
- `output/captioned/` — matching `.srt` files + `_captioned.mp4` videos with
  burned-in subtitles

It accepts the same `--language`, `--model`, and `--no-gpu` flags as
`add_subtitles.py`, plus `--reencode` from `cut_clips.py`.
