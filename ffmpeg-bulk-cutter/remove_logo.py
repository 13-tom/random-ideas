#!/usr/bin/env python3
"""Remove the "Evolving AI" account-info block (avatar circle + name + blue
checkmark + @handle) that repost-bot templates burn onto a solid black
letterbox bar above the actual video content - for your own videos you
lost the source files for, re-downloaded from Instagram.

This ONLY works because of how that block sits on screen: it's on a flat,
pure-black bar (not overlaid on top of moving video pixels), with a
separate caption line below it, then the real video content below that.
That means there's no need for blur-prone inpainting at all - detect the
exact row-band the logo block occupies (it's always the topmost band of
non-black pixels, confirmed against your 2 sample videos), and repaint
that exact band with solid black. Since the true background really is
flat black, this comes out seamless - not an approximation.

The caption line below the logo, and the real video content below that,
are left completely untouched: detection stops at the first gap back to
pure black, which is exactly the bottom edge of the logo block.

If a video doesn't match this layout (e.g. the logo sits directly on top
of real video content, not a black bar), detection is refused rather than
guessed at - see verify_band() below. Run with --debug first on a new
video/batch: it saves a preview frame with the detected removal box drawn
on it, so you can sanity-check before trusting the real output.

Usage:
    python remove_logo.py clip.mp4 -o clean.mp4
    python remove_logo.py clips/ -o clean_clips
    python remove_logo.py clips/ -o clean_clips --debug   # preview only, no video output
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import gpu_utils
from ffmpeg_utils import get_media_duration
from template_compose import _run_with_gpu_fallback

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# ============================================================================
# DETECTION TUNING - edit these directly if a video's logo isn't being
# found reliably. All defaults were tuned against 2 real sample videos.
# ============================================================================

SAMPLE_TIME_SEC = 1.0          # which frame to inspect for the logo's position (assumed static for the whole clip)
ROW_BRIGHTNESS_THRESHOLD = 30  # a pixel counts as "non-black" if its brightest channel exceeds this (tolerates compression noise around true black)
ROW_CONTENT_THRESHOLD = 0.003  # a row counts as "has content" if at least this fraction of its width is non-black
REAL_VIDEO_ROW_FRACTION = 0.85 # a row is "real video content" (not text) if its non-black fraction exceeds this - text/logo rows never get this dense
MARGIN_ABOVE_CHECK = 15        # rows immediately above the detected band must be this many pixels of solid black, or detection is refused (sanity check that we're really in a letterbox)
BAND_PADDING = 3               # extra pixels painted above/below the detected band, in case of soft/antialiased text edges

# ============================================================================


def extract_frame(video_path: Path, t: float, out_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", "-update", "1", str(out_path)],
        check=True, capture_output=True,
    )


def detect_logo_band(frame: np.ndarray):
    """Returns (y0, y1, fill_rgb) for the topmost non-black row-band, or
    None if the frame doesn't look like it has a black-letterbox logo
    block at all (nothing to remove, or not safe to guess)."""
    h, w = frame.shape[:2]
    nonblack = frame.max(axis=2) > ROW_BRIGHTNESS_THRESHOLD
    frac = nonblack.mean(axis=1)

    y0 = None
    for y in range(h):
        if frac[y] > ROW_CONTENT_THRESHOLD:
            if frac[y] >= REAL_VIDEO_ROW_FRACTION:
                return None  # real video content starts immediately - no letterbox logo to find
            y0 = y
            break
    if y0 is None:
        return None  # frame is entirely black - nothing to do

    if y0 < MARGIN_ABOVE_CHECK or frac[max(0, y0 - MARGIN_ABOVE_CHECK):y0].max() > ROW_CONTENT_THRESHOLD:
        return None  # not enough solid black above the band to trust this is a real letterbox

    y1 = y0
    for y in range(y0, h):
        if frac[y] > ROW_CONTENT_THRESHOLD:
            if frac[y] >= REAL_VIDEO_ROW_FRACTION:
                return None  # the band ran straight into real video content with no gap - not a clean logo block, refuse
            y1 = y
        else:
            break
    y1 += 1  # exclusive end

    y0 = max(0, y0 - BAND_PADDING)
    y1 = min(h, y1 + BAND_PADDING)

    # Sample the true background color from the far corners of the band's
    # row range, rather than assuming pure #000 - a median of several
    # corner pixels is robust to a single noisy/compressed one.
    corners = [frame[y0, 0], frame[y0, w - 1], frame[y1 - 1, 0], frame[y1 - 1, w - 1]]
    fill_rgb = tuple(int(v) for v in np.median(corners, axis=0))
    return y0, y1, fill_rgb


def save_debug_preview(frame: np.ndarray, band, preview_path: Path):
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    if band:
        y0, y1, _ = band
        draw.rectangle((0, y0, img.width - 1, y1 - 1), outline=(255, 0, 0), width=3)
    img.save(preview_path)


def remove_logo(input_path: Path, output_path: Path, use_gpu: bool, band):
    y0, y1, fill_rgb = band
    duration = get_media_duration(input_path)
    r, g, b = fill_rgb
    filter_complex = f"[0:v]drawbox=x=0:y={y0}:w=iw:h={y1 - y0}:color=0x{r:02X}{g:02X}{b:02X}:t=fill[outv]"
    base_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?", "-t", str(duration),
    ]
    _run_with_gpu_fallback(
        base_cmd,
        ["-c:v", gpu_utils.encoder_name(), "-c:a", "copy", str(output_path)],
        ["-c:v", "libx264", "-c:a", "copy", str(output_path)],
        use_gpu,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("logo_removed"), help="Where to write cleaned videos (default: ./logo_removed)")
    parser.add_argument("--debug", action="store_true", help="Don't process video - just save a preview PNG per clip with the detected removal box drawn on it, so you can check it before trusting a real run")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if a GPU encoder (NVIDIA NVENC or Mac VideoToolbox) is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    if args.input.is_dir():
        videos = sorted(p for p in args.input.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    else:
        videos = [args.input]
    if not videos:
        sys.exit(f"No video files found in {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_gpu = not args.no_gpu and gpu_utils.gpu_available()

    failures = []
    skipped = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, video_path in enumerate(videos, start=1):
            print(f"[{i}/{len(videos)}] {video_path.name}")
            frame_path = Path(tmp) / "frame.png"
            try:
                extract_frame(video_path, SAMPLE_TIME_SEC, frame_path)
                frame = np.array(Image.open(frame_path).convert("RGB"))
            except Exception as e:
                print(f"    FAILED to read a frame: {e}")
                failures.append(video_path.name)
                continue

            band = detect_logo_band(frame)

            if args.debug:
                preview_path = args.output_dir / f"{video_path.stem}_debug.png"
                save_debug_preview(frame, band, preview_path)
                status = f"band y={band[0]}-{band[1]}, fill={band[2]}" if band else "NOT DETECTED"
                print(f"    {status}  ->  {preview_path}")
                continue

            if band is None:
                print("    Couldn't confidently detect a letterbox logo block - skipping (run with --debug to see why)")
                skipped.append(video_path.name)
                continue

            y0, y1, fill_rgb = band
            print(f"    Removing rows {y0}-{y1} (fill {fill_rgb})")
            output_path = args.output_dir / video_path.name
            try:
                remove_logo(video_path, output_path, use_gpu, band)
            except Exception as e:
                print(f"    FAILED: {e}")
                failures.append(video_path.name)

    if args.debug:
        print(f"\nDebug previews in {args.output_dir}/ - check the red boxes before running for real.")
        return

    print(f"\nDone. Output in {args.output_dir}/")
    if skipped:
        print(f"{len(skipped)} clip(s) skipped (no confident detection): {', '.join(skipped)}")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
