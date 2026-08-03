#!/usr/bin/env python3
"""Compose a landscape clip into a fixed 3-zone vertical Reel template:

    +--------------------------+
    |   Top Zone (headline +   |   ~320px  - brand pill + headline text
    |   brand)                 |
    +--------------------------+
    |                          |
    |   Main Content Zone      |   original 16:9 video, LETTERBOXED
    |   (video, not cropped)   |   (not cropped) with visible side/top
    |                          |   margins so it doesn't touch the edges
    +--------------------------+
    |   Reading Zone            |   spoken captions, placed BELOW the
    |   (captions)              |   video (not overlaid on top of it)
    +--------------------------+

This is a different shape from reframe.py's crop-to-fill approach: instead
of cropping the source to fill the whole 9:16 frame, it shrinks the source
to fit inside a box and pads around it, so the full original frame stays
visible. The background isn't flat black - a very faint grid (drawgrid) is
layered in for a bit of texture instead of dead space.

Usage:
    python template_compose.py clip.mp4 -o reel.mp4 --headline "SAM ALTMAN *WARNS* ABOUT AI"
    python template_compose.py clip.mp4 -o reel.mp4 --headline "..." --brand "aieverymorning"
    python template_compose.py clips/ -o template_output --headline "..." --language hinglish
    python template_compose.py clip.mp4 -o reel.mp4 --zoom 1.2   # 20% zoom-in, crops edges to fill the box

Headline markup: wrap a word in *asterisks* to render it in the highlight
color (e.g. "ELON MUSK *WARNS* EVERYONE" highlights just "WARNS"), matching
the yellow-keyword look common in this template style.

Captions in the Reading Zone reuse the same transcription + styling engine
as add_subtitles.py (--language, --caption-style, --font, colors, etc.) -
see add_subtitles.py --help for what each of those does. Pass --no-captions
to compose the frame + headline only, with no transcription.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils
from captions import (
    EVENTS_FORMAT_LINE,
    STYLES_FORMAT_LINE,
    CaptionStyle,
    _ass_override_color,
    _escape_ass_text,
    _style_line,
    format_ass_timestamp,
    highlight_mode_dialogue_lines,
    parse_color,
    word_mode_dialogue_lines,
)
from ffmpeg_utils import get_media_duration

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# --- Template geometry (all in pixels on a fixed 1080x1920 canvas) ---
CANVAS_W, CANVAS_H = 1080, 1920
TOP_ZONE_H = 320                                    # headline + brand zone (only reserved if used)
SIDE_MARGIN = 60                                    # video's negative space, left/right (and top, when there's no heading)
VIDEO_GAP_TOP = 40                                  # gap between top zone and video
VIDEO_BOX_W = CANVAS_W - 2 * SIDE_MARGIN            # 960
VIDEO_BOX_H = round(VIDEO_BOX_W * 9 / 16)           # 540 - sized for a 16:9 source
CAPTION_GAP = 50                                    # gap between video and reading zone
CAPTION_TOP_PAD = 30                                # padding from the reading zone's top edge to the caption text

BRAND_MARGIN_V = 30
HEADLINE_MARGIN_V = 110

BG_COLOR = "0x0d0d0d"
GRID_SPACING = 54
GRID_OPACITY = 0.05


def video_y_for(has_heading: bool) -> int:
    """Top zone only takes up space if it's actually used (--headline/--brand);
    otherwise the clip is centered vertically in the canvas instead of
    hugging the top margin."""
    if has_heading:
        return TOP_ZONE_H + VIDEO_GAP_TOP
    return (CANVAS_H - VIDEO_BOX_H) // 2


def caption_margin_v_for(video_y: int) -> int:
    """Distance from the canvas top to the caption text (captions use
    top-anchored alignment), derived from wherever the video actually ends."""
    subtitle_zone_top = video_y + VIDEO_BOX_H + CAPTION_GAP
    return subtitle_zone_top + CAPTION_TOP_PAD


def _video_filter(zoom: float) -> str:
    """zoom <= 1.0 (default): fit the whole source frame inside the box,
    preserving every pixel (letterboxed, negative-space margins around it).
    zoom > 1.0: crop in by that factor and scale to fill the box completely
    (e.g. 1.2 = 20% zoomed in, edges of the frame get cropped away, subject
    reads bigger) - centered both times, since ffmpeg's crop defaults to
    centering when x/y are omitted."""
    if zoom <= 1.0:
        return f"scale=w={VIDEO_BOX_W}:h={VIDEO_BOX_H}:force_original_aspect_ratio=decrease"
    return (
        f"crop='min(iw,ih*{VIDEO_BOX_W}/{VIDEO_BOX_H})':'min(ih,iw*{VIDEO_BOX_H}/{VIDEO_BOX_W})',"
        f"crop='iw/{zoom}':'ih/{zoom}',"
        f"scale={VIDEO_BOX_W}:{VIDEO_BOX_H}"
    )


def _compose_frame(input_path: Path, framed_path: Path, duration: float, use_gpu: bool, video_y: int, zoom: float = 1.0):
    """Letterbox (or, with zoom > 1.0, zoom-and-fill) the source video inside
    the Main Content Zone over a faintly-textured dark background."""
    filter_complex = (
        f"[1:v]drawgrid=width={GRID_SPACING}:height={GRID_SPACING}:thickness=1:color=white@{GRID_OPACITY}[bg];"
        f"[0:v]{_video_filter(zoom)}[vid];"
        f"[bg][vid]overlay=x=(W-w)/2:y={video_y}+({VIDEO_BOX_H}-h)/2[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
    ]

    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "aac", "-shortest", str(framed_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        stderr_tail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] if result.stderr else []
        print(f"  GPU encode failed at runtime, falling back to CPU (libx264){': ' + stderr_tail[0] if stderr_tail else ''}")

    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(framed_path)]
    subprocess.run(cpu_cmd, check=True)


def _parse_headline_markup(text: str, base_rgb: tuple, highlight_rgb: tuple) -> str:
    """'*word*' -> that word rendered in highlight_rgb, rest in base_rgb."""
    base_tag = _ass_override_color(base_rgb)
    highlight_tag = _ass_override_color(highlight_rgb)
    parts = re.split(r"(\*[^*]+\*)", text)
    out = [f"{{\\c{base_tag}}}"]
    for part in parts:
        if not part:
            continue
        if part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"{{\\c{highlight_tag}}}{_escape_ass_text(part[1:-1])}{{\\c{base_tag}}}")
        else:
            out.append(_escape_ass_text(part))
    return "".join(out)


def write_template_ass(
    ass_path: Path, duration: float, *,
    headline: str | None, headline_style: CaptionStyle, headline_highlight_rgb: tuple,
    brand: str | None, brand_style: CaptionStyle,
    caption_words: list | None, caption_style: CaptionStyle, caption_mode: str, max_words: int,
) -> None:
    lines = [
        "[Script Info]\n", "ScriptType: v4.00+\n",
        f"PlayResX: {CANVAS_W}\n", f"PlayResY: {CANVAS_H}\n",
        "ScaledBorderAndShadow: yes\n", "\n",
        "[V4+ Styles]\n", STYLES_FORMAT_LINE,
    ]
    if headline:
        lines.append(_style_line("Headline", headline_style, headline_style.text_rgb, headline_style.outline_rgb, border_style=1))
    if brand:
        # BorderStyle=3 -> OutlineColour fills an opaque box behind the
        # text (same trick used for --box word-highlight captions).
        lines.append(_style_line("Brand", brand_style, brand_style.text_rgb, brand_style.outline_rgb, border_style=3))
    if caption_words:
        lines.append(_style_line("Default", caption_style, caption_style.text_rgb, caption_style.outline_rgb, border_style=1))
        if caption_style.box:
            lines.append(_style_line("Highlight", caption_style, (0, 0, 0), caption_style.highlight_rgb, border_style=3))

    lines += ["\n", "[Events]\n", EVENTS_FORMAT_LINE]

    if headline:
        text = _parse_headline_markup(headline, headline_style.text_rgb, headline_highlight_rgb)
        lines.append(f"Dialogue: 0,{format_ass_timestamp(0)},{format_ass_timestamp(duration)},Headline,,0,0,0,,{text}\n")
    if brand:
        lines.append(f"Dialogue: 0,{format_ass_timestamp(0)},{format_ass_timestamp(duration)},Brand,,0,0,0,,{_escape_ass_text(brand)}\n")
    if caption_words:
        if caption_mode == "word":
            dialogue_lines, _ = word_mode_dialogue_lines(caption_words, caption_style)
        else:
            dialogue_lines, _ = highlight_mode_dialogue_lines(caption_words, caption_style, max_words)
        lines += dialogue_lines

    ass_path.write_text("".join(lines), encoding="utf-8")


def _escape_subtitles_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def burn_ass(video_path: Path, ass_path: Path, output_path: Path, use_gpu: bool):
    escaped = _escape_subtitles_path(ass_path)
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-vf", f"subtitles={escaped}"]
    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        stderr_tail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] if result.stderr else []
        print(f"  GPU encode failed at runtime, falling back to CPU (libx264){': ' + stderr_tail[0] if stderr_tail else ''}")
    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "copy", str(output_path)]
    subprocess.run(cpu_cmd, check=True)


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, args, model=None, pipe=None,
                   caption_style: CaptionStyle, headline_style: CaptionStyle, brand_style: CaptionStyle,
                   use_gpu_encode: bool, use_gpu_whisper: bool):
    print(f"[{i}/{total}] Composing {video_path.name}...")
    duration = get_media_duration(video_path)
    framed_path = output_dir / f"{video_path.stem}_framed.mp4"
    has_heading = bool(args.headline or args.brand)
    _compose_frame(video_path, framed_path, duration, use_gpu_encode, video_y_for(has_heading), args.zoom)

    caption_words = None
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

    ass_path = output_dir / f"{video_path.stem}.ass"
    write_template_ass(
        ass_path, duration,
        headline=args.headline, headline_style=headline_style, headline_highlight_rgb=parse_color(args.headline_highlight_color),
        brand=args.brand, brand_style=brand_style,
        caption_words=caption_words, caption_style=caption_style, caption_mode=args.caption_style, max_words=args.max_words,
    )

    output_path = output_dir / f"{video_path.stem}_reel{video_path.suffix}"
    if args.headline or args.brand or caption_words:
        burn_ass(framed_path, ass_path, output_path, use_gpu_encode)
        framed_path.unlink()
    else:
        framed_path.replace(output_path)
    print(f"    -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A landscape video file, or a folder of clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("template_output"), help="Where to write composed reels (default: ./template_output)")
    parser.add_argument("--headline", default=None, help="Headline text for the top zone. Wrap a word in *asterisks* to highlight it, e.g. \"SAM ALTMAN *WARNS* ABOUT AI\"")
    parser.add_argument("--brand", default=None, help="Small brand/handle text shown as a pill above the headline, e.g. \"aieverymorning\"")
    parser.add_argument("--headline-color", default="white", help="Headline text color (default: white)")
    parser.add_argument("--headline-highlight-color", default="yellow", help="Color for *highlighted* headline words (default: yellow)")
    parser.add_argument("--headline-font", default="Arial", help="Headline font family (default: Arial)")
    parser.add_argument("--headline-font-size", type=int, default=58, help="Headline font size (default: 58)")
    parser.add_argument("--brand-color", default="#FFD400", help="Brand pill background color (default: #FFD400)")
    parser.add_argument("--brand-font-size", type=int, default=32, help="Brand pill font size (default: 32)")
    parser.add_argument("--zoom", type=float, default=1.2, help="Zoom in on the clip before fitting it into the content zone, e.g. 1.2 = 20%% zoom-in (this is now the default). Crops the edges to fill the box completely (centered) instead of leaving letterbox margins around the clip itself. Pass --zoom 1.0 to disable and show the full frame with negative-space margins instead.")
    parser.add_argument("--no-captions", action="store_true", help="Skip transcription; compose the frame + headline only")
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

    has_heading = bool(args.headline or args.brand)
    caption_margin_v = caption_margin_v_for(video_y_for(has_heading))

    try:
        headline_style = CaptionStyle(
            font=args.headline_font, font_size=args.headline_font_size,
            text_rgb=parse_color(args.headline_color), outline_rgb=(0, 0, 0), outline_width=3,
            bold=True, position="top", margin_v=HEADLINE_MARGIN_V,
        )
        brand_style = CaptionStyle(
            font=args.headline_font, font_size=args.brand_font_size,
            text_rgb=(0, 0, 0), outline_rgb=parse_color(args.brand_color),
            bold=True, position="top", margin_v=BRAND_MARGIN_V,
        )
        caption_style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position="top", margin_v=caption_margin_v,
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
                caption_style=caption_style, headline_style=headline_style, brand_style=brand_style,
                use_gpu_encode=use_gpu_encode, use_gpu_whisper=use_gpu_whisper,
            )
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
