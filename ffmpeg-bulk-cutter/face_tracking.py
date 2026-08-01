"""Smart subject-tracking crop: samples face positions across a clip with
MediaPipe, figures out who's actively speaking when multiple people are in
frame (via mouth-movement over time, not just face size), smooths the
resulting path, and crops each frame to follow that subject instead of a
fixed centered window. Falls back to a static center crop if no faces are
found anywhere in the clip.

Requires opencv-python-headless + mediapipe (see requirements.txt) - these
are optional, heavier dependencies only needed for reframe.py --track-faces.
"""
import math
import subprocess
import sys
from collections import deque
from functools import lru_cache
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

from reframe import ASPECT_RATIOS

FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
FACE_MODEL_CACHE = Path.home() / ".cache" / "ffmpeg-bulk-cutter" / "face_landmarker.task"

SAMPLE_INTERVAL_SEC = 0.4
SMOOTHING_WINDOW = 7
MOUTH_HISTORY_LEN = 6
MAX_FACES = 5
# Mouth landmark indices in MediaPipe's 478-point face mesh: inner lip
# top/bottom (vertical gap = how open the mouth is) and left/right corners
# (mouth width, used to normalize the gap so it's scale-invariant).
MOUTH_TOP, MOUTH_BOTTOM, MOUTH_LEFT, MOUTH_RIGHT = 13, 14, 61, 291


def _get_model_path() -> Path:
    if not FACE_MODEL_CACHE.exists():
        FACE_MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("  Downloading face landmark model (one-time, ~3.7MB)...")
        urlretrieve(FACE_MODEL_URL, FACE_MODEL_CACHE)
    return FACE_MODEL_CACHE


@lru_cache(maxsize=1)
def _load_landmarker(try_gpu: bool):
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    model_path = str(_get_model_path())
    if try_gpu:
        try:
            base_options = mp_python.BaseOptions(model_asset_path=model_path, delegate=mp_python.BaseOptions.Delegate.GPU)
            options = vision.FaceLandmarkerOptions(base_options=base_options, num_faces=MAX_FACES, min_face_detection_confidence=0.5)
            landmarker = vision.FaceLandmarker.create_from_options(options)
            print("  Face detection: GPU delegate")
            return landmarker, mp
        except Exception:
            # MediaPipe's GPU delegate support for desktop Python (especially
            # Windows) is inconsistent - this model is tiny (a few ms/frame
            # on CPU anyway) so falling back costs little.
            print("  Face detection: GPU delegate unavailable, using CPU")
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = vision.FaceLandmarkerOptions(base_options=base_options, num_faces=MAX_FACES, min_face_detection_confidence=0.5)
    return vision.FaceLandmarker.create_from_options(options), mp


def _face_metrics(landmarks, width: int, height: int):
    """Returns (center_x, center_y, mouth_open_ratio, area) in pixel space."""
    xs = [p.x * width for p in landmarks]
    ys = [p.y * height for p in landmarks]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    area = (max(xs) - min(xs)) * (max(ys) - min(ys))

    top, bottom = landmarks[MOUTH_TOP], landmarks[MOUTH_BOTTOM]
    left, right = landmarks[MOUTH_LEFT], landmarks[MOUTH_RIGHT]
    gap = math.dist((top.x * width, top.y * height), (bottom.x * width, bottom.y * height))
    mouth_width = math.dist((left.x * width, left.y * height), (right.x * width, right.y * height)) or 1.0
    return cx, cy, gap / mouth_width, area


def _detect_all(landmarker, mp, rgb_array):
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_array)
    result = landmarker.detect(mp_image)
    h, w = rgb_array.shape[:2]
    return [_face_metrics(fl, w, h) for fl in result.face_landmarks]


def _tile_positions(dim_size: int, tile_size: int, stride: int) -> list[int]:
    if tile_size >= dim_size:
        return [0]
    positions = list(range(0, dim_size - tile_size + 1, stride))
    if positions[-1] != dim_size - tile_size:
        positions.append(dim_size - tile_size)
    return positions


def _merge_detections(detections, merge_dist: float):
    """Overlapping tiles see the same face more than once. Cluster
    detections whose centers are within merge_dist of each other (greedy,
    largest-area first - a tighter crop generally gives a more reliable
    landmark read), keeping one representative per cluster."""
    order = sorted(range(len(detections)), key=lambda i: -detections[i][3])
    used = [False] * len(detections)
    merged = []
    for i in order:
        if used[i]:
            continue
        used[i] = True
        cx, cy, ratio, area = detections[i]
        cluster_ratios = [ratio]
        for j in order:
            if used[j]:
                continue
            cx2, cy2, ratio2, _ = detections[j]
            if math.hypot(cx - cx2, cy - cy2) < merge_dist:
                used[j] = True
                cluster_ratios.append(ratio2)
        merged.append((cx, cy, sum(cluster_ratios) / len(cluster_ratios), area))
    return merged


def _detect_faces_in_frame(landmarker, mp, frame_bgr):
    """Returns a list of (cx, cy, mouth_ratio, area) in full-frame pixel
    coordinates - one entry per face found.

    The detector needs a face to occupy roughly half of its input to
    detect reliably (confirmed empirically: 50% of a crop was detected,
    39% was not), so a plain full-frame pass alone misses faces in
    ordinary medium shots - including a normal 2-person side-by-side
    framing, confirmed with a real test where full-frame detection found
    only one of two clearly visible faces. So tiled detection always runs
    (not just as a "zero faces found" fallback), merging results with the
    full-frame pass and deduplicating overlapping tile detections of the
    same face."""
    import cv2
    height, width = frame_bgr.shape[:2]
    rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    all_detections = list(_detect_all(landmarker, mp, rgb))
    short_side = min(width, height)
    tile_size = max(64, int(short_side * 0.55))
    stride = max(1, tile_size // 2)
    for y0 in _tile_positions(height, tile_size, stride):
        for x0 in _tile_positions(width, tile_size, stride):
            tile = np.ascontiguousarray(rgb[y0:y0 + tile_size, x0:x0 + tile_size])
            for cx, cy, ratio, area in _detect_all(landmarker, mp, tile):
                all_detections.append((x0 + cx, y0 + cy, ratio, area))

    if not all_detections:
        # Still nothing - try a tighter zoom for a single subject smaller
        # than even the tile pass above can resolve (e.g. one person far
        # from camera in a wide shot).
        tile_size = max(64, int(short_side * 0.35))
        stride = max(1, tile_size // 2)
        for y0 in _tile_positions(height, tile_size, stride):
            for x0 in _tile_positions(width, tile_size, stride):
                tile = np.ascontiguousarray(rgb[y0:y0 + tile_size, x0:x0 + tile_size])
                tile_faces = _detect_all(landmarker, mp, tile)
                if tile_faces:
                    cx, cy, ratio, area = tile_faces[0]
                    return [(x0 + cx, y0 + cy, ratio, area)]
        return []

    return _merge_detections(all_detections, merge_dist=0.08 * math.hypot(width, height))


def crop_dimensions(aspect: str, src_w: int, src_h: int) -> tuple[int, int]:
    ratio_w, ratio_h = ASPECT_RATIOS[aspect]
    crop_w = min(src_w, round(src_h * ratio_w / ratio_h))
    crop_h = min(src_h, round(src_w * ratio_h / ratio_w))
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2
    return crop_w, crop_h


class _Identity:
    __slots__ = ("id", "cx", "cy", "mouth_history")

    def __init__(self, id_, cx, cy):
        self.id = id_
        self.cx = cx
        self.cy = cy
        self.mouth_history = deque(maxlen=MOUTH_HISTORY_LEN)

    def activity(self) -> float:
        """How much this person's mouth is currently oscillating - a
        talking mouth opens/closes repeatedly, a quiet one stays roughly
        constant. Mean frame-to-frame movement (not max-min range) so a
        single old jump that's since gone flat doesn't keep scoring as
        "active" - it needs to keep moving to count."""
        if len(self.mouth_history) < 2:
            return 0.0
        diffs = [abs(b - a) for a, b in zip(self.mouth_history, list(self.mouth_history)[1:])]
        return sum(diffs) / len(diffs)


def _select_active_speaker(samples, frame_w: int, frame_h: int):
    """samples: [(frame_idx, [(cx,cy,mouth_ratio,area), ...]), ...] - one
    or more faces per sampled frame. Returns [(frame_idx, (cx,cy) or None)]
    following whichever person is actively speaking, using nearest-position
    matching to track identities across samples and mouth-movement variance
    to pick the speaker. With only one face throughout, this reduces to
    simply tracking that face - no speaker selection needed."""
    identities: list[_Identity] = []
    next_id = 0
    max_match_dist = 0.2 * math.hypot(frame_w, frame_h)
    active_id = None
    output = []

    for frame_idx, faces in samples:
        if not faces:
            output.append((frame_idx, None))
            continue

        unmatched = list(identities)
        current_faces = []
        for cx, cy, ratio, area in faces:
            best, best_dist = None, max_match_dist
            for ident in unmatched:
                d = math.hypot(ident.cx - cx, ident.cy - cy)
                if d < best_dist:
                    best, best_dist = ident, d
            if best is None:
                best = _Identity(next_id, cx, cy)
                next_id += 1
                identities.append(best)
            else:
                unmatched.remove(best)
            best.cx, best.cy = cx, cy
            best.mouth_history.append(ratio)
            current_faces.append(best)

        if len(current_faces) == 1:
            chosen = current_faces[0]
        else:
            ranked = sorted(current_faces, key=lambda i: i.activity(), reverse=True)
            top = ranked[0]
            current = next((i for i in current_faces if i.id == active_id), None)
            # Hysteresis: don't switch speakers unless the new candidate is
            # clearly more active than whoever we're currently following,
            # so we don't flicker between people on detection noise.
            if current is not None and current is not top and top.activity() < current.activity() * 1.3:
                chosen = current
            else:
                chosen = top

        active_id = chosen.id
        output.append((frame_idx, (chosen.cx, chosen.cy)))

    return output


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
                    static_crop_fallback, try_gpu_detect: bool = False) -> bool:
    """Returns True if smart tracking was used, False if it fell back to a
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

    # Pass 1: sample all faces + mouth movement across the clip.
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

    speaker_samples = _select_active_speaker(raw_samples, src_w, src_h)
    path = _build_smoothed_path(speaker_samples, total_frames)
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
