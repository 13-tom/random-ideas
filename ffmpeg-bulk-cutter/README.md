# FFmpeg Bulk Cutter

Cut many clips out of one video from a CSV list of timestamps, crop them to
Reels/Stories (9:16), square (1:1), portrait (4:5), or landscape (16:9)
aspect ratio, and generate free local subtitles — plain, one-word-at-a-time,
or Opus Clip-style highlighted captions. Works on Windows, Mac, and Linux,
and on any hardware: it runs on
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

## Aspect ratio cropping

Crop a video (or a folder of clips) to a fixed aspect ratio:

```
python reframe.py clips -o reframed --aspect vertical    # 9:16  -> 1080x1920, Reels/Stories/Shorts/TikTok
python reframe.py clips -o reframed --aspect square       # 1:1   -> 1080x1080, feed post/carousel
python reframe.py clips -o reframed --aspect portrait      # 4:5   -> 1080x1350, Instagram's own recommended feed ratio
python reframe.py clips -o reframed --aspect landscape      # 16:9  -> 1920x1080, YouTube/horizontal feed
```

By default this is a **centered crop** - works well when the
speaker/subject is roughly centered in frame, but won't follow a moving
subject.

Adding another ratio later is a one-line change: `ASPECT_RATIOS` in
`reframe.py` maps a name to a `(width, height)` ratio tuple - the crop
expression and target resolution are both derived from it automatically.

### Smart subject-tracking (`--track-faces`)

```
python reframe.py clips -o reframed --aspect vertical --track-faces
```

Detects faces across the clip (MediaPipe, free) and pans the crop window
to follow the subject, smoothed over time, instead of a fixed center
window. Falls back automatically to a static center crop if no faces are
found anywhere in the clip.

Requires `opencv-python-headless` + `mediapipe` (see `requirements.txt`).
It decodes the video twice (once to sample faces, once to crop), so it's
slower than the static crop - budget more time for longer clips.

**`--track-mode dynamic` (default) vs `--track-mode static`:**
```
python reframe.py clips -o reframed --aspect vertical --track-faces --track-mode static
```
- `dynamic` pans to follow the subject frame by frame.
- `static` detects faces the same way, but picks **one fixed crop position**
  (median face location) for the whole clip - literally zero panning, so
  zero possible camera shake. Better than a plain center crop since it's
  still centered on wherever the subject actually is, but won't follow a
  subject that moves around a lot. Good choice for a mostly-stationary
  talking-head shot where you don't want any camera movement at all.

Caught a real jitter bug building `dynamic` mode: the smoothing window was
narrower than the gap between detection samples (7 frames ≈ 0.28s of
smoothing against a 0.4s sample interval), so per-sample detection noise -
a still face's landmarks naturally wobble a few pixels frame to frame -
passed straight through as visible camera shake. Fixed with a proper
multi-sample smoothing window plus a deadzone that snaps sub-threshold
movement to a held position. Verified with real numbers, not just "looks
smoother": simulated a stationary face with realistic detection noise and
confirmed frame-to-frame movement dropped to exactly 0.000px, while a
separate test with genuine 270px movement confirmed the tracking still
follows real motion rather than being oversuppressed.

**`--zoom-on-gesture`** (dynamic mode only): the tight face-focused crop
can clip hand gestures out of frame when someone talks with their hands.
This detects hands (MediaPipe, a second model) on the same sampled frames
already used for face tracking, and eases the crop out to a wider (but
still modest - not all the way to an unzoomed full frame) view while a
hand is visible, then eases back to the normal tight crop once the
gesture ends:
```
python reframe.py clips -o reframed --aspect vertical --track-faces --zoom-on-gesture
```
The zoom transition is smoothed the same way position is (interpolate +
multi-sample window), so it eases rather than jump-cuts. Verified the
mechanics end to end with a real render: simulated a hand appearing for a
3-second window mid-clip and confirmed the output visibly zooms out
during that window and back in afterward, with no corruption or crash in
the variable-size-crop-then-resize pipeline this required. One honest
gap: I couldn't get a real photo of a hand through this sandbox's network
to verify actual hand-detection *accuracy* (only the zoom mechanics, via
a simulated detection signal) - worth keeping an eye on with your own
footage, and let me know if real gestures aren't being picked up
reliably.

**Zooms in and frames with headroom, not just a raw aspect-ratio slice.**
A crop that only just fits the target aspect ratio around the full source
frame often has nowhere to vertically reposition at all (e.g. a 16:9
source cropped to 9:16 already needs the full source height, so whatever
headroom existed in the original shot is exactly what you get - caught
this from a real clip where the subject's head ended up jammed against
the top edge). `--track-faces` zooms in further and centers the crop so
the tracked face sits in the upper third with room above the head and
more room below for chest/shoulders, using the actual tracked vertical
position rather than an untouched full-height crop.

**Multiple people in frame → follows whoever's speaking, not just the
biggest face.** It reads mouth movement over time per person (via face
landmarks, not just a bounding box) and tracks each person as a separate
identity across samples. Whoever's mouth is actively moving (not just
open once) is treated as the active speaker; switching speakers requires
a clearly sustained difference (hysteresis), so it doesn't flicker between
people on detection noise.

Face detection itself runs on CPU by default - the model is tiny (a few
ms/frame), so a GPU wouldn't meaningfully speed it up, and MediaPipe's GPU
delegate support for desktop Python is inconsistent, especially on
Windows. Pass `--gpu-detect` to opportunistically try it anyway (falls
back to CPU automatically if unavailable). Video *encoding* already uses
your GPU regardless of this flag (via `--no-gpu` to disable).

**Real limitations found while building this, not hypothetical ones:**
- The face detector needs a face to occupy roughly *half* of its input to
  detect reliably - confirmed by testing (a face at 50% of a crop was
  detected, the same face at 39% was not). A full-resolution video frame
  often makes a normally-framed face much smaller than that relative to
  the whole frame, so naive full-frame detection misses faces in ordinary
  medium shots, not just wide ones - confirmed with a single moving face
  that was completely missed at full-frame resolution.
- Worse, with **two** people in frame, full-frame detection found only
  one of them, not zero - so a "retry only if nothing found" fallback
  wasn't enough; it would have silently ignored the second person. Fixed
  by always running a tiled scan (not just as an all-faces-missed
  fallback) and deduplicating overlapping detections of the same face -
  verified with a real two-person test clip that both people are found
  and tracked.
- The active-speaker logic itself had a bug caught by testing: an early
  version scored "activity" as the full range of a person's recent mouth
  movement, which kept scoring a person as "active" for a while after
  they'd already gone quiet (one big earlier jump was still inside the
  averaging window). Switched to average frame-to-frame movement, which
  only rewards sustained, current movement - verified with a scripted
  two-speaker handoff that it now switches correctly.
- What I *haven't* been able to verify: real two-person footage with
  actual overlapping conversation (my tests use synthetic mouth-movement
  data and static photos, since I don't have real multi-speaker video to
  test against). Try it on your own footage and treat the speaker
  switching as "best effort" until you've seen it handle a real
  back-and-forth.

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
python add_subtitles.py clips -o out --caption-style word --box --highlight-color "#FFCC00" --position top --all-caps
```

`word`/`highlight` modes write a `.ass` file instead of `.srt` (needed for
per-word styling) and support:

**Text & color**
- `--font` — font family, must be installed on your system (default: Arial)
- `--font-size` — default 64
- `--text-color` — default white; a name (white/yellow/black/red/green/
  cyan/blue/orange) or a hex code like `#FFCC00`
- `--highlight-color` — active-word color for `highlight`/`--box` (default: yellow)
- `--all-caps` — render captions in ALL CAPS

**Weight & outline**
- `--no-bold` — bold is on by default (matches most Reels caption styles); disable it
- `--italic` — italic text
- `--outline-color` — text outline color (default: black)
- `--outline-width` — outline width in pixels (default: 3)

**Layout**
- `--position` — `bottom` (default), `middle`, or `top`
- `--max-words` — words shown per line in `highlight` mode (default: 5)

**`--box`** — highlights the active word with a solid colored background
pill instead of just colored text (closer to Opus Clip's actual look than
plain color-highlighting). Uses `--highlight-color` as the box fill, and
automatically picks black or white text on top of it, whichever contrasts
better. Works with both `word` and `highlight` modes.

Getting this right took a genuine debugging pass, not just writing it and
assuming it worked: ASS's "opaque box" style (`BorderStyle=3`) turned out
to fill from the *OutlineColour* field, not `BackColour` like the spec
naming suggests - confirmed by rendering several hand-written variants
and comparing them, since the box first came out solid black regardless
of the highlight color requested (verified by reading the rendered
frames, not just checking the generated `.ass` text looked plausible).

**Note on Hinglish word timing:** the Hinglish model doesn't provide true
word-level timestamps (it lacks the alignment-head metadata Whisper needs
for that), so `word`/`highlight` modes for `--language hinglish` use timing
*interpolated* proportionally across each sentence rather than the model's
own per-word alignment. It reads fine on screen, but isn't frame-perfect
the way the English/Hindi path (faster-whisper, which does give real
per-word timestamps) is.

## Reel template (`template_compose.py`)

This is a different look from `reframe.py` above. `reframe.py --track-faces`
crops the source to fill the *entire* 9:16 frame edge to edge.
`template_compose.py` instead matches the aieverymorning-style reference
template (minus the heading/logo): the full, uncropped video sits in a
fixed box, over a faintly-textured dark background, with spoken captions
in their own separate space below it - not overlaid on the video:

```
+--------------------------+
|   (background, faint      |
|    grid texture)          |
+--------------------------+
|                            |
|   full original video,    |
|   NOT cropped - letterboxed|
|   inside the box if its    |
|   aspect ratio needs it    |
|                            |
+--------------------------+
|                            |
|      [captions here]      |  <- separate zone, below the video,
|                            |     never overlapping it
+--------------------------+
```

The background isn't flat black - it's a very faint grid texture (ffmpeg's
`drawgrid`, ~5% opacity) so the margins don't look like dead space.

```
python template_compose.py clip.mp4 -o reel.mp4
python template_compose.py clips/ -o template_output --language hinglish
python template_compose.py clip.mp4 -o reel.mp4 --zoom 1.3   # optional: crop in instead of showing the full frame
```

Every layout number - the video box's size, its position, the gap to the
captions - is a plain, heavily-commented constant at the top of
`template_compose.py`. Edit those directly to reposition or resize things;
nothing else in the file needs to change.

- `VIDEO_BOX_W` / `VIDEO_BOX_H` / `VIDEO_Y` - the video box's size and its
  top-edge y-coordinate (always horizontally centered). Defaults match the
  reference template's proportions: full width, positioned in the
  upper-middle area.
- `CAPTION_MARGIN_TOP` - distance from the canvas's *top* edge down to the
  caption text (captions grow downward from this point). Defaults to a
  fixed gap below the video box, but it's an independent number - set it
  to anything to put the caption wherever you want, regardless of where
  the video itself sits.

`--zoom` (default `1.0`) shows the full frame with nothing cropped
(letterboxed if the source's aspect ratio doesn't exactly match the box).
Above `1.0` it switches to cropping in by that factor and filling the box
edge-to-edge instead - e.g. `--zoom 1.3` crops in 30%, so the subject reads
bigger at the cost of the original frame's edges being cut off.

If one clip in a batch fails (bad audio, corrupt file, etc.) it's reported
and skipped - the rest of the batch still runs, rather than the whole
command aborting.

- `--headline "TEXT"` — top-zone headline. Wrap a word in `*asterisks*` to
  render it in the highlight color, e.g. `"SAM ALTMAN *WARNS* ABOUT AI"`
  highlights just "WARNS" (matches the yellow-keyword look in the reference
  template). Wraps to a second line automatically if it's long.
- `--brand "TEXT"` — small pill/badge above the headline (e.g. an account
  handle). Uses the same opaque-box ASS trick as `--box` captions.
- `--headline-color`, `--headline-highlight-color`, `--headline-font`,
  `--headline-font-size`, `--brand-color`, `--brand-font-size` — styling for
  the above.
- Captions in the reading zone reuse the exact same transcription/styling
  engine as `add_subtitles.py` — `--language`, `--model`, `--caption-style`
  (`word`/`highlight`), `--font`, `--font-size`, `--text-color`,
  `--highlight-color`, `--outline-color`/`--outline-width`, `--no-bold`,
  `--italic`, `--all-caps`, `--box`, `--max-words` all work the same way (see
  the "Styled captions" section above). Position is fixed to the reading
  zone below the clip - not configurable here, since that's the whole point
  of the template.
- `--no-captions` — compose the frame + headline/brand only, skip
  transcription (useful if you want to add captions separately, or none).

The source clip's own aspect ratio doesn't have to be exactly 16:9 - it's
scaled to fit inside the content zone's box while preserving its own aspect
ratio (`force_original_aspect_ratio=decrease`), so anything landscape-ish
works. Audio comes from the source clip, GPU/CPU encoding falls back
automatically the same way every other script here does.

## Auto-generating timestamps with AI (`generate_timestamps.py`)

Every command above needs a `timestamps.csv` you write by hand. This script
generates one automatically: it transcribes the video, asks an LLM to pick
the most clip-worthy moments, and writes a CSV in the exact format
`cut_clips.py`/`run_pipeline.py` already read - so it's a drop-in step
*before* everything above, not a replacement for any of it.

```
python generate_timestamps.py raw_video.mp4 -o timestamps.csv
python run_pipeline.py raw_video.mp4 timestamps.csv -o output --aspect vertical --track-faces --caption-style highlight
```

Install the extra dependency first: `pip install -r requirements-scoring.txt`.

- `--provider openrouter` (default) — calls a cheap LLM via
  [OpenRouter](https://openrouter.ai) (default model: Gemini 2.5 Flash).
  Needs an API key: `--llm-api-key` or the `OPENROUTER_API_KEY` env var.
  Override the model with `--llm-model`, e.g.
  `--llm-model deepseek/deepseek-chat`.
- `--provider local` — calls a local OpenAI-compatible server instead (e.g.
  [Ollama](https://ollama.com) running on another machine reachable over
  Tailscale) for free prompt iteration during development. No API key
  needed. Point it elsewhere with `--llm-base-url` (or the
  `LOCAL_LLM_BASE_URL` env var) and `--llm-model`.
- `--min-duration` / `--max-duration` — target clip length in seconds
  (default 20-90).
- `--max-clips` — how many clips to output at most (default 10).
- `--min-score` — drop candidates the LLM scored below this, 0-100 scale
  (default 0, i.e. keep everything that survives length/overlap filtering).
- `--language` — same `en`/`hi`/`auto`/`hinglish` choices as
  `add_subtitles.py`.

If the LLM call fails outright (no API key, provider outage, an
unparseable response even after one automatic repair retry), it falls back
to evenly-spaced, unscored clips instead of failing the whole run - you
still get a usable `timestamps.csv`, just without AI ranking.

**How the scoring itself works, and how to swap models/providers:**
`clip_scoring.py` defines the provider interface
(`ClipScoringProvider.score_candidates`) that `clip_scoring_openrouter.py`
and `clip_scoring_local.py` both implement - swapping the LLM behind
`generate_timestamps.py` is a `--provider`/`--llm-model` flag, not a code
change. `clip_scoring_prompt.py` holds the actual scoring rubric (hook
strength, self-contained thought, target length, etc.) sent to the model -
that prompt is the part worth iterating on for better picks.

## Full pipeline (one command)

`run_pipeline.py` chains cutting, reframing, and subtitling together — raw
video in, captioned Reels-ready clips out:

```
python run_pipeline.py raw_video.mp4 timestamps.csv -o output \
  --aspect vertical --track-faces --language hinglish --caption-style highlight --reencode
```

This writes:
- `output/clips/` — the cut clips (original aspect ratio, no captions)
- `output/reframed/` — clips cropped to `--aspect` (skipped if `--aspect original`, the default)
- `output/captioned/` — caption files + `_captioned.mp4` videos, ready to post

It accepts the same `--language`, `--model`, `--caption-style` (and its
font/color flags), and `--no-gpu` flags as `add_subtitles.py`, plus
`--reencode` from `cut_clips.py` and `--aspect`/`--track-faces` from
`reframe.py`.
