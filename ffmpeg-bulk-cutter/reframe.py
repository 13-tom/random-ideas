#!/usr/bin/env python3
"""Crop a video (or a whole folder of clips) to a fixed aspect ratio for
Instagram Reels/Stories (9:16 vertical) or feed posts/carousels (1:1 square).

Usage:
    python reframe.py clips/intro.mp4 --aspect vertical
    python reframe.py clips -o reframed --aspect square
    python reframe.py clips -o reframed --aspect vertical --track-faces

By default this does a CENTERED crop - works well when the speaker/subject
is roughly centered in frame (typical talking-head footage), but it won't
follow a moving subject.

--track-faces switches to smart subject-tracking: it detects faces across
the clip (MediaPipe) and pans the crop window to follow the largest face,
smoothed over time. Falls back to a static center crop automatically if no
faces are found. This is CPU-only (no GPU acceleration for the detection
step itself) and decodes the video twice, so it's noticeably slower than
the static crop - budget more time for longer clips. Requires
opencv-python-headless + mediapipe (see requirements.txt).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# (crop filter expression, output resolution) per aspect ratio.
# crop expressions assume a landscape source (width >= target); ffmpeg's
# crop filter centers by default when x/y are omitted.
ASPECT_PRESETS = {
    "square": ("crop='min(iw,ih)':'min(iw,ih)'", "1080:1080"),
    "vertical": ("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)'", "1080:1920"),
}


def reframe_video(input_path: Path, output_path: Path, aspect: str, use_gpu: bool = False):
    crop_expr, target_res = ASPECT_PRESETS[aspect]
    vf = f"{crop_expr},scale={target_res}"
    base_cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vf", vf]

    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        print("  GPU encode failed at runtime, falling back to CPU (libx264)")

    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "copy", str(output_path)]
    subprocess.run(cpu_cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("reframed"), help="Where to write reframed videos (default: ./reframed)")
    parser.add_argument("--aspect", choices=["square", "vertical"], required=True, help="square = 1:1 (feed/carousel), vertical = 9:16 (Reels/Stories)")
    parser.add_argument("--track-faces", action="store_true", help="Smart subject-tracking crop instead of a static center crop (see module docstring)")
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

    if args.track_faces:
        import face_tracking
        target_res = ASPECT_PRESETS[args.aspect][1]
        use_gpu = not args.no_gpu and gpu_utils.nvenc_works()
        for i, video_path in enumerate(videos, start=1):
            output_path = args.output_dir / video_path.name
            print(f"[{i}/{len(videos)}] {video_path.name} -> {args.aspect} (tracking faces)  =>  {output_path}")
            face_tracking.track_and_crop(video_path, output_path, args.aspect, target_res, use_gpu, reframe_video)
    else:
        use_gpu = not args.no_gpu and gpu_utils.has_nvenc()
        for i, video_path in enumerate(videos, start=1):
            output_path = args.output_dir / video_path.name
            print(f"[{i}/{len(videos)}] {video_path.name} -> {args.aspect}  =>  {output_path}")
            reframe_video(video_path, output_path, args.aspect, use_gpu)

    print(f"\nDone. {len(videos)} video(s) written to {args.output_dir}/")


if __name__ == "__main__":
    main()
