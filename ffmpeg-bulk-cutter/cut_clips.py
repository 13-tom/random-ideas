#!/usr/bin/env python3
"""Bulk-cut a video into clips using a CSV list of start,end timestamps.

Usage:
    python cut_clips.py input.mp4 timestamps.csv -o output_dir

CSV format (no header required), one clip per row:
    start,end
    start,end,label
    00:01:23,00:01:45
    00:05:10,00:05:40,intro_recap
"""
import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils
from ffmpeg_utils import get_media_duration


def parse_timestamp(value: str) -> float:
    """Convert HH:MM:SS(.ms), MM:SS, or raw seconds into seconds."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) > 3:
        raise ValueError(f"Unrecognized timestamp: {value!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def format_timestamp(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def read_clips(csv_path: Path):
    clips = []
    with csv_path.open(newline="") as f:
        for line_num, row in enumerate(csv.reader(f), start=1):
            row = [cell.strip() for cell in row if cell.strip() != ""]
            if not row:
                continue
            if len(row) < 2:
                raise ValueError(f"{csv_path}:{line_num}: expected 'start,end[,label]', got {row}")
            start = parse_timestamp(row[0])
            end = parse_timestamp(row[1])
            if end <= start:
                raise ValueError(f"{csv_path}:{line_num}: end ({row[1]}) must be after start ({row[0]})")
            label = row[2] if len(row) > 2 else None
            clips.append((start, end, label))
    return clips


def validate_clips(clips, video_path: Path):
    """Raise ValueError listing any clip whose start is at/beyond the
    video's actual length, instead of letting ffmpeg silently write an
    empty file that fails confusingly downstream."""
    duration = get_media_duration(video_path)
    problems = [
        f"  clip {i} ({label or 'unlabeled'}): start {format_timestamp(start)} is at/after "
        f"the video's length ({format_timestamp(duration)})"
        for i, (start, end, label) in enumerate(clips, start=1)
        if start >= duration
    ]
    if problems:
        raise ValueError("Some timestamps are beyond the video's actual length:\n" + "\n".join(problems))


def _base_cut_cmd(input_path: Path, start: float, end: float) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-ss", format_timestamp(start),
        "-i", str(input_path),
        "-t", format_timestamp(end - start),
    ]
    # -ss before -i resets output timestamps to 0 at the seek point, so the
    # duration must be relative (-t end-start), not an absolute -to end.


def cut_clip(input_path: Path, start: float, end: float, output_path: Path, reencode: bool, use_gpu: bool = False):
    if not reencode:
        cmd = _base_cut_cmd(input_path, start, end) + ["-c", "copy", str(output_path)]
        subprocess.run(cmd, check=True)
        return

    if use_gpu:
        gpu_cmd = _base_cut_cmd(input_path, start, end) + ["-c:v", "h264_nvenc", "-c:a", "aac", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        print("  GPU encode failed at runtime, falling back to CPU (libx264)")

    cpu_cmd = _base_cut_cmd(input_path, start, end) + ["-c:v", "libx264", "-c:a", "aac", str(output_path)]
    subprocess.run(cpu_cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Source video file")
    parser.add_argument("timestamps", type=Path, help="CSV file with start,end[,label] rows")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("clips"), help="Where to write clips (default: ./clips)")
    parser.add_argument(
        "--reencode",
        action="store_true",
        help="Re-encode for frame-accurate cuts instead of fast stream copy "
             "(use this if clips start a bit early/late or with a black flash)",
    )
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU encoding even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input video not found: {args.input}")
    if not args.timestamps.exists():
        sys.exit(f"Timestamps CSV not found: {args.timestamps}")

    try:
        clips = read_clips(args.timestamps)
        if not clips:
            sys.exit("No clips found in CSV.")
        validate_clips(clips, args.input)
    except ValueError as e:
        sys.exit(str(e))

    use_gpu = args.reencode and not args.no_gpu and gpu_utils.has_nvenc()
    if args.reencode:
        print(f"Re-encoding with {'GPU (h264_nvenc)' if use_gpu else 'CPU (libx264)'}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.input.suffix

    for i, (start, end, label) in enumerate(clips, start=1):
        name = label if label else f"clip_{i:03d}"
        output_path = args.output_dir / f"{name}{suffix}"
        print(f"[{i}/{len(clips)}] {format_timestamp(start)} -> {format_timestamp(end)}  =>  {output_path}")
        cut_clip(args.input, start, end, output_path, args.reencode, use_gpu)

    print(f"\nDone. {len(clips)} clip(s) written to {args.output_dir}/")


if __name__ == "__main__":
    main()
