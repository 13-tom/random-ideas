# FFmpeg Bulk Cutter

Cut many clips out of one video from a CSV list of timestamps, crop them to
Reels/Stories (9:16) or feed/carousel (1:1) aspect ratio, and generate free
local subtitles — plain, one-word-at-a-time, or Opus Clip-style highlighted
captions. Works on Windows, Mac, and Linux, and on any hardware: it runs on
CPU by default, and automatically speeds up using an NVIDIA GPU
(CUDA/NVENC) if one is detected — no setup needed either way, and it safely
falls back to CPU if GPU encoding fails for any reason (e.g. a
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

## Aspect ratio cropping (Reels/Stories/Carousel)

Crop a video (or a folder of clips) to a fixed aspect ratio:

```
python reframe.py clips -o reframed --aspect vertical   # 9:16, Reels/Stories
python reframe.py clips -o reframed --aspect square      # 1:1, feed/carousel
```

This is a **centered crop**, not smart subject-tracking - it works well
when the speaker/subject is roughly centered in frame (typical
talking-head footage), but it won't follow a moving subject around the
frame the way Opus Clip's face-tracking auto-reframe does. That's a
separate, harder feature (needs face detection) that isn't built yet.

## Styled captions (word-by-word / highlighted, like Opus Clip)

`add_subtitles.py --caption-style` controls how captions look:

- `plain` (default) — one `.srt` line per sentence, static text. Best for
  importing into Premiere/Resolve as an editable subtitle track.
- `word` — one word on screen at a time, big and bold (TikTok/CapCut style).
- `highlight` — a few words shown together, with the word currently being
  spoken highlighted in a different color (Opus Clip style, karaoke-style).

```
python add_subtitles.py clips -o out --caption-style word --burn
python add_subtitles.py clips -o out --caption-style highlight --highlight-color "#00FFCC" --burn
```

`word`/`highlight` modes write a `.ass` file instead of `.srt` (needed for
per-word coloring) and support:
- `--font` — font family, must be installed on your system (default: Arial)
- `--font-size` — default 64
- `--text-color` — default white; a name (white/yellow/black/red/green/
  cyan/blue/orange) or a hex code like `#FFCC00`
- `--highlight-color` — active-word color for `highlight` mode (default: yellow)
- `--max-words` — words shown per line in `highlight` mode (default: 5)

**Note on Hinglish word timing:** the Hinglish model doesn't provide true
word-level timestamps (it lacks the alignment-head metadata Whisper needs
for that), so `word`/`highlight` modes for `--language hinglish` use timing
*interpolated* proportionally across each sentence rather than the model's
own per-word alignment. It reads fine on screen, but isn't frame-perfect
the way the English/Hindi path (faster-whisper, which does give real
per-word timestamps) is.

## Full pipeline (one command)

`run_pipeline.py` chains cutting, reframing, and subtitling together — raw
video in, captioned Reels-ready clips out:

```
python run_pipeline.py raw_video.mp4 timestamps.csv -o output \
  --aspect vertical --language hinglish --caption-style highlight --reencode
```

This writes:
- `output/clips/` — the cut clips (original aspect ratio, no captions)
- `output/reframed/` — clips cropped to `--aspect` (skipped if `--aspect original`, the default)
- `output/captioned/` — caption files + `_captioned.mp4` videos, ready to post

It accepts the same `--language`, `--model`, `--caption-style` (and its
font/color flags), and `--no-gpu` flags as `add_subtitles.py`, plus
`--reencode` from `cut_clips.py` and `--aspect` from `reframe.py`.
