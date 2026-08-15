#!/usr/bin/env python3
"""Compose a landscape clip onto a vertical (1080x1920) canvas, "Ntfb2-blur"
style: the full landscape video plays at readable size in the middle,
letterboxed (not cropped - every pixel of the source stays visible), with
the SAME video running behind it full-frame, scaled up to cover the whole
canvas and blurred - the classic "blurred backdrop" look (Spotify Canvas /
reposted landscape clips), instead of a plain color background.

    +--------------------------+
    |  same video, blurred and  |
    |  scaled to fill the       |
    |  whole canvas             |
    +--------------------------+
    |                            |
    |   the SAME video again,   |  <- sharp, full landscape frame,
    |   sharp, at native aspect |     nothing cropped
    |   ratio (letterboxed, not |
    |   cropped)                |
    |                            |
    +--------------------------+
    |  blurred video continues  |
    |  (same as above)           |
    +--------------------------+

Both layers come from the SAME input stream (ffmpeg splits it internally
when referenced twice in one filter graph) - not a separately-generated
background - so there's no frame-rate-mismatch/timing-drift class of bug
to worry about here; foreground and background are guaranteed frame-exact
in sync by construction.

Usage:
    python template_ntfb2_blur.py clip.mp4 -o reel.mp4
    python template_ntfb2_blur.py clips/ -o template_output --language hinglish
    python template_ntfb2_blur.py clip.mp4 -o reel.mp4 --blur-sigma 30 --video-y 500
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

# ============================================================================
# LAYOUT SETTINGS - these are just the DEFAULTS. Either edit them directly
# here, or override per-run with --blur-sigma/--video-y/--caption-y/
# --caption-position (see --help) without touching the file.
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920

# How strong the background blur is - bigger = blurrier/softer. gblur's
# sigma, not a pixel-radius box blur, so it stays smooth at any strength
# without the blocky look boxblur can get at high values.
DEFAULT_BLUR_SIGMA = 20

# Vertical position of the sharp foreground video's top edge. None (the
# default) centers it - (canvas height - actual video height)/2, computed
# by ffmpeg at runtime so it's correct for ANY source aspect ratio, not
# just 16:9. Pass --video-y for an absolute pixel position instead.
DEFAULT_VIDEO_Y = None

# Caption position: default sits in the blurred lower margin below the
# sharp video, comfortably clear of it. position="bottom" measures this as
# the distance from the CANVAS bottom edge upward (ASS convention).
DEFAULT_CAPTION_MARGIN_V = 260

# ============================================================================


def compose_frame(input_path: Path, framed_path: Path, duration: float, use_gpu: bool, blur_sigma: int, video_y):
    """Step: split the source into a blurred full-canvas background and a
    sharp letterboxed foreground of the same frame, then composite. No
    captions yet - that's a separate burn pass once we know the caption
    text/timing."""
    y_expr = str(video_y) if video_y is not None else "(H-h)/2"
    filter_complex = (
        f"[0:v]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{CANVAS_H},gblur=sigma={blur_sigma}[bg];"
        f"[0:v]scale={CANVAS_W}:-2[fg];"
        f"[bg][fg]overlay=x=0:y={y_expr}[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", str(framed_path)],
        ["-c:v", "libx264", "-c:a", "aac", str(framed_path)],
        use_gpu,
    )


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, args,
                   model=None, pipe=None, caption_style: CaptionStyle, use_gpu_encode: bool,
                   groq_api_key: str = None, groq_model: str = None):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    duration = get_media_duration(video_path)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    compose_frame(video_path, framed_path, duration, use_gpu_encode, args.blur_sigma, args.video_y)

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
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("ntfb2_blur_output"), help="Where to write composed reels (default: ./ntfb2_blur_output)")
    parser.add_argument("--blur-sigma", type=int, default=DEFAULT_BLUR_SIGMA, help=f"Background blur strength - bigger = blurrier (default: {DEFAULT_BLUR_SIGMA})")
    parser.add_argument("--video-y", type=int, default=DEFAULT_VIDEO_Y, help="Y position (pixels from canvas top) of the sharp video's top edge. Default: vertically centered, correct for any source aspect ratio.")
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
    parser.add_argument("--caption-position", choices=["bottom", "middle", "top"], default="bottom", help="Vertical anchor for captions (default: bottom - sits in the blurred margin below the sharp video)")
    parser.add_argument("--caption-y", type=int, default=DEFAULT_CAPTION_MARGIN_V, help=f"Caption vertical position in pixels. Meaning depends on --caption-position (default: {DEFAULT_CAPTION_MARGIN_V})")
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
            box=args.box, position=args.caption_position, margin_v=args.caption_y,
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
