#!/usr/bin/env python3
"""A copy of template_compose.py with one difference: a PNG logo image
placed in the top margin, above the landscape video, instead of that space
staying empty (or holding heading text). Everything else - video box size/
position, background grid, caption placement below the video - is
identical to template_compose.py; see that file's docstring for the full
picture.

    +--------------------------+
    |  [LOGO]                   |  <- your PNG, left-aligned, in the
    |   (background, faint      |     plain top margin - never overlaps
    |    grid texture)          |     the video below it
    +--------------------------+
    |                            |
    |   full original video,    |
    |   NOT cropped - letterboxed|
    |   inside the box if its    |
    |   aspect ratio needs it    |
    |                            |
    +--------------------------+
    |                            |
    |      [captions here]      |
    |                            |
    +--------------------------+

Use PNG for the logo, not JPG - PNG supports a transparent background (an
alpha channel), so the logo shows up as a clean cutout over the grid
background. A JPG logo would come with an opaque rectangle around it
(JPG has no transparency), which looks wrong here.

You mentioned 5 logos: register each one as a named preset in LOGO_PRESETS
below (just add a line - name -> file path), then pick between them
per-run with --logo <name>. --logo also accepts a raw file path directly,
so presets are optional convenience, not required.

Usage:
    python template_logo.py clip.mp4 -o reel.mp4 --logo brand1
    python template_logo.py clip.mp4 -o reel.mp4 --logo /path/to/any_logo.png
    python template_logo.py clips/ -o template_output --logo brand2 --language hinglish
    python template_logo.py clip.mp4 -o reel.mp4 --logo brand1 --logo-width 300 --logo-x 80 --logo-y 40
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import gpu_utils
from captions import CaptionStyle, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_media_duration, get_video_fps
from template_compose import _run_with_gpu_fallback, burn_ass

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
LOGO_EXTENSIONS = {".png"}

# ============================================================================
# LOGO PRESETS - register your 5 logos here (name -> file path), then pick
# one per run with --logo <name>. Add/remove/rename entries freely - this
# is just a lookup table, nothing else in the file needs to change.
# ============================================================================

LOGO_PRESETS = {
    # "brand1": "/path/to/logo1.png",
    # "brand2": "/path/to/logo2.png",
    # "brand3": "/path/to/logo3.png",
    # "brand4": "/path/to/logo4.png",
    # "brand5": "/path/to/logo5.png",
}

# ============================================================================
# LAYOUT SETTINGS - same video box/caption layout as template_compose.py
# (copied as-is), plus the new logo settings below. Either edit these
# directly, or override per-run with --logo-width/--logo-x/--logo-y (see
# --help) without touching the file.
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920

VIDEO_BOX_W = 1080
VIDEO_BOX_H = 650
VIDEO_Y = 700

DEFAULT_ZOOM = 1.0

BG_COLOR = "0x0d0d0d"
GRID_SPACING = 54
GRID_OPACITY = 0.05

CAPTION_GAP = 140
CAPTION_MARGIN_TOP = VIDEO_Y + VIDEO_BOX_H + CAPTION_GAP

# Logo size and position - it lives in the plain top margin (0 to VIDEO_Y),
# left-aligned. Width in pixels; height is computed automatically to
# preserve the logo's own aspect ratio (never stretched/distorted).
DEFAULT_LOGO_WIDTH = 240
DEFAULT_LOGO_X = 60                                  # distance from canvas LEFT edge
DEFAULT_LOGO_Y = None                                # None = vertically centered within the top margin (0..VIDEO_Y); pass --logo-y for an absolute pixel position instead

# ============================================================================


def _resolve_logo_path(logo: str) -> Path:
    if logo in LOGO_PRESETS:
        path = Path(LOGO_PRESETS[logo])
    else:
        path = Path(logo)
    if not path.exists():
        presets = ", ".join(sorted(LOGO_PRESETS)) or "(none registered yet - edit LOGO_PRESETS in template_logo.py)"
        sys.exit(f"--logo {logo!r} isn't a known preset or an existing file path. Known presets: {presets}")
    if path.suffix.lower() not in LOGO_EXTENSIONS:
        print(f"    WARNING: {path.name} isn't a .png - use PNG for a transparent background, "
              "otherwise the logo will show up with a solid rectangle around it.")
    return path


def _video_filter(zoom: float) -> str:
    """zoom <= 1.0 (default): fit the whole source frame inside the box,
    preserving every pixel (letterboxed if the aspect ratio doesn't match -
    nothing cropped). zoom > 1.0: crop in by that factor and scale to fill
    the box completely instead (bigger subject, edges of the frame cut off)."""
    if zoom <= 1.0:
        return f"scale=w={VIDEO_BOX_W}:h={VIDEO_BOX_H}:force_original_aspect_ratio=decrease"
    return (
        f"crop='min(iw,ih*{VIDEO_BOX_W}/{VIDEO_BOX_H})':'min(ih,iw*{VIDEO_BOX_H}/{VIDEO_BOX_W})',"
        f"crop='iw/{zoom}':'ih/{zoom}',"
        f"scale={VIDEO_BOX_W}:{VIDEO_BOX_H}"
    )


def compose_frame(input_path: Path, logo_path: Path, framed_path: Path, duration: float, use_gpu: bool,
                   zoom: float, logo_width: int, logo_x: int, logo_y):
    """Step: build the background + video box + logo, per the layout
    settings above. No captions yet - that's a separate burn pass once we
    know the caption text/timing."""
    fps = get_video_fps(input_path)
    y_expr = str(logo_y) if logo_y is not None else f"({VIDEO_Y}-h)/2"
    filter_complex = (
        f"[1:v]drawgrid=width={GRID_SPACING}:height={GRID_SPACING}:thickness=1:color=white@{GRID_OPACITY}[bg];"
        f"[0:v]fps={fps},{_video_filter(zoom)}[vid];"
        f"[bg][vid]overlay=x=(W-w)/2:y={VIDEO_Y}+({VIDEO_BOX_H}-h)/2[withvid];"
        f"[2:v]scale={logo_width}:-1[logo];"
        f"[withvid][logo]overlay=x={logo_x}:y={y_expr}[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}:r={fps}",
        "-loop", "1", "-i", str(logo_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", "-shortest", str(framed_path)],
        ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(framed_path)],
        use_gpu,
    )


def process_video(video_path: Path, output_dir: Path, logo_path: Path, i: int, total: int, *, args,
                   model=None, pipe=None, caption_style: CaptionStyle, use_gpu_encode: bool,
                   groq_api_key: str = None, groq_model: str = None):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    duration = get_media_duration(video_path)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    compose_frame(video_path, logo_path, framed_path, duration, use_gpu_encode,
                  args.zoom, args.logo_width, args.logo_x, args.logo_y)

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
    parser.add_argument("input", type=Path, help="A landscape video file, or a folder of clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("template_output"), help="Where to write composed reels (default: ./template_output)")
    parser.add_argument("--logo", required=True, help=f"Which logo to use - either a preset name from LOGO_PRESETS in this file, or a raw path to a PNG. Known presets: {', '.join(sorted(LOGO_PRESETS)) or '(none registered yet)'}")
    parser.add_argument("--logo-width", type=int, default=DEFAULT_LOGO_WIDTH, help=f"Logo width in pixels - height is scaled automatically to preserve its aspect ratio (default: {DEFAULT_LOGO_WIDTH})")
    parser.add_argument("--logo-x", type=int, default=DEFAULT_LOGO_X, help=f"Logo's distance from the canvas LEFT edge, in pixels (default: {DEFAULT_LOGO_X})")
    parser.add_argument("--logo-y", type=int, default=DEFAULT_LOGO_Y, help="Logo's distance from the canvas TOP edge, in pixels. Default: vertically centered within the top margin above the video.")
    parser.add_argument("--zoom", type=float, default=DEFAULT_ZOOM, help=f"1.0 (default) = show the full frame, letterboxed if needed, nothing cropped. Above 1.0 crops in by that factor and fills the box completely instead, e.g. 1.3 = crops in 30%% (default: {DEFAULT_ZOOM})")
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
    parser.add_argument("--caption-position", choices=["bottom", "middle", "top"], default="top", help="Vertical anchor for captions (default: top, matches template_compose.py)")
    parser.add_argument("--caption-y", type=int, default=None, help=f"Manually override the caption's vertical position in pixels. Default: {CAPTION_MARGIN_TOP}")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    parser.add_argument("--groq", action="store_true", help="Use Groq's paid hosted Whisper API instead of the free local model, for any --language. See add_subtitles.py --help for details.")
    parser.add_argument("--groq-api-key", default=None, help="Groq API key (get one at https://console.groq.com/keys). Falls back to the GROQ_API_KEY environment variable if not passed.")
    parser.add_argument("--groq-model", default=None, help="Groq Whisper model to use (default: whisper-large-v3-turbo)")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")
    logo_path = _resolve_logo_path(args.logo)

    try:
        caption_style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position=args.caption_position,
            margin_v=args.caption_y if args.caption_y is not None else CAPTION_MARGIN_TOP,
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

    print(f"Using logo: {logo_path}")
    failures = []
    for i, video_path in enumerate(videos, start=1):
        try:
            process_video(
                video_path, args.output_dir, logo_path, i, len(videos), args=args, model=model, pipe=pipe,
                caption_style=caption_style, use_gpu_encode=use_gpu_encode,
                groq_api_key=groq_api_key, groq_model=groq_model,
            )
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
