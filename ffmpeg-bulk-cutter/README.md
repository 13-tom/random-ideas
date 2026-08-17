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
  code-switched speech and outputs fully in Roman script — true Hinglish
  text like `mujhe office jana hai lekin traffic bahut zyada hai`, not
  Devanagari. This needs torch + transformers (`pip install -r
  requirements.txt` pulls the CPU build of torch, a few hundred MB).
  `--model` is ignored in this mode — that flag is for en/hi/auto. Use
  `--hinglish-model` instead to pick which of Oriserve's three sizes to
  use (each also accepts a tiny/small/large alias, in case that naming is
  easier to remember than Oriserve's own):
  - [`swift`](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift) / `tiny` (default) — smallest/fastest, still CPU-friendly
  - [`prime`](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Prime) / `small` — more accurate, ~39% better than baseline Whisper per Oriserve's benchmarks
  - [`apex`](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Apex) / `large` — largest (~800M params), most accurate, more robust on noisy/accented audio

  This is the **free** option, and the default. For clips over ~25 seconds,
  audio is split ourselves at silence gaps and each piece transcribed
  separately with its timestamps corrected back onto the full clip's
  timeline - this avoids transformers' own long-audio chunking, which is
  explicitly documented as experimental for Whisper-style models and was
  confirmed (via a user report) to cause audio/subtitle sync to drift by
  several seconds after a chunk boundary.
- `--groq` switches to **Groq's paid hosted Whisper API** instead of
  running the model locally, for **any** `--language` (`en`/`hi`/`auto`/
  `hinglish`) - no torch/transformers needed at all in this mode, real
  per-word timestamps come back directly from the API (more accurate than
  the free path's proportional-timing guess), and it's typically much
  faster since it's not running on your own CPU. Needs an API key from
  [console.groq.com/keys](https://console.groq.com/keys) (has its own free
  tier, but this flag is for when you want the paid/faster option). Pass
  it with `--groq-api-key sk-...` or set a `GROQ_API_KEY` environment
  variable so you don't have to pass it every time. `--groq-model` picks
  the Groq-hosted model (default: `whisper-large-v3-turbo`). Plain
  `en`/`hi`/`auto` transcription via Groq just requests that language
  directly - no Hinglish-specific handling involved. `--language hinglish
  --groq` **Known limitation:** Groq's checkpoint isn't
  fine-tuned for Hinglish the way the local Oriserve model is, so it needs
  a style-biasing prompt (baked in automatically) to get genuine
  transliteration instead of a straight English translation of the Hindi
  parts. Confirmed working on real code-switched clips, but with two
  quirks to know about: English words mixed into Hindi speech can come out
  phonetically misspelled (e.g. "present" -> "prezent") since the model
  errs toward phonetic spelling everywhere - the prompt has been tuned to
  discourage this but it isn't perfect - and short filler/unclear words can
  occasionally still come out garbled. If output quality matters more than
  speed, the free local model (no `--groq`) remains the more reliable
  option.

  If Groq is the only backend you ever use, `add_subtitles_groq.py` is a
  dedicated, simpler version of this same tool with no `--language`/`--groq`
  flags to remember - it's always Groq, always Hinglish:
  ```
  python add_subtitles_groq.py clips -o subtitled --burn --caption-style highlight
  ```
  Same styling flags as `add_subtitles.py` (`--font`, `--highlight-color`,
  `--box`, etc.), same `--groq-api-key`/`GROQ_API_KEY` behavior. It shares
  its Groq-calling code with `add_subtitles.py --groq` under the hood (one
  implementation, two entry points), so fixes and prompt tuning apply to
  both automatically.
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

## Removing silence (jump cuts)

`remove_silence.py` does Descript/CapCut-style auto-cut: it detects silent
gaps and splices out everything except the spoken segments, producing a
shorter video with a continuous timeline (no gaps, no black frames).

```
python remove_silence.py clip.mp4 -o jumpcut.mp4
python remove_silence.py clips/ -o jumpcut_clips
python remove_silence.py clips/ -o jumpcut_clips --min-silence 0.4 --padding 0.1
```

- `--min-silence` (default 0.7s) — gaps shorter than this are left alone as
  natural speech rhythm (breaths, pauses between words); only longer gaps
  get cut.
- `--padding` (default 0.12s) — a little audio/video is kept just before
  and after each spoken segment so words aren't clipped right at the cut.
- `--noise-db` (default `-35dB`) — volume threshold below which audio
  counts as silence; lower it (e.g. `-40dB`) if quiet speech is getting
  detected as silence, raise it (e.g. `-30dB`) if background noise/hum is
  preventing gaps from being detected.

Run this **before** captioning, not after — since it changes the video's
timeline, captions transcribed from the original video would no longer line
up. Transcribe the *output* of this script instead (or use
`run_pipeline.py --remove-silence`, below) and the caption timestamps come
out correctly matched to the new, shorter timeline automatically.

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

**`--track-mode fanpage`** - a calmer, tighter variant tuned for
fanpage/clip-account style edits (see `fanpage_crop.py`):
```
python reframe.py clips -o reframed --aspect vertical --track-faces --track-mode fanpage
```
- Tighter zoom on a lone subject than the default `dynamic` mode.
- Slower, steadier pan (bigger smoothing window) and a bigger deadzone, so
  it holds still unless the subject truly moves - prioritizes stability
  over quickly chasing movement.
- Frames by **how many people are on screen**, not who's currently
  talking: a single wide crop that's just big enough to fit everyone,
  automatically easing out the moment a 2nd person enters frame and back
  to the tight single-person crop once they leave - all in one smoothed
  pass, not a jump cut between modes. Caps at the 2 most prominent
  (largest/closest) faces, so a stray background face doesn't pull the
  crop wide open.

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

- Captions reuse the exact same transcription/styling engine as
  `add_subtitles.py` — `--language`, `--model`, `--hinglish-model`,
  `--caption-style` (`word`/`highlight`), `--font`, `--font-size`,
  `--text-color`, `--highlight-color`, `--outline-color`/`--outline-width`,
  `--no-bold`, `--italic`, `--all-caps`, `--box`, `--max-words` all work the
  same way (see the "Styled captions" section above). `--groq` (+
  `--groq-api-key`/`--groq-model`) works with **any** `--language` here
  (`en`/`hi`/`auto`/`hinglish`), not just `hinglish` - plain English/Hindi
  transcription via Groq skips the Hinglish style-biasing prompt entirely
  and just requests that language directly, e.g.
  `--language en --groq --groq-api-key sk-...`.
- `--caption-y PIXELS` — move the caption without touching the file: pass
  any pixel value on the command line to override `CAPTION_MARGIN_TOP` for
  that run only. `--caption-position {top,bottom,middle}` (default `top`)
  changes what that number is measured from — `top` (default) = distance
  from the canvas's top edge with text growing downward (matches the
  reference template), `bottom` = distance from the canvas's bottom edge
  with text growing upward, `middle` = vertically centered on that point.
- `--no-captions` — compose the frame only, skip transcription (useful if
  you want to add captions separately, or none).

The source clip's own aspect ratio doesn't have to be exactly 16:9 - it's
scaled to fit inside the content zone's box while preserving its own aspect
ratio (`force_original_aspect_ratio=decrease`), so anything landscape-ish
works. Audio comes from the source clip, GPU/CPU encoding falls back
automatically the same way every other script here does.

## Ntfp1 template (`template_ntfp1.py`)

A second reel template, matching a different reference layout than
`template_compose.py`'s: a near-fullscreen video (not a boxed-off letterbox)
with a plain grid-textured margin above it and a soft fade into the
background at the bottom edge, instead of a hard cut.

```
python template_ntfp1.py clip.mp4 -o reel.mp4
python template_ntfp1.py clips/ -o template_output --language hinglish
```

    +--------------------------+
    |  plain black margin,      |  <- no heading text, just the faint
    |  faint grid texture       |     grid texture
    +--------------------------+
    |                            |
    |   video, cropped+tracked  |
    |   to fill edge-to-edge -  |
    |   auto-focus on whoever's |
    |   on screen, zooms out    |
    |   to fit both if 2 people |
    |   are in frame            |
    |   ...fades into the        |  <- soft gradient, not a hard edge
    |      background here...   |
    +--------------------------+
    |  plain black margin        |
    +--------------------------+

The key difference from `template_compose.py`: that template letterboxes
the **whole** source frame into a modest box (every pixel visible, nothing
cropped). This one instead **crops** the source down to fill the
near-fullscreen video box edge-to-edge, using `fanpage_crop.py`'s
subject-aware tracking (see "Smart subject-tracking" → `--track-mode
fanpage` above) - tight zoom on a lone subject, automatically widening to
fit both people the moment a 2nd one enters frame.

**Adjust the layout yourself, without editing the file:**
```
python template_ntfp1.py clip.mp4 -o reel.mp4 --video-y 300 --video-h 1500 --fade-h 100
```
- `--video-y` — Y position (pixels from the canvas top) of the video box's
  top edge. Raise it to make the plain top margin taller, lower it to
  shrink the margin (default: `380`).
- `--video-h` — height of the video box in pixels. Bigger = the video
  takes up more of the canvas (default: `1450`).
- `--fade-h` — height of the fade at the video's bottom edge, in pixels,
  measured up from the video box's own bottom edge. `0` disables it for a
  hard edge instead (default: `140`).
- `--caption-y`/`--caption-position` — same as `template_compose.py`;
  the default caption position automatically re-centers itself just above
  the fade zone based on whatever `--video-y`/`--video-h`/`--fade-h` you
  pass, so you only need `--caption-y` if you want it somewhere else.

These same numbers are also the `DEFAULT_VIDEO_Y`/`DEFAULT_VIDEO_BOX_H`/
`DEFAULT_FADE_H` constants at the top of `template_ntfp1.py`, if you'd
rather change the file's own defaults once instead of passing flags every
run. Current defaults are estimated from the reference image's own
proportions - plain top margin ~20% of the canvas, video ~75%, a ~140px
fade at the bottom.

Same `--language`/`--model`/`--hinglish-model`/`--groq`, `--caption-style`
(+ font/color flags), and `--no-gpu`/`--gpu-detect` flags as
`template_compose.py`.

**How the fade is built:** the tracked/cropped video's alpha channel is
merged (`alphamerge`) with a generated grayscale gradient mask - solid
white (fully opaque) except the last `FADE_H` rows, which ramp linearly to
black (fully transparent) - then overlaid onto the grid background, so
ffmpeg's own alpha blending does the fade. Verified by pixel-sampling a
rendered frame straight through the transition band: solid video color
above the fade, a smooth linear blend down to the exact background color
across it, solid background below - no seam.

## Ntfb2-blur template (`template_ntfb2_blur.py`)

A third reel template: the classic "blurred backdrop" look (Spotify
Canvas / reposted landscape clips) - the full landscape video plays at
readable size in the middle, letterboxed (nothing cropped, every pixel of
the source visible), with the *same* video running behind it full-frame,
scaled up to cover the whole canvas and blurred, instead of a plain color
or grid background.

```
python template_ntfb2_blur.py clip.mp4 -o reel.mp4
python template_ntfb2_blur.py clips/ -o template_output --language hinglish
python template_ntfb2_blur.py clip.mp4 -o reel.mp4 --blur-sigma 30 --video-y 500
```

    +--------------------------+
    |  same video, blurred and  |
    |  scaled to fill the       |
    |  whole canvas             |
    +--------------------------+
    |                            |
    |   the SAME video again,   |  <- sharp, full landscape frame,
    |   sharp, at native aspect |     nothing cropped
    |   ratio (letterboxed)     |
    |                            |
    +--------------------------+
    |  blurred video continues  |
    +--------------------------+

Both layers come from the **same** input stream - ffmpeg splits it
internally when referenced twice in one filter graph, so there's no
separately-generated background to keep in sync, and no frame-rate-
mismatch/timing-drift class of bug possible here by construction (unlike
`template_compose.py`/`template_ntfp1.py`, which do need to match a
generated background's frame rate to the source's).

- `--blur-sigma` — background blur strength, bigger = blurrier (default:
  `20`). Uses `gblur` (Gaussian), not a pixel-radius box blur, so it stays
  smooth at any strength instead of looking blocky.
- `--video-y` — Y position (pixels from canvas top) of the sharp video's
  top edge. Default: vertically centered, computed by ffmpeg at runtime so
  it's correct for any source aspect ratio, not just 16:9.
- `--caption-y`/`--caption-position` — same as the other templates; default
  sits in the blurred margin below the sharp video.
- No face tracking involved (the video isn't cropped, just letterboxed +
  blurred), so this template doesn't need opencv/mediapipe at all -
  lighter dependency footprint than `template_ntfp1.py`.

Same `--language`/`--model`/`--hinglish-model`/`--groq`, `--caption-style`
(+ font/color flags), and `--no-gpu` flags as the other templates.

## Dreamina template (`template_dreamina.py`)

A bulk batch tool for a whole folder of numbered clips (built for a
100-video batch): burns a fixed title - not a spoken-word transcription,
one string per video read from a text file - and a logo, automatically
choosing the layout based on each clip's own orientation.

```
python template_dreamina.py clips/ titles.txt -o output
```

- **Horizontal clips** (width > height) get composed onto a white
  1080x1920 canvas matching the reference screenshot: bold black title at
  the top, the video cropped to fill its box edge-to-edge below that, and
  the logo centered beneath the video.
- **Vertical clips** (height ≥ width) are **not** recomposed - the title
  (in a solid highlighted box, like a caption chip) and the logo are
  burned straight onto the original video, at its own resolution, at
  comparable relative positions.

**Matching videos to titles:** every video filename and every line of
`titles.txt` must start with the same clip number - e.g. `clip_007.mp4`
matches a titles.txt line starting with `7`. A video with no number in
its filename, or no matching title line, is skipped with a clear reason
printed to the console rather than guessed at.

**titles.txt format** - one line per clip, `NUMBER<sep>title text`:
```
7: My brother thought this was a movie clip until I told him it's AI
12 - There is no way AI made this entire video in 30 seconds
```
`<sep>` can be `:`, `.`, `)`, `-`, or `|`. Blank lines are ignored.

**Two logos alternate automatically** by the clip's own number - odd
numbers get one, even numbers get the other - so a big batch doesn't look
identical clip to clip. Two are already registered and checked into
`logos/` (`dreamina_lowest_price.png` / `dreamina_free_generation.png`) -
override with `--logo-odd`/`--logo-even` to use different files.

Other flags: `--font`/`--title-font-size` (horizontal title),
`--vertical-title-y`/`--vertical-title-font-size`/`--title-box-color`
(vertical title), `--logo-width`/`--vertical-logo-width`/
`--vertical-logo-margin-bottom` (logo sizing/position), `--no-gpu`.
Layout constants for the horizontal canvas (`TITLE_Y`, `VIDEO_BOX_H`,
`LOGO_Y`, etc.) are at the top of the file for anything not exposed as a
flag - same edit-directly-or-pass-a-flag pattern as the other templates.

Verified end-to-end with one synthetic horizontal clip and one synthetic
vertical clip against a matching titles.txt: correct orientation
detection, correct title/logo matching by number, correct logo
alternation (odd->lowest_price, even->free_generation), horizontal output
resized to the 1080x1920 canvas while vertical output kept its own
source resolution untouched - plus a skip-behavior check (unmatched
video, unmatched title number) confirming neither crashes nor silently
guesses.

## Adding a logo/watermark (`add_logo.py`)

A plain watermark/branding pass, nothing else: stamps a PNG logo onto a
video (or a whole folder of videos) at a fixed position and size. Doesn't
touch aspect ratio, resolution, or captions - whatever the source video
already is (already-edited reels, landscape footage, anything), that's
what comes out, just with the logo overlaid on top. Not a compose
template like the others above - this is a lightweight bulk-processing
tool for videos you've already finished.

```
python add_logo.py clip.mp4 -o branded.mp4 --logo brand1
python add_logo.py clips/ -o branded_clips --logo brand2
python add_logo.py clip.mp4 -o branded.mp4 --logo /path/to/any_logo.png
python add_logo.py clips/ -o out --logo brand1 --logo-width 300 --logo-x 80 --logo-y 40
```

**Use PNG, not JPG.** PNG supports a transparent background (an alpha
channel) so the logo composites as a clean cutout - a JPG version would
come with a solid rectangle around it, since JPG has no transparency.
Verified this directly: overlaid a transparent PNG onto a test video and
confirmed the surrounding pixels show the video through, not a box.

**Picking between your logos:** register each one as a named preset in
`LOGO_PRESETS` at the top of `add_logo.py` (just add a `"name":
"/path/to/logo.png"` line), then select one per run with `--logo name`.
`--logo` also accepts a raw file path directly, so presets are a
convenience, not a requirement. Two are already registered, with their
assets checked into `logos/`:
- `aieverymorning` (alias: `brand1`) — `logos/aieverymorning.png`
- `itfeelsai` (alias: `brand2`) — `logos/itfeelsai.png`

Both started as a white-background screenshot (icon + wordmark + verified
badge) and were processed before registering: the white background was
removed via a color-to-alpha un-matte (which also cleans up anti-aliased
edges properly, not just a hard cutout), and - since the wordmark text
was black and would've been unreadable against these templates' dark
backgrounds - just the text was recolored white, leaving the icon/avatar
and badge at their original colors untouched (done by isolating the
wordmark's own horizontal pixel range first, not a blanket recolor -
an earlier blanket attempt also washed out the icon and photo, which is
why the isolation step matters).

- `--logo-width` — logo width in pixels; height is scaled automatically
  to preserve its own aspect ratio, never stretched (default: `240`).
- `--logo-x` — distance from the video's left edge (default: `40`).
- `--logo-y` — distance from the video's top edge (default: `40`).

These are also the `DEFAULT_LOGO_WIDTH`/`DEFAULT_LOGO_X`/`DEFAULT_LOGO_Y`
constants at the top of `add_logo.py`, if you'd rather change the
defaults once instead of passing flags every run. They're in pixels
relative to each source video's own frame (this script doesn't
resize/recompose anything), so re-check them if your clips vary a lot in
resolution.

**A real bug caught while building this:** `-shortest` alone doesn't
reliably terminate output when one input is a `-loop 1` still image (its
duration is effectively undefined to ffmpeg) - confirmed this directly
when a real encode hung, burning CPU for minutes on a 1.5-second test
clip instead of finishing instantly. Fixed by passing `-t` explicitly,
bound to the real source video's own duration, instead of relying on
`-shortest` to cut the output off.

## Full pipeline (one command)

`run_pipeline.py` chains cutting, silence removal, reframing, and
subtitling together — raw video in, captioned Reels-ready clips out:

```
python run_pipeline.py raw_video.mp4 timestamps.csv -o output \
  --remove-silence --aspect vertical --track-faces --language hinglish --caption-style highlight --reencode
```

This writes:
- `output/clips/` — the cut clips (original aspect ratio, no captions)
- `output/jumpcut/` — silence removed (skipped unless `--remove-silence`)
- `output/reframed/` — clips cropped to `--aspect` (skipped if `--aspect original`, the default)
- `output/captioned/` — caption files + `_captioned.mp4` videos, ready to post

`--remove-silence` runs *before* reframing/captioning on purpose: each step
transcribes/processes whatever clip is currently on disk at that point in
the pipeline, so cutting silence first means the caption timestamps
naturally match the already-shortened timeline — no separate timestamp
remapping needed. Use `--min-silence`, `--padding`, `--noise-db` to tune it
(see `remove_silence.py` above).

It accepts the same `--language`, `--model`, `--caption-style` (and its
font/color flags), and `--no-gpu` flags as `add_subtitles.py`, plus
`--reencode` from `cut_clips.py` and `--aspect`/`--track-faces` from
`reframe.py`.

## Fanpage pipeline (`fanpage_pipeline.py`)

A dedicated pipeline for fanpage/clip-account style edits — cut, crop to
whoever's on screen with smooth subject tracking, then caption, in one
command:

```
python fanpage_pipeline.py raw_video.mp4 timestamps.csv -o output \
  --aspect vertical --language hinglish --caption-style highlight
```

This writes:
- `output/clips/` — the cut clips
- `output/jumpcut/` — silence removed (skipped unless `--remove-silence`)
- `output/cropped/` — cropped to `--aspect` with fanpage-style subject tracking (always on — that's the point of this pipeline)
- `output/captioned/` — caption files + `_captioned.mp4` videos, ready to post

The crop step always uses `fanpage_crop.py`'s tracking (see "Smart
subject-tracking" → `--track-mode fanpage` above): tight zoom on a lone
subject, automatically easing out to a wider crop that fits everyone the
moment a 2nd person enters frame, and back again when they leave.

Accepts the same `--language`/`--model`/`--hinglish-model`/`--groq`,
`--caption-style` (+ font/color flags), `--remove-silence`
(+`--min-silence`/`--padding`/`--noise-db`), and `--no-gpu`/`--gpu-detect`
flags as the other pipelines/scripts above.

**Note on captions:** this currently just burns styled captions straight
onto the cropped video (the same engine as `add_subtitles.py`
`--caption-style`). The branded "Ntfp1" template (a specific layout - not
built yet) will replace this final step once it exists.
