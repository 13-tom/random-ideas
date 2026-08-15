#!/usr/bin/env python3
"""Stamp a PNG logo onto a video (or a whole folder of videos), at a fixed
position and size - a plain watermark/branding pass, nothing else. Doesn't
touch aspect ratio, resolution, or captions - whatever the source video
already is, that's what comes out, just with the logo overlaid on top.

Use PNG for the logo, not JPG - PNG supports a transparent background (an
alpha channel), so the logo composites as a clean cutout. A JPG logo would
come with an opaque rectangle around it (JPG has no transparency), which
looks wrong here.

You have 5 logos ready: register each one as a named preset in
LOGO_PRESETS below (just add a line - name -> file path), then pick
between them per-run with --logo <name>. --logo also accepts a raw file
path directly, so presets are optional convenience, not required.

Usage:
    python add_logo.py clip.mp4 -o branded.mp4 --logo brand1
    python add_logo.py clips/ -o branded_clips --logo brand2
    python add_logo.py clip.mp4 -o branded.mp4 --logo /path/to/any_logo.png
    python add_logo.py clips/ -o out --logo brand1 --logo-width 300 --logo-x 80 --logo-y 40
"""
import argparse
import shutil
import sys
from pathlib import Path

import gpu_utils
from ffmpeg_utils import get_media_duration
from template_compose import _run_with_gpu_fallback

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
LOGO_EXTENSIONS = {".png"}

# Logo assets live alongside this script (in logos/), not at some
# machine-specific path - resolved via __file__ so it works regardless of
# where the repo is cloned/run from.
LOGOS_DIR = Path(__file__).resolve().parent / "logos"

# ============================================================================
# LOGO PRESETS - register your logos here (name -> file path), then pick
# one per run with --logo <name>. Add/remove/rename entries freely - this
# is just a lookup table, nothing else in the file needs to change.
# ============================================================================

LOGO_PRESETS = {
    "aieverymorning": str(LOGOS_DIR / "aieverymorning.png"),
    "itfeelsai": str(LOGOS_DIR / "itfeelsai.png"),
    # short aliases for the same two logos
    "brand1": str(LOGOS_DIR / "aieverymorning.png"),
    "brand2": str(LOGOS_DIR / "itfeelsai.png"),
    # "brand3": "/path/to/logo3.png",
    # "brand4": "/path/to/logo4.png",
    # "brand5": "/path/to/logo5.png",
}

# ============================================================================
# DEFAULT SIZE/POSITION - edit these directly, or override per-run with
# --logo-width/--logo-x/--logo-y (see --help) without touching the file.
# In pixels, relative to the source video's own frame (not a fixed canvas -
# this script doesn't resize/recompose the video at all), so re-check these
# if your clips vary a lot in resolution.
# ============================================================================

DEFAULT_LOGO_WIDTH = 240                             # height is scaled automatically to preserve the logo's own aspect ratio
DEFAULT_LOGO_X = 40                                  # distance from the video's LEFT edge
DEFAULT_LOGO_Y = 40                                  # distance from the video's TOP edge

# ============================================================================


def _resolve_logo_path(logo: str) -> Path:
    if logo in LOGO_PRESETS:
        path = Path(LOGO_PRESETS[logo])
    else:
        path = Path(logo)
    if not path.exists():
        presets = ", ".join(sorted(LOGO_PRESETS)) or "(none registered yet - edit LOGO_PRESETS in add_logo.py)"
        sys.exit(f"--logo {logo!r} isn't a known preset or an existing file path. Known presets: {presets}")
    if path.suffix.lower() not in LOGO_EXTENSIONS:
        print(f"    WARNING: {path.name} isn't a .png - use PNG for a transparent background, "
              "otherwise the logo will show up with a solid rectangle around it.")
    return path


def add_logo(input_path: Path, logo_path: Path, output_path: Path, use_gpu: bool,
              logo_width: int, logo_x: int, logo_y: int):
    # -shortest alone doesn't reliably terminate a -loop 1 still-image
    # input's duration is effectively undefined, and confirmed (via a
    # hung real encode) that -shortest can let the output run far past
    # the real video's length. Passing -t explicitly, from the real
    # source duration, bounds it correctly regardless.
    duration = get_media_duration(input_path)
    filter_complex = (
        f"[1:v]scale={logo_width}:-1[logo];"
        f"[0:v][logo]overlay=x={logo_x}:y={logo_y}[outv]"
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
        ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)],
        ["-c:v", "libx264", "-c:a", "copy", str(output_path)],
        use_gpu,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("branded"), help="Where to write logo'd videos (default: ./branded)")
    parser.add_argument("--logo", required=True, help=f"Which logo to use - either a preset name from LOGO_PRESETS in this file, or a raw path to a PNG. Known presets: {', '.join(sorted(LOGO_PRESETS)) or '(none registered yet)'}")
    parser.add_argument("--logo-width", type=int, default=DEFAULT_LOGO_WIDTH, help=f"Logo width in pixels - height is scaled automatically to preserve its aspect ratio (default: {DEFAULT_LOGO_WIDTH})")
    parser.add_argument("--logo-x", type=int, default=DEFAULT_LOGO_X, help=f"Logo's distance from the video's LEFT edge, in pixels (default: {DEFAULT_LOGO_X})")
    parser.add_argument("--logo-y", type=int, default=DEFAULT_LOGO_Y, help=f"Logo's distance from the video's TOP edge, in pixels (default: {DEFAULT_LOGO_Y})")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")
    logo_path = _resolve_logo_path(args.logo)

    if args.input.is_dir():
        videos = sorted(p for p in args.input.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    else:
        videos = [args.input]
    if not videos:
        sys.exit(f"No video files found in {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_gpu = not args.no_gpu and gpu_utils.has_nvenc()

    print(f"Using logo: {logo_path}")
    failures = []
    for i, video_path in enumerate(videos, start=1):
        output_path = args.output_dir / video_path.name
        print(f"[{i}/{len(videos)}] {video_path.name}  =>  {output_path}")
        try:
            add_logo(video_path, logo_path, output_path, use_gpu, args.logo_width, args.logo_x, args.logo_y)
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
