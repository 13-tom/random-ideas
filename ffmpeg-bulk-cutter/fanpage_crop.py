"""Fanpage-style tracking crop: crops to whoever's on screen, automatically
switching between a tight single-person framing and a wider crop that fits
everyone as people enter/leave the shot - a single smoothed pass, not a
separate "detect count then pick a mode" step.

Tuned deliberately tighter/steadier than face_tracking.py's general
--track-faces mode: closer zoom on a lone subject, a slower/steadier pan,
and a bigger deadzone (so it holds still unless the subject truly moves),
matching a calmer fanpage/clip-account edit instead of an energetic vlog
pan. See SINGLE_ZOOM / SMOOTHING_WINDOW_SEC / DEADZONE_FRAC below to
retune.

Only exposes one entry point, fanpage_track_and_crop(), with the same call
shape as face_tracking.track_and_crop() so it's a drop-in alternative
(see reframe.py --track-mode fanpage).
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

import gpu_utils
from face_tracking import (
    HEADROOM_FRACTION,
    SAMPLE_INTERVAL_SEC,
    _detect_faces_in_frame,
    _load_landmarker,
    crop_dimensions,
)

# Tighter than face_tracking.py's TRACK_ZOOM (0.72) - a lone subject reads
# closer/more "in your face", matching typical fanpage clip framing.
SINGLE_ZOOM = 0.5
# Padding around a multi-person bounding box, as a multiplier of its raw
# span, so faces don't sit jammed against the crop edge.
GROUP_MARGIN = 1.35
# The tightest a multi-person crop is allowed to get, even if everyone
# happens to be standing right next to each other - keeps some minimum
# breathing room instead of framing as tight as the single-person case.
MIN_GROUP_ZOOM = SINGLE_ZOOM * 1.15
# How many of the most prominent (largest/closest to camera) faces to
# actually frame around. Extra background faces beyond this are ignored
# rather than pulling the crop wide open for someone barely in shot.
MAX_TRACKED_SUBJECTS = 2

# Slower/steadier pan than face_tracking.py's SMOOTHING_WINDOW_SEC (1.2s) -
# prioritizes stability over quickly chasing movement.
SMOOTHING_WINDOW_SEC = 2.5
# Bigger deadzone than face_tracking.py's DEADZONE_FRAC (0.025) - ignores
# more small movement before treating it as real motion to pan toward.
DEADZONE_FRAC = 0.05


def _group_target(faces, max_crop_w: int, max_crop_h: int):
    """faces: up to MAX_TRACKED_SUBJECTS most prominent (cx,cy,ratio,area)
    tuples for this sample. Returns (cx, cy, zoom) - zoom is a fraction of
    (max_crop_w, max_crop_h), same convention as face_tracking.py's
    TRACK_ZOOM (1.0 = the largest crop the aspect ratio allows, smaller =
    more zoomed in). A single face uses the fixed tight SINGLE_ZOOM; two+
    faces get a crop just big enough to contain all of them plus
    GROUP_MARGIN padding, clamped to [MIN_GROUP_ZOOM, 1.0]."""
    if len(faces) == 1:
        cx, cy, _, _ = faces[0]
        return cx, cy, SINGLE_ZOOM

    xs_min, xs_max, ys_min, ys_max = [], [], [], []
    for cx, cy, _, area in faces:
        half = math.sqrt(max(area, 1.0)) / 2
        xs_min.append(cx - half)
        xs_max.append(cx + half)
        ys_min.append(cy - half)
        ys_max.append(cy + half)

    span_w = (max(xs_max) - min(xs_min)) * GROUP_MARGIN
    span_h = (max(ys_max) - min(ys_min)) * GROUP_MARGIN
    zoom = max(span_w / max_crop_w, span_h / max_crop_h, MIN_GROUP_ZOOM)
    zoom = min(zoom, 1.0)
    cx = (min(xs_min) + max(xs_max)) / 2
    cy = (min(ys_min) + max(ys_max)) / 2
    return cx, cy, zoom


def _build_group_path(samples, total_frames: int, fps: float):
    """samples: [(frame_idx, (cx,cy,zoom) or None), ...]. Same
    interpolate + deadzone + smooth approach as face_tracking.py, but
    carries a per-frame zoom alongside position so panning AND the
    single<->multi-person crop size both ease smoothly together instead of
    jump-cutting the instant someone enters or leaves frame."""
    known = [(idx, v) for idx, v in samples if v is not None]
    if not known:
        return None

    frame_w_est = max(v[0] for _, v in known) + 1
    frame_h_est = max(v[1] for _, v in known) + 1
    threshold = DEADZONE_FRAC * math.hypot(frame_w_est, frame_h_est)

    held = None
    deadzoned = []
    for idx, (cx, cy, zoom) in known:
        if held is not None and math.hypot(cx - held[0], cy - held[1]) < threshold:
            deadzoned.append((idx, held[0], held[1], zoom))
        else:
            held = (cx, cy)
            deadzoned.append((idx, cx, cy, zoom))

    xs = [d[0] for d in deadzoned]
    cxs = [d[1] for d in deadzoned]
    cys = [d[2] for d in deadzoned]
    zooms = [d[3] for d in deadzoned]
    frame_indices = np.arange(total_frames)
    interp_cx = np.interp(frame_indices, xs, cxs)
    interp_cy = np.interp(frame_indices, xs, cys)
    interp_zoom = np.interp(frame_indices, xs, zooms)

    window = max(1, round(fps * SMOOTHING_WINDOW_SEC))
    kernel = np.ones(window) / window
    pad = window // 2

    def _smooth(arr):
        return np.convolve(np.pad(arr, pad, mode="edge"), kernel, mode="valid")[:total_frames]

    return list(zip(_smooth(interp_cx), _smooth(interp_cy), _smooth(interp_zoom)))


def fanpage_track_and_crop(input_path: Path, output_path: Path, aspect, target_res: str, use_gpu: bool,
                            static_crop_fallback, try_gpu_detect: bool = False) -> bool:
    """Crops to whoever's on screen: a tight single-person framing when
    only one face is detected, automatically easing out to a wider crop
    that fits everyone when a second person is in frame, and back again
    when they leave - all in one smoothed pass.

    aspect: either a named key into reframe.ASPECT_RATIOS, or a raw
    (ratio_w, ratio_h) tuple for a one-off ratio (e.g. a template's own
    fixed video-box proportions) - see crop_dimensions().

    Returns True if smart tracking was used, False if it fell back to a
    static center crop via static_crop_fallback(input_path, output_path,
    aspect, use_gpu)."""
    try:
        import cv2
    except ImportError:
        sys.exit("opencv-python-headless / mediapipe not installed. Run: pip install -r requirements.txt")

    landmarker, mp = _load_landmarker(try_gpu_detect)

    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample_interval_frames = max(1, round(fps * SAMPLE_INTERVAL_SEC))

    max_crop_w, max_crop_h = crop_dimensions(aspect, src_w, src_h)

    def _sized(zoom: float) -> tuple[int, int]:
        w = max(2, int(max_crop_w * zoom))
        h = max(2, int(max_crop_h * zoom))
        return w - w % 2, h - h % 2

    # Pass 1: sample every face in frame (not reduced to one active
    # speaker like face_tracking.py's mouth-movement selection - this
    # pipeline frames by HOW MANY people are visible, not who's currently
    # talking).
    raw_samples = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_interval_frames == 0:
            raw_samples.append((frame_idx, _detect_faces_in_frame(landmarker, mp, frame)))
        frame_idx += 1
    cap.release()
    total_frames = frame_idx

    target_samples = []
    for idx, faces in raw_samples:
        if not faces:
            target_samples.append((idx, None))
            continue
        top_faces = sorted(faces, key=lambda f: -f[3])[:MAX_TRACKED_SUBJECTS]
        target_samples.append((idx, _group_target(top_faces, max_crop_w, max_crop_h)))

    path = _build_group_path(target_samples, total_frames, fps)
    if path is None:
        print("  No faces detected anywhere in this clip, falling back to center crop")
        static_crop_fallback(input_path, output_path, aspect, use_gpu)
        return False

    pipe_w, pipe_h = _sized(SINGLE_ZOOM)

    # Pass 2: crop each frame following the smoothed position+zoom path,
    # piping raw frames into ffmpeg for encoding (keeps quality/GPU-encode
    # consistent with the rest of the pipeline instead of using OpenCV's
    # own encoder).
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{pipe_w}x{pipe_h}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(input_path),
        "-map", "0:v", "-map", "1:a?",
        "-vf", f"scale={target_res}:flags=lanczos",
        "-c:v", gpu_utils.encoder_name() if use_gpu else "libx264", "-c:a", "copy",
        "-shortest", str(output_path),
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    cap = cv2.VideoCapture(str(input_path))
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx < len(path):
            cx, cy, zoom = path[frame_idx]
        else:
            cx, cy, zoom = src_w / 2, src_h / 2, SINGLE_ZOOM

        crop_w, crop_h = _sized(zoom)
        x = int(min(max(cx - crop_w / 2, 0), src_w - crop_w))
        y = int(min(max(cy - crop_h * HEADROOM_FRACTION, 0), src_h - crop_h))
        cropped = frame[y:y + crop_h, x:x + crop_w]
        if (crop_w, crop_h) != (pipe_w, pipe_h):
            cropped = cv2.resize(cropped, (pipe_w, pipe_h), interpolation=cv2.INTER_LANCZOS4)
        proc.stdin.write(cropped.tobytes())
        frame_idx += 1
    cap.release()
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode} while encoding the fanpage crop")
    return True
