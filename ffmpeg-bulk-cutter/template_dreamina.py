#!/usr/bin/env python3
"""Bulk-process a whole folder of numbered video clips against a matching
titles file - "Dreamina" style: burns a fixed title (not a spoken-word
transcription - one string per video, read from a text file) and a logo,
choosing the layout automatically based on each clip's own orientation.

    Horizontal clips (width > height) get composed onto a white 1080x1920
    canvas matching the reference screenshot: bold black title at the top,
    the video cropped to fill its box edge-to-edge below that, and the
    logo centered beneath the video.

    Vertical clips (height >= width) are NOT recomposed - the title (in a
    solid highlighted box, like a caption chip) and the logo are burned
    straight onto the original video at comparable relative positions.

Matching videos to titles: every video filename and every line of the
titles file must start with the same clip number (e.g. clip_007.mp4 <->
a titles.txt line starting with "7"). Videos with no number, or no
matching title, are skipped with a warning rather than guessed at.

Titles file format - one line per clip, "NUMBER<sep>title text":
    7: My brother thought this was a movie clip until I told him it's AI
    12 - There is no way AI made this entire video in 30 seconds
<sep> can be ":", ".", ")", "-", or "|". Blank lines are ignored.

Two logos (checked into logos/) alternate by the clip's own number - odd
numbers get one, even numbers get the other - so a big batch doesn't look
identical clip to clip. Swap DEFAULT_LOGO_ODD/DEFAULT_LOGO_EVEN below to
change which, or to point at different logo files entirely.

Usage:
    python template_dreamina.py clips/ titles.txt -o output
    python template_dreamina.py clips/ titles.txt -o output --no-gpu
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import gpu_utils
from captions import CaptionStyle, _ass_header, _escape_ass_text, format_ass_timestamp, parse_color
from ffmpeg_utils import get_media_duration, get_video_fps, get_video_resolution
from template_compose import _escape_subtitles_path, _run_with_gpu_fallback

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
NUMBER_RE = re.compile(r"\d+")
TITLE_LINE_RE = re.compile(r"^\s*(\d+)\s*[:.\)\-|]\s*(.+?)\s*$")

LOGOS_DIR = Path(__file__).resolve().parent / "logos"
DEFAULT_LOGO_ODD = str(LOGOS_DIR / "dreamina_lowest_price.png")
DEFAULT_LOGO_EVEN = str(LOGOS_DIR / "dreamina_free_generation.png")

# ============================================================================
# LAYOUT SETTINGS - these are just the DEFAULTS. Either edit them directly
# here, or override the ones exposed as flags per run (see --help).
# ============================================================================

CANVAS_W = 1080
CANVAS_H = 1920
BG_COLOR = "white"

# --- Horizontal-clip template (composed white canvas) ---
TITLE_Y = 220                  # y of the title text block's top edge
TITLE_ZONE_H = 380             # reserved height for the title (fits ~3 wrapped lines at TITLE_FONT_SIZE)
TITLE_MAX_CHARS_PER_LINE = 22  # rough text-wrap width - tune alongside TITLE_FONT_SIZE
TITLE_FONT_SIZE = 64

VIDEO_Y = TITLE_Y + TITLE_ZONE_H   # video box starts right after the title zone
VIDEO_BOX_W = CANVAS_W
VIDEO_BOX_H = 620

LOGO_GAP = 100                     # gap between the video's bottom edge and the logo
LOGO_Y = VIDEO_Y + VIDEO_BOX_H + LOGO_GAP
LOGO_WIDTH = 420

# --- Vertical-clip direct overlay (no recomposition) ---
VERTICAL_TITLE_Y = 150
VERTICAL_TITLE_MAX_CHARS_PER_LINE = 20
VERTICAL_TITLE_FONT_SIZE = 56
VERTICAL_LOGO_WIDTH = 380
# Distance from the video's own bottom edge to the LOGO'S OWN BOTTOM EDGE
# (not its top - see the comment in compose_vertical). Instagram's Reels
# player overlays its own UI on top of your video: username + caption +
# audio credit stacked in the bottom-left, and a like/comment/share/save
# icon column on the right (roughly the rightmost ~150px of a 1080px-wide
# frame). 420px keeps the logo clear of that bottom-left text stack, which
# can run 2-3 lines deep for a long caption; the logo itself is already
# horizontally centered well clear of the right icon column as long as
# VERTICAL_LOGO_WIDTH stays well under the frame width.
VERTICAL_LOGO_MARGIN_BOTTOM = 420

# ============================================================================


def parse_titles_file(path: Path) -> dict[int, str]:
    titles = {}
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        m = TITLE_LINE_RE.match(line)
        if not m:
            print(f"  WARNING: {path.name} line {lineno} doesn't look like 'NUMBER: title' - skipping: {line!r}")
            continue
        num, title = int(m.group(1)), m.group(2).strip()
        if num in titles:
            print(f"  WARNING: {path.name} has two lines for #{num} - keeping the first, ignoring line {lineno}")
            continue
        titles[num] = title
    return titles


def extract_number(name: str) -> int | None:
    m = NUMBER_RE.search(name)
    return int(m.group()) if m else None


def _wrap_title(text: str, max_chars: int) -> str:
    return textwrap.fill(text, width=max_chars)


def write_title_ass(text: str, ass_path: Path, video_res: tuple, style: CaptionStyle, duration: float, max_chars: int):
    """A single static Dialogue line spanning the whole clip - not word-
    timed captions, just one fixed title string, optionally in a solid
    highlighted box (style.box=True) reusing captions.py's existing
    BorderStyle=3 box-fill mechanism."""
    width, height = video_res
    wrapped = _escape_ass_text(_wrap_title(text, max_chars))
    style_name = "Highlight" if style.box else "Default"
    start, end = format_ass_timestamp(0), format_ass_timestamp(duration)
    dialogue = f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{wrapped}\n"
    ass_path.write_text(_ass_header(width, height, style) + dialogue, encoding="utf-8")


def _center_crop_fill(box_w: int, box_h: int) -> str:
    return f"crop='min(iw,ih*{box_w}/{box_h})':'min(ih,iw*{box_h}/{box_w})',scale={box_w}:{box_h}:flags=lanczos"


def compose_horizontal(input_path: Path, ass_path: Path, logo_path: Path, output_path: Path,
                        duration: float, use_gpu: bool, logo_width: int):
    """White canvas: title at the top, video cropped-to-fill below it,
    logo centered beneath the video."""
    fps = get_video_fps(input_path)
    escaped_ass = _escape_subtitles_path(ass_path)
    filter_complex = (
        f"[0:v]{_center_crop_fill(VIDEO_BOX_W, VIDEO_BOX_H)}[vid];"
        f"[1:v][vid]overlay=x=(W-w)/2:y={VIDEO_Y}[withvid];"
        f"[withvid]subtitles={escaped_ass}[titled];"
        f"[2:v]scale={logo_width}:-1[logo];"
        f"[titled][logo]overlay=x=(W-w)/2:y={LOGO_Y}[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-f", "lavfi", "-i", f"color=c={BG_COLOR}:s={CANVAS_W}x{CANVAS_H}:d={duration}:r={fps}",
        "-loop", "1", "-i", str(logo_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?", "-t", str(duration),
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", str(output_path)],
        ["-c:v", "libx264", "-c:a", "aac", str(output_path)],
        use_gpu,
    )


def compose_vertical(input_path: Path, ass_path: Path, logo_path: Path, output_path: Path,
                      duration: float, use_gpu: bool, logo_width: int, logo_margin_bottom: int):
    """No recomposition - burn the title (highlighted box) and logo
    straight onto the original vertical video, at its own resolution."""
    src_w, src_h = get_video_resolution(input_path)
    escaped_ass = _escape_subtitles_path(ass_path)
    # y=H-{margin}-h (h = the logo's own scaled height, resolved by ffmpeg
    # at filter-graph runtime) measures logo_margin_bottom from the LOGO'S
    # OWN BOTTOM EDGE to the frame's bottom edge. An earlier version used
    # H-{margin} directly as the logo's TOP y-coordinate instead, which
    # silently let the logo's bottom edge sit margin-minus-height (not
    # margin) pixels from the true bottom - for this logo's height that
    # put it right in Instagram's own username/caption overlay zone.
    filter_complex = (
        f"[0:v]subtitles={escaped_ass}[titled];"
        f"[1:v]scale={logo_width}:-1[logo];"
        f"[titled][logo]overlay=x=({src_w}-w)/2:y=H-{logo_margin_bottom}-h[outv]"
    )
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-loop", "1", "-i", str(logo_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?", "-t", str(duration),
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", "h264_nvenc", "-c:a", "aac", str(output_path)],
        ["-c:v", "libx264", "-c:a", "aac", str(output_path)],
        use_gpu,
    )


def process_video(video_path: Path, title: str, logo_path: Path, output_dir: Path, use_gpu: bool, args):
    duration = get_media_duration(video_path)
    src_w, src_h = get_video_resolution(video_path)
    horizontal = src_w > src_h
    output_path = output_dir / f"{video_path.stem}_dreamina{video_path.suffix}"

    fd, ass_path_str = tempfile.mkstemp(suffix=".ass", dir=str(output_dir))
    os.close(fd)
    ass_path = Path(ass_path_str)
    try:
        if horizontal:
            style = CaptionStyle(
                font=args.font, font_size=args.title_font_size, text_rgb=(0, 0, 0),
                bold=True, outline_width=0, position="top", margin_v=TITLE_Y,
            )
            write_title_ass(title, ass_path, (CANVAS_W, CANVAS_H), style, duration, args.title_max_chars_per_line)
            compose_horizontal(video_path, ass_path, logo_path, output_path, duration, use_gpu, args.logo_width)
        else:
            style = CaptionStyle(
                font=args.font, font_size=args.vertical_title_font_size,
                highlight_rgb=parse_color(args.title_box_color), bold=True,
                box=True, position="top", margin_v=args.vertical_title_y,
            )
            write_title_ass(title, ass_path, (src_w, src_h), style, duration, args.vertical_title_max_chars_per_line)
            compose_vertical(video_path, ass_path, logo_path, output_path, duration, use_gpu,
                              args.vertical_logo_width, args.vertical_logo_margin_bottom)
    finally:
        ass_path.unlink(missing_ok=True)

    return output_path, horizontal


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Folder of numbered video clips")
    parser.add_argument("titles", type=Path, help="Titles file: one 'NUMBER: title text' line per clip")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("dreamina_output"), help="Where to write processed videos (default: ./dreamina_output)")
    parser.add_argument("--font", default="Arial", help="Title font family (default: Arial)")
    parser.add_argument("--title-font-size", type=int, default=TITLE_FONT_SIZE, help=f"Title font size for horizontal-template clips (default: {TITLE_FONT_SIZE})")
    parser.add_argument("--title-max-chars-per-line", type=int, default=TITLE_MAX_CHARS_PER_LINE, help=f"How many characters wide a title line can be, for horizontal-template clips, before wrapping to a new line - raise this to widen lines and use fewer of them (default: {TITLE_MAX_CHARS_PER_LINE})")
    parser.add_argument("--logo-width", type=int, default=LOGO_WIDTH, help=f"Logo width in pixels for horizontal-template clips (default: {LOGO_WIDTH})")
    parser.add_argument("--vertical-title-y", type=int, default=VERTICAL_TITLE_Y, help=f"Title's distance from the top edge for vertical clips (default: {VERTICAL_TITLE_Y})")
    parser.add_argument("--vertical-title-font-size", type=int, default=VERTICAL_TITLE_FONT_SIZE, help=f"Title font size for vertical clips (default: {VERTICAL_TITLE_FONT_SIZE})")
    parser.add_argument("--vertical-title-max-chars-per-line", type=int, default=VERTICAL_TITLE_MAX_CHARS_PER_LINE, help=f"How many characters wide a title line can be, for vertical clips, before wrapping to a new line (default: {VERTICAL_TITLE_MAX_CHARS_PER_LINE})")
    parser.add_argument("--title-box-color", default="black", help="Highlighted box color behind the title on vertical clips (default: black)")
    parser.add_argument("--vertical-logo-width", type=int, default=VERTICAL_LOGO_WIDTH, help=f"Logo width in pixels for vertical clips (default: {VERTICAL_LOGO_WIDTH})")
    parser.add_argument("--vertical-logo-margin-bottom", type=int, default=VERTICAL_LOGO_MARGIN_BOTTOM, help=f"Distance from the video's own bottom edge to the LOGO'S OWN BOTTOM EDGE, for vertical clips - raise this to clear more space for Instagram's own username/caption overlay (default: {VERTICAL_LOGO_MARGIN_BOTTOM})")
    parser.add_argument("--logo-odd", default=DEFAULT_LOGO_ODD, help="Logo PNG used for odd-numbered clips")
    parser.add_argument("--logo-even", default=DEFAULT_LOGO_EVEN, help="Logo PNG used for even-numbered clips")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.is_dir():
        sys.exit(f"Input folder not found: {args.input}")
    if not args.titles.exists():
        sys.exit(f"Titles file not found: {args.titles}")

    logo_odd, logo_even = Path(args.logo_odd), Path(args.logo_even)
    if not logo_odd.exists():
        sys.exit(f"--logo-odd file not found: {logo_odd}")
    if not logo_even.exists():
        sys.exit(f"--logo-even file not found: {logo_even}")

    titles = parse_titles_file(args.titles)
    if not titles:
        sys.exit(f"No usable titles parsed from {args.titles} - check the file format (see --help).")

    videos = sorted(p for p in args.input.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        sys.exit(f"No video files found in {args.input}")

    matched = []
    for video_path in videos:
        num = extract_number(video_path.stem)
        if num is None:
            print(f"  SKIP {video_path.name}: no number found in the filename")
            continue
        if num not in titles:
            print(f"  SKIP {video_path.name} (#{num}): no matching title in {args.titles.name}")
            continue
        matched.append((num, video_path))

    if not matched:
        sys.exit("No videos matched a title - check that filenames and titles.txt use the same clip numbers.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_gpu = not args.no_gpu and gpu_utils.has_nvenc()

    print(f"Matched {len(matched)}/{len(videos)} video(s) to a title\n")
    failures = []
    for i, (num, video_path) in enumerate(matched, start=1):
        title = titles[num]
        logo_path = logo_odd if num % 2 == 1 else logo_even
        try:
            output_path, horizontal = process_video(video_path, title, logo_path, args.output_dir, use_gpu, args)
            print(f"[{i}/{len(matched)}] #{num} {video_path.name} ({'horizontal' if horizontal else 'vertical'}, {logo_path.stem}) -> {title[:60]!r}")
            print(f"    -> {output_path}")
        except Exception as e:
            print(f"[{i}/{len(matched)}] #{num} {video_path.name} FAILED: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(matched)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
