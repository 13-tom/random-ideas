#!/usr/bin/env python3
"""Compose a landscape clip onto a vertical (1080x1920) canvas, matching the
aieverymorning-style Reel template minus the heading/logo: the full,
uncropped video sits in a fixed box, over a faintly-textured dark
background, with spoken captions in their own separate space below it -
not overlaid on the video.

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

All the layout numbers (box size, position, gap to the captions) are plain
constants right below this docstring - edit them directly to change the
layout, no need to read the rest of the file.

Usage:
    python template_compose.py clip.mp4 -o reel.mp4
    python template_compose.py clips/ -o template_output --language hinglish
    python template_compose.py clip.mp4 -o reel.mp4 --zoom 1.3   # optional: crop in instead of showing the full frame
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils
from captions import CaptionStyle, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_media_duration, get_video_fps

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# ============================================================================
# LAYOUT SETTINGS - edit these directly to change the canvas. Nothing below
# this block needs to change to move/resize the video or captions.
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920

# The video's box: size and position on the canvas. Matches the reference
# template's proportions - full width (no side margins), positioned in the
# upper-middle area (~36%-70% down the canvas).
VIDEO_BOX_W = 1080                                   # box width  (<= CANVAS_W) - full width, no side margins
VIDEO_BOX_H = 650                                    # box height (<= CANVAS_H)
VIDEO_Y = 700                                        # y of the box's TOP edge.
                                                       # Set this to any number
                                                       # 0..(CANVAS_H -
                                                       # VIDEO_BOX_H) to move
                                                       # the video up/down -
                                                       # e.g. 0 = flush with
                                                       # the top.
# (the box is always horizontally centered: x = (CANVAS_W - VIDEO_BOX_W) / 2 -
# which is 0 here since VIDEO_BOX_W == CANVAS_W)

# How much the source is cropped in beyond a plain fit-inside. 1.0 (default)
# = show the FULL original frame, letterboxed inside the box if its aspect
# ratio doesn't exactly match (nothing cropped away) - this is what the
# reference template does. Above 1.0 switches to cropping in by that factor
# and filling the box edge-to-edge instead (bigger subject, edges of the
# original frame get cut off). Overridable per-run with --zoom.
DEFAULT_ZOOM = 1.0

# Background behind the video box (visible through the margins around it).
BG_COLOR = "0x0d0d0d"
GRID_SPACING = 54
GRID_OPACITY = 0.05

# Captions sit in their own space below the video, never overlapping it.
# CAPTION_MARGIN_TOP is the distance from the CANVAS TOP edge down to the
# caption text (captions use top-anchored alignment, so multi-line text
# grows downward from this point). The default puts it a fixed gap below
# the video box's bottom edge, but you can set CAPTION_MARGIN_TOP to any
# plain number yourself to move the caption independently of the video -
# or skip editing this file entirely and pass --caption-y (and
# --caption-position) on the command line instead, per-run.
CAPTION_GAP = 140                                      # (used only by the default calc below)
CAPTION_MARGIN_TOP = VIDEO_Y + VIDEO_BOX_H + CAPTION_GAP

# ============================================================================


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


def _gpu_error_reason(stderr: bytes) -> str:
    """ffmpeg's actual failure reason is usually a few lines before its
    generic final "Conversion failed!" banner - prefer a line that looks
    like a real error/hw-encoder message, falling back to the last line."""
    lines = stderr.decode(errors="replace").strip().splitlines()
    if not lines:
        return ""
    for line in reversed(lines):
        lowered = line.lower()
        if "nvenc" in lowered or "videotoolbox" in lowered or "error" in lowered or "failed" in lowered and "conversion failed" not in lowered:
            return line.strip()
    return lines[-1].strip()


def _run_with_gpu_fallback(base_cmd: list[str], gpu_tail: list[str], cpu_tail: list[str], use_gpu: bool):
    if use_gpu:
        result = subprocess.run(base_cmd + gpu_tail, capture_output=True)
        if result.returncode == 0:
            return
        reason = _gpu_error_reason(result.stderr) if result.stderr else ""
        print(f"  GPU encode failed at runtime, falling back to CPU (libx264){': ' + reason if reason else ''}")
    subprocess.run(base_cmd + cpu_tail, check=True)


def compose_frame(input_path: Path, framed_path: Path, duration: float, use_gpu: bool, zoom: float):
    """Step: build the background + video box, per the layout settings
    above. The video is centered within its box both ways - horizontally
    always, and vertically too since a letterboxed (zoom<=1.0) video can be
    shorter than the box. No captions yet - that's a separate burn pass
    once we know the caption text/timing."""
    # The generated background must run at the SAME frame rate as the real
    # source video. Without an explicit :r=, the lavfi color source defaults
    # to 25fps - if the source is anything else (24/30/29.97fps footage is
    # extremely common), overlay has to reconcile two video streams ticking
    # at different rates, and combined with -shortest below this was
    # confirmed (via a synthetic 30fps test) to truncate the composed
    # video to a fraction of its real length, and more generally to
    # introduce audio/video timing drift even when it doesn't truncate
    # outright - which is what was showing up as subtitles drifting out of
    # sync with the audio.
    fps = get_video_fps(input_path)
    filter_complex = (
        f"[1:v]drawgrid=width={GRID_SPACING}:height={GRID_SPACING}:thickness=1:color=white@{GRID_OPACITY}[bg];"
        # fps= locks the source onto the SAME frame clock as the canvas
        # (not just the same nominal rate) - real-world footage (phone
        # recordings, screen captures) is often not perfectly constant
        # frame rate even when r_frame_rate reports a clean number, and
        # that jitter was the last source of a small residual audio/caption
        # lag on top of the frame-rate-mismatch bug fixed above.
        f"[0:v]fps={fps},{_video_filter(zoom)}[vid];"
        f"[bg][vid]overlay=x=(W-w)/2:y={VIDEO_Y}+({VIDEO_BOX_H}-h)/2[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}:r={fps}",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", gpu_utils.encoder_name(), "-c:a", "aac", "-shortest", str(framed_path)],
        ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(framed_path)],
        use_gpu,
    )


def _escape_subtitles_path(path: Path) -> str:
    # Escaping the drive-letter colon alone isn't enough - confirmed via a
    # real user report (Windows, ffmpeg 9.0) and reproduced directly: the
    # subtitles filter's own option parser still splits on the escaped
    # colon and misreads everything after it as the filter's SECOND
    # positional option (original_size), throwing "Unable to parse
    # ... as image size". Wrapping the whole escaped path in single quotes
    # makes the filtergraph parser treat it as one literal token - the
    # standard fix for this exact failure mode - verified fixed with the
    # same reproduction.
    escaped = str(path).replace("\\", "/").replace(":", "\\:")
    return f"'{escaped}'"


def burn_ass(video_path: Path, ass_path: Path, output_path: Path, use_gpu: bool):
    """Step: burn the caption .ass file into the composed video - this is a
    separate ffmpeg pass from compose_frame, after transcription."""
    escaped = _escape_subtitles_path(ass_path)
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-vf", f"subtitles={escaped}"]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", gpu_utils.encoder_name(), "-c:a", "copy", str(output_path)],
        ["-c:v", "libx264", "-c:a", "copy", str(output_path)],
        use_gpu,
    )


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, args, model=None, pipe=None,
                   caption_style: CaptionStyle, use_gpu_encode: bool,
                   groq_api_key: str = None, groq_model: str = None):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    duration = get_media_duration(video_path)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    compose_frame(video_path, framed_path, duration, use_gpu_encode, args.zoom)

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
            # caption_words was non-empty, but every word got filtered out
            # while building the .ass lines (e.g. degenerate/zero-length
            # word timestamps) - burning still "succeeds" but the output
            # has no visible captions at all, which otherwise looks
            # identical to a silent failure. Surface it explicitly instead
            # of burning a blank subtitle track.
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
    parser.add_argument("--caption-position", choices=["bottom", "middle", "top"], default="top", help="Vertical anchor for captions: top = grows down from --caption-y (default, matches the reference template), bottom = grows up from --caption-y measured off the bottom edge, middle = vertically centered on --caption-y (default: top)")
    parser.add_argument("--caption-y", type=int, default=None, help=f"Manually override the caption's vertical position in pixels, instead of editing CAPTION_MARGIN_TOP/CAPTION_GAP in the script. Meaning depends on --caption-position (top = distance from canvas top, bottom = distance from canvas bottom, middle = distance from canvas top to the centered text). Default: {CAPTION_MARGIN_TOP} (computed from VIDEO_Y/VIDEO_BOX_H/CAPTION_GAP below the video box)")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if a GPU encoder (NVIDIA NVENC or Mac VideoToolbox) is detected")
    parser.add_argument("--groq", action="store_true", help="Use Groq's paid hosted Whisper API instead of the free local model, for any --language (en/hi/auto/hinglish). Faster, no local torch/transformers install needed, real per-word timestamps - but costs money and needs internet + an API key.")
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
    use_gpu_encode = gpu_requested and gpu_utils.gpu_available()
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
    for i, video_path in enumerate(videos, start=1):
        try:
            process_video(
                video_path, args.output_dir, i, len(videos), args=args, model=model, pipe=pipe,
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
