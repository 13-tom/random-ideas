#!/usr/bin/env python3
"""Cut out silent gaps from a video - jump-cut editing like Descript/CapCut
auto-cut. Detects silence, then splices the remaining spoken segments
together into a new, shorter video with a continuous timeline.

Run this BEFORE captioning, not after: since this changes the video's
timeline (removes chunks of time), any captions generated from the
ORIGINAL video would no longer line up. Transcribe the OUTPUT of this
script instead (add_subtitles.py / template_compose.py / run_pipeline.py
--remove-silence) - its timestamps are naturally correct for the new,
shorter timeline, no remapping needed.

Usage:
    python remove_silence.py clip.mp4 -o jumpcut.mp4
    python remove_silence.py clips/ -o jumpcut_clips
    python remove_silence.py clips/ -o jumpcut_clips --min-silence 0.4 --padding 0.1
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils
from add_subtitles import _detect_silences
from ffmpeg_utils import get_media_duration

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
DEFAULT_MIN_SILENCE = 0.5   # seconds - shorter gaps are natural speech pauses, left alone
DEFAULT_PADDING = 0.12      # seconds kept just before/after each spoken segment so words don't get clipped
DEFAULT_NOISE_DB = "-35dB"


def _keep_ranges(duration: float, silences: list[tuple[float, float]], padding: float) -> list[tuple[float, float]]:
    """The complement of the silent ranges - what actually stays in the
    output - with a little padding kept around each spoken segment so
    words aren't abruptly clipped at the cut points."""
    ranges = []
    cursor = 0.0
    for s, e in silences:
        seg_end = min(s + padding, duration)
        if seg_end > cursor:
            ranges.append((cursor, seg_end))
        cursor = max(e - padding, seg_end)
    if cursor < duration:
        ranges.append((cursor, duration))

    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _select_expr(ranges: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in ranges)


def remove_silence(input_path: Path, output_path: Path, use_gpu: bool,
                    min_silence: float, padding: float, noise_db: str) -> tuple[float, float]:
    """Returns (original_duration, new_duration)."""
    duration = get_media_duration(input_path)
    silences = _detect_silences(input_path, noise_db=noise_db, min_duration=min_silence)

    if not silences:
        shutil.copy(input_path, output_path)
        return duration, duration

    ranges = _keep_ranges(duration, silences, padding)
    expr = _select_expr(ranges)
    new_duration = sum(e - s for s, e in ranges)

    vf = f"select='{expr}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{expr}',asetpts=N/SR/TB"
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(input_path), "-vf", vf, "-af", af]

    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "aac", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return duration, new_duration
        print("  GPU encode failed at runtime, falling back to CPU (libx264)")

    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "aac", str(output_path)]
    subprocess.run(cpu_cmd, check=True)
    return duration, new_duration


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("jumpcut"), help="Where to write the cut videos (default: ./jumpcut)")
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE, help=f"Minimum gap duration (seconds) to actually cut - shorter pauses are left alone as natural speech rhythm (default: {DEFAULT_MIN_SILENCE})")
    parser.add_argument("--padding", type=float, default=DEFAULT_PADDING, help=f"Seconds of audio kept just before/after each spoken segment so words aren't clipped at the cut (default: {DEFAULT_PADDING})")
    parser.add_argument("--noise-db", default=DEFAULT_NOISE_DB, help=f"Volume threshold below which audio counts as silence (default: {DEFAULT_NOISE_DB})")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
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
    use_gpu = not args.no_gpu and gpu_utils.has_nvenc()

    for i, video_path in enumerate(videos, start=1):
        output_path = args.output_dir / video_path.name
        print(f"[{i}/{len(videos)}] {video_path.name}...")
        try:
            old_dur, new_dur = remove_silence(video_path, output_path, use_gpu, args.min_silence, args.padding, args.noise_db)
            cut = old_dur - new_dur
            pct = (cut / old_dur * 100) if old_dur else 0
            print(f"    {old_dur:.1f}s -> {new_dur:.1f}s (removed {cut:.1f}s, {pct:.0f}%)  =>  {output_path}")
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")

    print(f"\nDone. Output in {args.output_dir}/")


if __name__ == "__main__":
    main()
