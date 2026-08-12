#!/usr/bin/env python3
"""Compose a landscape/any-aspect clip onto a vertical (1080x1920) canvas,
"Ntfp1" style: a near-fullscreen video with a plain (no heading) grid-
textured black margin above it and a soft fade into the same background at
the bottom edge - no separate boxed-off video like template_compose.py.

    +--------------------------+
    |  plain black margin,      |  <- no heading text, just the faint
    |  faint grid texture       |     grid texture
    +--------------------------+
    |                            |
    |   video, cropped+tracked  |
    |   to fill the box edge-   |
    |   to-edge (auto-focus on  |
    |   the subject; zooms out  |
    |   to fit both people if   |
    |   2 are in frame)         |
    |                            |
    |   ...fades into the        |  <- soft gradient into the background
    |      background here...   |     over the last FADE_H pixels
    +--------------------------+
    |  plain black margin        |
    +--------------------------+

Unlike template_compose.py (which letterboxes the WHOLE source frame into
a modest box, showing every pixel), this template crops the source down to
the box's own aspect ratio using fanpage_crop.py's subject-aware tracking:
tight zoom on a lone subject, automatically easing out to a wider crop
that fits both people when a 2nd one enters frame.

All the layout numbers (margins, video box size, fade height) are plain
constants right below this docstring - edit them directly to change the
layout, no need to read the rest of the file.

Usage:
    python template_ntfp1.py clip.mp4 -o reel.mp4
    python template_ntfp1.py clips/ -o template_output --language hinglish
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

import fanpage_crop
import gpu_utils
from captions import CaptionStyle, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_media_duration, get_video_fps
from template_compose import _escape_subtitles_path, _gpu_error_reason, _run_with_gpu_fallback, burn_ass

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# ============================================================================
# LAYOUT SETTINGS - edit these directly to change the canvas, or override
# per-run with --video-y/--video-h/--fade-h/--caption-y/--caption-position
# (see --help) instead of editing the file.
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920

# The video's box: full width, near-fullscreen height. Estimated from the
# reference image's own proportions ("almost same size as the template") -
# a plain top margin (~20% of the canvas), the video itself (~75%), and a
# small bottom margin the video fades into (~5%).
VIDEO_BOX_W = 1080
VIDEO_BOX_H = 1450
VIDEO_Y = 380                                        # y of the box's TOP edge

# Soft fade at the BOTTOM of the video into the background, instead of a
# hard edge - height in pixels, measured up from the video box's own
# bottom edge (so it blends into whatever's below, background or the
# canvas edge).
FADE_H = 140

BG_COLOR = "0x0d0d0d"
GRID_SPACING = 54
GRID_OPACITY = 0.05

# Caption position: default sits inside the video's solid (non-faded)
# area, comfortably above where the fade starts, so text never sits on
# top of the fading edge. position="bottom" measures CAPTION_MARGIN_V as
# the distance from the CANVAS bottom edge upward (ASS convention).
CAPTION_MARGIN_V = (CANVAS_H - (VIDEO_Y + VIDEO_BOX_H - FADE_H)) + 40

# ============================================================================


def _fit_ratio() -> tuple[int, int]:
    """The video box's own aspect ratio, as a raw (w, h) tuple - passed to
    fanpage_crop.py instead of a named reframe.py aspect, since this
    template's proportions are its own fixed thing, not one of the
    standard platform ratios."""
    return VIDEO_BOX_W, VIDEO_BOX_H


def _center_crop_fallback(input_path: Path, output_path: Path, aspect, use_gpu: bool):
    """Passed into fanpage_crop.fanpage_track_and_crop as its
    static_crop_fallback - used only if literally no faces are found
    anywhere in the clip. A plain centered crop+scale to the video box's
    exact size (aspect/use_gpu params kept for call-shape compatibility,
    even though use_gpu isn't used here - the crop+scale is cheap enough
    on CPU that a GPU encode fallback dance isn't worth the complexity)."""
    vf = (
        f"crop='min(iw,ih*{VIDEO_BOX_W}/{VIDEO_BOX_H})':'min(ih,iw*{VIDEO_BOX_H}/{VIDEO_BOX_W})',"
        f"scale={VIDEO_BOX_W}:{VIDEO_BOX_H}:flags=lanczos"
    )
    subprocess.run(["ffmpeg", "-y", "-nostdin", "-i", str(input_path), "-vf", vf,
                     "-c:v", "libx264", "-c:a", "copy", str(output_path)], check=True)


def _make_fade_mask(mask_path: Path):
    """A grayscale gradient image the exact size of the video box: solid
    white (opaque) everywhere except the last FADE_H rows, which ramp
    linearly down to black (transparent). Merged onto the tracked video's
    alpha channel via ffmpeg's alphamerge filter to fade its bottom edge
    into the background - verified empirically (pixel-sampled a rendered
    frame through the transition) to blend smoothly with no seam."""
    column = np.full(VIDEO_BOX_H, 255, dtype=np.uint8)
    if FADE_H > 0:
        column[VIDEO_BOX_H - FADE_H:] = np.linspace(255, 0, FADE_H, dtype=np.uint8)
    mask = np.tile(column[:, None], (1, VIDEO_BOX_W))
    cv2.imwrite(str(mask_path), mask)


def track_and_crop(input_path: Path, tracked_path: Path, use_gpu: bool, gpu_detect: bool):
    """Step: crop the source down to the video box's exact size, following
    whoever's on screen (fanpage_crop.py - see its docstring for the
    tracking behavior)."""
    fanpage_crop.fanpage_track_and_crop(
        input_path, tracked_path, _fit_ratio(), f"{VIDEO_BOX_W}x{VIDEO_BOX_H}",
        use_gpu, _center_crop_fallback, gpu_detect,
    )


def compose_frame(tracked_path: Path, mask_path: Path, framed_path: Path, duration: float, use_gpu: bool):
    """Step: build the grid-textured background, fade the tracked video's
    bottom edge into it via the gradient mask, and composite. No captions
    yet - that's a separate burn pass once we know the caption text/timing."""
    fps = get_video_fps(tracked_path)
    filter_complex = (
        f"[1:v]drawgrid=width={GRID_SPACING}:height={GRID_SPACING}:thickness=1:color=white@{GRID_OPACITY}[bg];"
        f"[2:v]format=gray[grad];"
        f"[0:v]format=yuva420p[vidrgba];"
        f"[vidrgba][grad]alphamerge[vidfaded];"
        f"[bg][vidfaded]overlay=x=0:y={VIDEO_Y}[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(tracked_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}:r={fps}",
        "-loop", "1", "-i", str(mask_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", "-shortest", str(framed_path)],
        ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(framed_path)],
        use_gpu,
    )


def process_video(video_path: Path, output_dir: Path, mask_path: Path, i: int, total: int, *, args,
                   model=None, pipe=None, caption_style: CaptionStyle, use_gpu_encode: bool,
                   groq_api_key: str = None, groq_model: str = None):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    fd, tracked_path_str = tempfile.mkstemp(suffix="_tracked.mp4", dir=str(output_dir))
    os.close(fd)
    tracked_path = Path(tracked_path_str)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    try:
        track_and_crop(video_path, tracked_path, use_gpu_encode, args.gpu_detect)
        duration = get_media_duration(tracked_path)
        compose_frame(tracked_path, mask_path, framed_path, duration, use_gpu_encode)
    finally:
        tracked_path.unlink(missing_ok=True)

    caption_words = []
    if not args.no_captions:
        print(f"    Transcribing ({args.language})...")
        if groq_api_key:
            if args.language == "hinglish":
                from add_subtitles_groq import get_words_hinglish_groq
                caption_words = get_words_hinglish_groq(framed_path, groq_api_key, groq_model)
            else:
                from add_subtitles_groq import get_words_groq
                language = None if args.language == "auto" else args.language
                caption_words = get_words_groq(framed_path, groq_api_key, groq_model, language)
        elif pipe is not None:
            from add_subtitles import get_words_hinglish
            caption_words = get_words_hinglish(pipe, framed_path)
        else:
            from add_subtitles import get_words_faster_whisper
            language = None if args.language in ("auto", "hinglish") else args.language
            caption_words, _ = get_words_faster_whisper(model, framed_path, language)
        print(f"    Transcribed {len(caption_words)} word(s)")
        if not caption_words:
            print("    WARNING: no words transcribed - the output will have no captions. "
                  "Check the clip actually has audible speech (not just music/silence), "
                  "or try --language auto or --language en to compare.")

    output_path = output_dir / f"{video_path.stem}_reel{video_path.suffix}"
    if caption_words:
        ass_path = output_dir / f"{video_path.stem}.ass"
        video_res = (CANVAS_W, CANVAS_H)
        if args.caption_style == "word":
            count = write_ass_word_mode(caption_words, ass_path, video_res, caption_style)
        else:
            count = write_ass_highlight_mode(caption_words, ass_path, video_res, caption_style, args.max_words)
        print(f"    -> {ass_path} ({count} caption line(s))")
        if count == 0:
            print("    WARNING: 0 usable caption lines from the transcribed words - the burned "
                  "video will have NO visible captions. This usually means the word timestamps "
                  "came back degenerate (start >= end). Try a different --model/--hinglish-model, "
                  "or --caption-style word instead of highlight.")
        print(f"    Burning captions...")
        burn_ass(framed_path, ass_path, output_path, use_gpu_encode)
        framed_path.unlink()
    else:
        framed_path.replace(output_path)
    print(f"    -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("ntfp1_output"), help="Where to write composed reels (default: ./ntfp1_output)")
    parser.add_argument("--gpu-detect", action="store_true", help="Opportunistically try MediaPipe's GPU delegate for face detection (experimental, falls back to CPU automatically)")
    parser.add_argument("--no-captions", action="store_true", help="Compose the frame only, skip transcription")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="See add_subtitles.py --help (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size for en/hi/auto, ignored for --language hinglish (default: small)")
    parser.add_argument("--hinglish-model", default="swift", choices=["swift", "prime", "apex", "tiny", "small", "large"], help="Which local Hinglish model size to use (only relevant with --language hinglish, no --groq): swift/tiny (default, fastest), prime/small (more accurate), apex/large (largest/most accurate).")
    parser.add_argument("--caption-style", choices=["word", "highlight"], default="highlight", help="word = one word at a time. highlight = full line with active word highlighted (default: highlight)")
    parser.add_argument("--font", default="Arial", help="Caption font family (default: Arial)")
    parser.add_argument("--font-size", type=int, default=56, help="Caption font size (default: 56)")
    parser.add_argument("--text-color", default="white", help="Caption text color (default: white)")
    parser.add_argument("--highlight-color", default="yellow", help="Active-word caption color (default: yellow)")
    parser.add_argument("--outline-color", default="black", help="Caption text outline color (default: black)")
    parser.add_argument("--outline-width", type=int, default=3, help="Caption text outline width (default: 3)")
    parser.add_argument("--no-bold", action="store_true", help="Disable bold captions")
    parser.add_argument("--italic", action="store_true", help="Italic captions")
    parser.add_argument("--all-caps", action="store_true", help="ALL CAPS captions")
    parser.add_argument("--box", action="store_true", help="Highlight the active caption word with a solid colored box instead of colored text")
    parser.add_argument("--max-words", type=int, default=5, help="Words per on-screen caption line (default: 5)")
    parser.add_argument("--caption-position", choices=["bottom", "middle", "top"], default="bottom", help="Vertical anchor for captions (default: bottom - sits inside the video's solid area, above the fade)")
    parser.add_argument("--caption-y", type=int, default=None, help=f"Manually override the caption's vertical position in pixels, instead of editing CAPTION_MARGIN_V in the script. Meaning depends on --caption-position. Default: {CAPTION_MARGIN_V}")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    parser.add_argument("--groq", action="store_true", help="Use Groq's paid hosted Whisper API instead of the free local model, for any --language. See add_subtitles.py --help for details.")
    parser.add_argument("--groq-api-key", default=None, help="Groq API key (get one at https://console.groq.com/keys). Falls back to the GROQ_API_KEY environment variable if not passed.")
    parser.add_argument("--groq-model", default=None, help="Groq Whisper model to use (default: whisper-large-v3-turbo)")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    try:
        caption_style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position=args.caption_position,
            margin_v=args.caption_y if args.caption_y is not None else CAPTION_MARGIN_V,
        )
    except ValueError as e:
        sys.exit(str(e))

    if args.input.is_dir():
        videos = sorted(p for p in args.input.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    else:
        videos = [args.input]
    if not videos:
        sys.exit(f"No video files found in {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    mask_path = args.output_dir / ".ntfp1_fade_mask.png"
    _make_fade_mask(mask_path)

    gpu_requested = not args.no_gpu
    use_gpu_encode = gpu_requested and gpu_utils.has_nvenc()
    use_gpu_whisper = gpu_requested and gpu_utils.has_nvidia_gpu()

    model = pipe = groq_api_key = None
    groq_model = args.groq_model
    if not args.no_captions:
        if args.groq:
            from add_subtitles_groq import DEFAULT_GROQ_MODEL
            groq_model = args.groq_model or DEFAULT_GROQ_MODEL
            groq_api_key = args.groq_api_key or os.environ.get("GROQ_API_KEY")
            if not groq_api_key:
                sys.exit("--groq requires an API key: pass --groq-api-key or set the GROQ_API_KEY environment variable. Get one at https://console.groq.com/keys")
            label = "Hinglish" if args.language == "hinglish" else args.language
            print(f"Using Groq API ({groq_model}) for {label} transcription (paid)")
        elif args.language == "hinglish":
            try:
                from transformers import pipeline  # noqa: F401
            except ImportError:
                sys.exit("transformers/torch not installed. Run: pip install -r requirements.txt")
            from add_subtitles import load_hinglish_pipeline
            pipe = load_hinglish_pipeline(use_gpu_whisper, args.hinglish_model)
        else:
            try:
                from faster_whisper import WhisperModel  # noqa: F401
            except ImportError:
                sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")
            from add_subtitles import load_whisper_model
            model = load_whisper_model(args.model, use_gpu_whisper)

    failures = []
    try:
        for i, video_path in enumerate(videos, start=1):
            try:
                process_video(
                    video_path, args.output_dir, mask_path, i, len(videos), args=args, model=model, pipe=pipe,
                    caption_style=caption_style, use_gpu_encode=use_gpu_encode,
                    groq_api_key=groq_api_key, groq_model=groq_model,
                )
            except Exception as e:
                print(f"    FAILED: {video_path.name}: {e}")
                failures.append(video_path.name)
    finally:
        mask_path.unlink(missing_ok=True)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
