#!/usr/bin/env python3
"""Crop a video (or a whole folder of clips) to a fixed aspect ratio.

Available --aspect values:
    vertical   9:16   Reels / Stories / Shorts / TikTok    -> 1080x1920
    square     1:1    Feed post / carousel                 -> 1080x1080
    portrait   4:5    Instagram feed portrait (their own recommended ratio) -> 1080x1350
    landscape  16:9   YouTube / horizontal feed             -> 1920x1080

Usage:
    python reframe.py clips/intro.mp4 --aspect vertical
    python reframe.py clips -o reframed --aspect portrait
    python reframe.py clips -o reframed --aspect vertical --track-faces

By default this does a CENTERED crop - works well when the speaker/subject
is roughly centered in frame (typical talking-head footage), but it won't
follow a moving subject.

--track-faces switches to smart subject-tracking: it detects faces across
the clip (MediaPipe), and when more than one person is in frame, follows
whichever one is actively speaking (based on mouth movement over time, not
just face size). Falls back to a static center crop automatically if no
faces are found. Decodes the video twice (once to sample faces, once to
crop), so it's noticeably slower than the static crop - budget more time
for longer clips. Requires opencv-python-headless + mediapipe (see
requirements.txt).

--track-mode controls how it uses that tracking:
    dynamic (default) - pans to follow the subject, smoothed over a
                         multi-sample window with a deadzone for small
                         detection noise so a mostly-still subject doesn't
                         visibly shake.
    static             - detects faces the same way, but picks one fixed
                         crop position (median face location) for the
                         whole clip - literally zero panning, so zero
                         possible camera shake. Better than a plain
                         center crop (it's centered on wherever the
                         subject actually is, not the frame's geometric
                         center) but won't follow a subject that moves
                         around a lot.

Face detection runs on CPU by default - the model is tiny (a few ms/frame)
so a GPU wouldn't meaningfully speed it up, and MediaPipe's GPU delegate
support for desktop Python is inconsistent (especially on Windows). Pass
--gpu-detect to opportunistically try it anyway; it falls back to CPU
automatically if unavailable. Video encoding always uses the GPU already
(via --no-gpu to disable), regardless of this flag.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import gpu_utils

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# name -> (ratio_w, ratio_h). Crop expression and target resolution are
# both derived from this ratio - add an entry here to support another
# platform's aspect ratio, nothing else needs to change.
ASPECT_RATIOS = {
    "vertical": (9, 16),    # Reels / Stories / Shorts / TikTok
    "square": (1, 1),       # Feed post / carousel
    "portrait": (4, 5),     # Instagram's own recommended feed ratio
    "landscape": (16, 9),   # YouTube / horizontal feed
}


def _target_resolution(ratio_w: int, ratio_h: int) -> str:
    if ratio_w <= ratio_h:
        width, height = 1080, round(1080 * ratio_h / ratio_w)
    else:
        height, width = 1080, round(1080 * ratio_w / ratio_h)
    width -= width % 2  # even dimensions required by most encoders
    height -= height % 2
    return f"{width}:{height}"


# (crop filter expression, output resolution) per aspect ratio. Crop
# expressions assume a landscape source (width >= target); ffmpeg's crop
# filter centers by default when x/y are omitted.
ASPECT_PRESETS = {
    name: (f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})'", _target_resolution(w, h))
    for name, (w, h) in ASPECT_RATIOS.items()
}


def reframe_video(input_path: Path, output_path: Path, aspect: str, use_gpu: bool = False):
    crop_expr, target_res = ASPECT_PRESETS[aspect]
    vf = f"{crop_expr},scale={target_res}"
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(input_path), "-vf", vf]

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
    parser.add_argument("--aspect", choices=list(ASPECT_RATIOS), required=True, help="vertical = 9:16 (Reels/Stories/Shorts), square = 1:1 (feed/carousel), portrait = 4:5 (IG feed), landscape = 16:9 (YouTube)")
    parser.add_argument("--track-faces", action="store_true", help="Smart subject-tracking crop instead of a static center crop (see module docstring)")
    parser.add_argument("--track-mode", choices=["dynamic", "static"], default="dynamic", help="dynamic = pan to follow the subject (default). static = one fixed, face-informed crop position for the whole clip - no panning, so no possible camera shake. Only relevant with --track-faces.")
    parser.add_argument("--zoom-on-gesture", action="store_true", help="Ease out to a wider crop when a hand is detected (gesturing) so it doesn't get clipped by the tight face crop, then ease back in once the hand is gone. Only relevant with --track-faces --track-mode dynamic.")
    parser.add_argument("--gpu-detect", action="store_true", help="Opportunistically try MediaPipe's GPU delegate for face detection (experimental, falls back to CPU automatically). Only relevant with --track-faces.")
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
            face_tracking.track_and_crop(video_path, output_path, args.aspect, target_res, use_gpu, reframe_video, args.gpu_detect, args.track_mode, args.zoom_on_gesture)
    else:
        use_gpu = not args.no_gpu and gpu_utils.has_nvenc()
        for i, video_path in enumerate(videos, start=1):
            output_path = args.output_dir / video_path.name
            print(f"[{i}/{len(videos)}] {video_path.name} -> {args.aspect}  =>  {output_path}")
            reframe_video(video_path, output_path, args.aspect, use_gpu)

    print(f"\nDone. {len(videos)} video(s) written to {args.output_dir}/")


if __name__ == "__main__":
    main()
