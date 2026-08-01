"""Smart subject-tracking crop: samples face positions across a clip with
MediaPipe, smooths the path, and crops each frame to follow the subject
instead of a fixed centered window. Falls back to a static center crop if
no faces are found anywhere in the clip.

Requires opencv-python-headless + mediapipe (see requirements.txt) - these
are optional, heavier dependencies only needed for reframe.py --track-faces.
"""
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
FACE_MODEL_CACHE = Path.home() / ".cache" / "ffmpeg-bulk-cutter" / "blaze_face_short_range.tflite"

SAMPLE_INTERVAL_SEC = 0.4
SMOOTHING_WINDOW = 7


def _get_model_path() -> Path:
    if not FACE_MODEL_CACHE.exists():
        FACE_MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("  Downloading face detection model (one-time, ~230KB)...")
        urlretrieve(FACE_MODEL_URL, FACE_MODEL_CACHE)
    return FACE_MODEL_CACHE


@lru_cache(maxsize=1)
def _load_detector():
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    base_options = mp_python.BaseOptions(model_asset_path=str(_get_model_path()))
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
    return vision.FaceDetector.create_from_options(options), mp


def _detect_best(detector, mp, rgb_array):
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_array)
    result = detector.detect(mp_image)
    if not result.detections:
        return None
    # Largest face = assume main subject (closest to camera / speaking).
    return max(result.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height)


def _tile_positions(dim_size: int, tile_size: int, stride: int) -> list[int]:
    if tile_size >= dim_size:
        return [0]
    positions = list(range(0, dim_size - tile_size + 1, stride))
    if positions[-1] != dim_size - tile_size:
        positions.append(dim_size - tile_size)
    return positions


def _detect_face_center(detector, mp, frame_bgr):
    import cv2
    height, width = frame_bgr.shape[:2]
    rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    best = _detect_best(detector, mp, rgb)
    if best is not None:
        bbox = best.bounding_box
        return (bbox.origin_x + bbox.width / 2, bbox.origin_y + bbox.height / 2)

    # BlazeFace needs a face to occupy roughly half of its input to detect
    # reliably - confirmed empirically: a face at 50% of a square crop was
    # detected, one at 39% was not. So full-frame detection misses faces
    # in typical medium/wide shots (a normal talking-head webcam framing,
    # not just a tight close-up). Search progressively smaller square
    # tiles until the face is found, only when the full-frame pass fails.
    short_side = min(width, height)
    for scale in (0.55, 0.35):
        tile_size = max(64, int(short_side * scale))
        stride = max(1, tile_size // 2)
        for y0 in _tile_positions(height, tile_size, stride):
            for x0 in _tile_positions(width, tile_size, stride):
                tile = np.ascontiguousarray(rgb[y0:y0 + tile_size, x0:x0 + tile_size])
                det = _detect_best(detector, mp, tile)
                if det is not None:
                    bbox = det.bounding_box
                    return (x0 + bbox.origin_x + bbox.width / 2, y0 + bbox.origin_y + bbox.height / 2)
    return None


def crop_dimensions(aspect: str, src_w: int, src_h: int) -> tuple[int, int]:
    if aspect == "square":
        size = min(src_w, src_h)
        crop_w = crop_h = size
    else:  # vertical
        crop_h = src_h
        crop_w = min(src_w, round(src_h * 9 / 16))
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2
    return crop_w, crop_h


def _build_smoothed_path(samples, total_frames):
    """samples: [(frame_idx, (cx,cy) or None), ...]. Returns a per-frame
    list of (cx,cy), interpolating across gaps and smoothing with a moving
    average to avoid jittery panning; or None if no faces were found at
    all in the clip."""
    known = [(idx, c) for idx, c in samples if c is not None]
    if not known:
        return None
    xs = [k[0] for k in known]
    cxs = [k[1][0] for k in known]
    cys = [k[1][1] for k in known]
    frame_indices = np.arange(total_frames)
    # np.interp holds the first/last known value outside the sampled range,
    # so positions before the first detection / after the last one stay put
    # instead of snapping somewhere odd.
    interp_cx = np.interp(frame_indices, xs, cxs)
    interp_cy = np.interp(frame_indices, xs, cys)

    kernel = np.ones(SMOOTHING_WINDOW) / SMOOTHING_WINDOW
    pad = SMOOTHING_WINDOW // 2
    smooth_cx = np.convolve(np.pad(interp_cx, pad, mode="edge"), kernel, mode="valid")[:total_frames]
    smooth_cy = np.convolve(np.pad(interp_cy, pad, mode="edge"), kernel, mode="valid")[:total_frames]
    return list(zip(smooth_cx, smooth_cy))


def track_and_crop(input_path: Path, output_path: Path, aspect: str, target_res: str, use_gpu: bool,
                    static_crop_fallback) -> bool:
    """Returns True if smart tracking was used, False if it fell back to a
    static center crop via static_crop_fallback(input_path, output_path,
    aspect, use_gpu)."""
    try:
        import cv2
    except ImportError:
        sys.exit("opencv-python-headless / mediapipe not installed. Run: pip install -r requirements.txt")

    detector, mp = _load_detector()

    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample_interval_frames = max(1, round(fps * SAMPLE_INTERVAL_SEC))

    # Pass 1: sample face positions across the clip.
    samples = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_interval_frames == 0:
            samples.append((frame_idx, _detect_face_center(detector, mp, frame)))
        frame_idx += 1
    cap.release()
    total_frames = frame_idx

    path = _build_smoothed_path(samples, total_frames)
    if path is None:
        print("  No faces detected anywhere in this clip, falling back to center crop")
        static_crop_fallback(input_path, output_path, aspect, use_gpu)
        return False

    crop_w, crop_h = crop_dimensions(aspect, src_w, src_h)

    # Pass 2: crop each frame following the smoothed path, piping raw
    # frames into ffmpeg for encoding (keeps quality/GPU-encode consistent
    # with the rest of the pipeline instead of using OpenCV's own encoder).
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{crop_w}x{crop_h}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(input_path),
        "-map", "0:v", "-map", "1:a?",
        "-vf", f"scale={target_res}",
        "-c:v", "h264_nvenc" if use_gpu else "libx264", "-c:a", "copy",
        "-shortest", str(output_path),
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    cap = cv2.VideoCapture(str(input_path))
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        cx, cy = path[frame_idx] if frame_idx < len(path) else (src_w / 2, src_h / 2)
        x = int(min(max(cx - crop_w / 2, 0), src_w - crop_w))
        y = int(min(max(cy - crop_h / 2, 0), src_h - crop_h))
        cropped = frame[y:y + crop_h, x:x + crop_w]
        proc.stdin.write(cropped.tobytes())
        frame_idx += 1
    cap.release()
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode} while encoding the tracked crop")
    return True
