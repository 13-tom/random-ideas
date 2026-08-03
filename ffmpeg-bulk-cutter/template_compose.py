#!/usr/bin/env python3
"""Compose a landscape clip onto a vertical (1080x1920) canvas: the clip is
zoomed in and cropped to fill a centered box, over a faintly-textured dark
background, with spoken captions burned directly on top of the video near
its bottom edge.

    +--------------------------+
    |   (background, faint      |
    |    grid texture)          |
    |   +--------------------+  |
    |   |                    |  |
    |   |   video, zoomed    |  |
    |   |   in and cropped   |  |
    |   |   to fill the box  |  |
    |   |                    |  |
    |   |   [captions here]  |  |  <- overlaid on the video, near its bottom
    |   +--------------------+  |
    |                            |
    +--------------------------+

All the layout numbers (box size, position, margins, where the captions
sit) are plain constants right below this docstring - edit them directly
to change the layout, no need to read the rest of the file.

Usage:
    python template_compose.py clip.mp4 -o reel.mp4
    python template_compose.py clips/ -o template_output --language hinglish
    python template_compose.py clip.mp4 -o reel.mp4 --zoom 1.3
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils
from captions import CaptionStyle, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_media_duration

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# ============================================================================
# LAYOUT SETTINGS - edit these directly to change the canvas. Nothing below
# this block needs to change to move/resize the video or captions.
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920

# The video's box: size and position on the canvas.
VIDEO_BOX_W = 1000                                   # box width  (<= CANVAS_W)
VIDEO_BOX_H = 1720                                   # box height (<= CANVAS_H)
VIDEO_Y = (CANVAS_H - VIDEO_BOX_H) // 2               # y of the box's TOP edge.
                                                       # Current value = dead
                                                       # center. Set this to
                                                       # any number 0..(CANVAS_H
                                                       # - VIDEO_BOX_H) to move
                                                       # the video up/down -
                                                       # e.g. 0 = flush with
                                                       # the top.
# (the box is always horizontally centered: x = (CANVAS_W - VIDEO_BOX_W) / 2)

# How far the source is zoomed in before it's cropped to the box's aspect
# ratio. 1.0 = crop just enough to match the box's shape, no extra zoom.
# Above 1.0 crops in further (bigger subject, more of the original frame's
# edges cut off). Overridable per-run with --zoom.
DEFAULT_ZOOM = 1.0

# Background behind the video box (visible through VIDEO_BOX_W/H margins).
BG_COLOR = "0x0d0d0d"
GRID_SPACING = 54
GRID_OPACITY = 0.05

# Captions are overlaid ON the video, this many pixels above the video
# box's bottom edge.
CAPTION_BOTTOM_PAD = 60

# ============================================================================


def _video_filter(zoom: float) -> str:
    """Crop the source to the box's aspect ratio (centered), optionally zoom
    in further, then scale to the exact box size - always fills the box
    edge to edge, no letterboxing."""
    zoom = max(zoom, 1.0)
    return (
        f"crop='min(iw,ih*{VIDEO_BOX_W}/{VIDEO_BOX_H})':'min(ih,iw*{VIDEO_BOX_H}/{VIDEO_BOX_W})',"
        f"crop='iw/{zoom}':'ih/{zoom}',"
        f"scale={VIDEO_BOX_W}:{VIDEO_BOX_H}"
    )


def _run_with_gpu_fallback(base_cmd: list[str], gpu_tail: list[str], cpu_tail: list[str], use_gpu: bool):
    if use_gpu:
        result = subprocess.run(base_cmd + gpu_tail, capture_output=True)
        if result.returncode == 0:
            return
        stderr_tail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] if result.stderr else []
        print(f"  GPU encode failed at runtime, falling back to CPU (libx264){': ' + stderr_tail[0] if stderr_tail else ''}")
    subprocess.run(base_cmd + cpu_tail, check=True)


def compose_frame(input_path: Path, framed_path: Path, duration: float, use_gpu: bool, zoom: float):
    """Step: build the background + zoomed/cropped video box, centered per
    the layout settings above. No captions yet - that's a separate burn pass
    once we know the caption text/timing."""
    filter_complex = (
        f"[1:v]drawgrid=width={GRID_SPACING}:height={GRID_SPACING}:thickness=1:color=white@{GRID_OPACITY}[bg];"
        f"[0:v]{_video_filter(zoom)}[vid];"
        f"[bg][vid]overlay=x=(W-w)/2:y={VIDEO_Y}[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", "-shortest", str(framed_path)],
        ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(framed_path)],
        use_gpu,
    )


def _escape_subtitles_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def burn_ass(video_path: Path, ass_path: Path, output_path: Path, use_gpu: bool):
    """Step: burn the caption .ass file into the composed video - this is a
    separate ffmpeg pass from compose_frame, after transcription."""
    escaped = _escape_subtitles_path(ass_path)
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-vf", f"subtitles={escaped}"]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)],
        ["-c:v", "libx264", "-c:a", "copy", str(output_path)],
        use_gpu,
    )


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, args, model=None, pipe=None,
                   caption_style: CaptionStyle, use_gpu_encode: bool):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    duration = get_media_duration(video_path)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    compose_frame(video_path, framed_path, duration, use_gpu_encode, args.zoom)

    caption_words = []
    if not args.no_captions:
        print(f"    Transcribing ({args.language})...")
        if pipe is not None:
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
            write_ass_word_mode(caption_words, ass_path, video_res, caption_style)
        else:
            write_ass_highlight_mode(caption_words, ass_path, video_res, caption_style, args.max_words)
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
    parser.add_argument("--zoom", type=float, default=DEFAULT_ZOOM, help=f"Extra zoom-in factor beyond the box-fill crop, e.g. 1.3 = 30%% more zoomed in (default: {DEFAULT_ZOOM})")
    parser.add_argument("--no-captions", action="store_true", help="Compose the frame only, skip transcription")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="See add_subtitles.py --help (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size, ignored for --language hinglish (default: small)")
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
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    video_bottom = VIDEO_Y + VIDEO_BOX_H
    caption_margin_v = (CANVAS_H - video_bottom) + CAPTION_BOTTOM_PAD

    try:
        caption_style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position="bottom", margin_v=caption_margin_v,
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

    model = pipe = None
    if not args.no_captions:
        if args.language == "hinglish":
            try:
                from transformers import pipeline  # noqa: F401
            except ImportError:
                sys.exit("transformers/torch not installed. Run: pip install -r requirements.txt")
            from add_subtitles import load_hinglish_pipeline
            pipe = load_hinglish_pipeline(use_gpu_whisper)
        else:
            try:
                from faster_whisper import WhisperModel  # noqa: F401
            except ImportError:
                sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")
            from add_subtitles import load_whisper_model
            model = load_whisper_model(args.model, use_gpu_whisper)

    failures = []
    for i, video_path in enumerate(videos, start=1):
        try:
            process_video(
                video_path, args.output_dir, i, len(videos), args=args, model=model, pipe=pipe,
                caption_style=caption_style, use_gpu_encode=use_gpu_encode,
            )
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
