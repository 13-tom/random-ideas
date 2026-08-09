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
HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
HAND_MODEL_CACHE = Path.home() / ".cache" / "ffmpeg-bulk-cutter" / "hand_landmarker.task"

SAMPLE_INTERVAL_SEC = 0.4
# Must span multiple sample intervals to actually smooth anything - a
# window narrower than SAMPLE_INTERVAL_SEC (the original bug: 7 frames at
# 25fps is ~0.28s, less than one 0.4s sample gap) lets per-sample detection
# noise pass straight through as visible camera shake.
SMOOTHING_WINDOW_SEC = 1.2
# Movement smaller than this fraction of the frame diagonal between
# samples is treated as detection noise (a static face's landmarks still
# wobble a few pixels frame to frame) and held at the previous position
# instead of being treated as real motion to pan toward.
DEADZONE_FRAC = 0.025
MOUTH_HISTORY_LEN = 6
MAX_FACES = 5
# A crop that just fits the target aspect ratio around the full source
# frame often leaves zero room to vertically reposition (e.g. a 16:9
# source cropped to 9:16 already uses the full source height, so the
# face's actual vertical position can't be honored - confirmed visually:
# heads ended up jammed against the top edge). Zooming in a bit creates
# slack to recenter on the face, and HEADROOM_FRACTION biases that
# placement so the face sits in the upper third with headroom above it
# and more room below for chest/shoulders, instead of dead-center.
TRACK_ZOOM = 0.72
HEADROOM_FRACTION = 0.38
# --zoom-on-gesture: when a hand is detected (someone gesturing), ease out
# to this wider crop instead of staying tight on the face, so hands don't
# get clipped out of frame - then ease back to TRACK_ZOOM once the hand is
# gone. Deliberately modest (not all the way to 1.0/no-zoom) per the
# "not too much zoom" request this was built for.
GESTURE_ZOOM = 0.88
ZOOM_SMOOTHING_SEC = 1.0
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


def _get_hand_model_path() -> Path:
    if not HAND_MODEL_CACHE.exists():
        HAND_MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("  Downloading hand landmark model (one-time, ~7.8MB)...")
        urlretrieve(HAND_MODEL_URL, HAND_MODEL_CACHE)
    return HAND_MODEL_CACHE


@lru_cache(maxsize=1)
def _load_hand_landmarker():
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    base_options = mp_python.BaseOptions(model_asset_path=str(_get_hand_model_path()))
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=2, min_hand_detection_confidence=0.4)
    return vision.HandLandmarker.create_from_options(options), mp


def _hand_present_in_frame(hand_landmarker, mp, frame_bgr) -> bool:
    import cv2
    rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = hand_landmarker.detect(mp_image)
    return len(result.hand_landmarks) > 0


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


def _apply_deadzone(known, frame_w: int, frame_h: int):
    """known: [(frame_idx, (cx,cy)), ...]. Snaps movement smaller than
    DEADZONE_FRAC of the frame diagonal to the previously held position,
    so a mostly-still subject produces a genuinely constant path instead
    of drifting by a few noisy pixels every sample."""
    threshold = DEADZONE_FRAC * math.hypot(frame_w, frame_h)
    result = []
    held = None
    for idx, (cx, cy) in known:
        if held is not None and math.hypot(cx - held[0], cy - held[1]) < threshold:
            result.append((idx, held))
        else:
            held = (cx, cy)
            result.append((idx, held))
    return result


def _build_smoothed_path(samples, total_frames, fps: float):
    """samples: [(frame_idx, (cx,cy) or None), ...]. Returns a per-frame
    list of (cx,cy), interpolating across gaps, snapping sub-threshold
    jitter to a held position, and smoothing over a multi-sample window to
    avoid jittery panning; or None if no faces were found at all."""
    known = [(idx, c) for idx, c in samples if c is not None]
    if not known:
        return None

    frame_w_est = max(c[0] for _, c in known) + 1
    frame_h_est = max(c[1] for _, c in known) + 1
    known = _apply_deadzone(known, frame_w_est, frame_h_est)

    xs = [k[0] for k in known]
    cxs = [k[1][0] for k in known]
    cys = [k[1][1] for k in known]
    frame_indices = np.arange(total_frames)
    # np.interp holds the first/last known value outside the sampled range,
    # so positions before the first detection / after the last one stay put
    # instead of snapping somewhere odd.
    interp_cx = np.interp(frame_indices, xs, cxs)
    interp_cy = np.interp(frame_indices, xs, cys)

    window = max(1, round(fps * SMOOTHING_WINDOW_SEC))
    kernel = np.ones(window) / window
    pad = window // 2
    smooth_cx = np.convolve(np.pad(interp_cx, pad, mode="edge"), kernel, mode="valid")[:total_frames]
    smooth_cy = np.convolve(np.pad(interp_cy, pad, mode="edge"), kernel, mode="valid")[:total_frames]
    return list(zip(smooth_cx, smooth_cy))


def _static_position(samples):
    """Median (x, y) across all known samples - a single robust crop
    center for the whole clip, resistant to outlier positions (e.g. a
    brief look-away) unlike a plain mean. None if nothing was ever found."""
    known = [c for _, c in samples if c is not None]
    if not known:
        return None
    cxs = sorted(c[0] for c in known)
    cys = sorted(c[1] for c in known)
    n = len(known)
    return cxs[n // 2], cys[n // 2]


def _build_zoom_path(gesture_samples, total_frames: int, fps: float):
    """gesture_samples: [(frame_idx, bool), ...] - whether a hand was
    detected at each sample. Returns a per-frame list of zoom factors
    eased between TRACK_ZOOM and GESTURE_ZOOM (via the same interpolate +
    smooth approach as the position path) instead of jump-cutting the
    crop size the instant a hand appears or disappears."""
    if not gesture_samples:
        return [TRACK_ZOOM] * total_frames
    xs = [idx for idx, _ in gesture_samples]
    targets = [GESTURE_ZOOM if active else TRACK_ZOOM for _, active in gesture_samples]
    frame_indices = np.arange(total_frames)
    interp = np.interp(frame_indices, xs, targets)
    window = max(1, round(fps * ZOOM_SMOOTHING_SEC))
    kernel = np.ones(window) / window
    pad = window // 2
    smooth = np.convolve(np.pad(interp, pad, mode="edge"), kernel, mode="valid")[:total_frames]
    return smooth


def _fixed_crop_video(input_path: Path, output_path: Path, x: int, y: int, crop_w: int, crop_h: int,
                       target_res: str, use_gpu: bool):
    vf = f"crop={crop_w}:{crop_h}:{x}:{y},scale={target_res}:flags=lanczos"
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(input_path), "-vf", vf]

    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        print("  GPU encode failed at runtime, falling back to CPU (libx264)")

    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "copy", str(output_path)]
    subprocess.run(cpu_cmd, check=True)


def track_and_crop(input_path: Path, output_path: Path, aspect: str, target_res: str, use_gpu: bool,
                    static_crop_fallback, try_gpu_detect: bool = False, mode: str = "dynamic",
                    zoom_on_gesture: bool = False) -> bool:
    """mode="dynamic" (default) pans to follow the subject, smoothed to
    avoid jitter. mode="static" picks one fixed, face-informed crop
    position for the whole clip - no panning at all, so no possible
    camera shake, at the cost of not following a subject that moves a lot.

    zoom_on_gesture (dynamic mode only) also detects hands: when someone
    gestures, it eases out from TRACK_ZOOM to the wider GESTURE_ZOOM so the
    gesture doesn't get clipped by the tight face crop, then eases back in
    once the hand is gone.

    Returns True if smart tracking was used, False if it fell back to a
    static center crop via static_crop_fallback(input_path, output_path,
    aspect, use_gpu)."""
    try:
        import cv2
    except ImportError:
        sys.exit("opencv-python-headless / mediapipe not installed. Run: pip install -r requirements.txt")

    landmarker, mp = _load_landmarker(try_gpu_detect)
    hand_landmarker = None
    if zoom_on_gesture and mode == "dynamic":
        hand_landmarker, _ = _load_hand_landmarker()

    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample_interval_frames = max(1, round(fps * SAMPLE_INTERVAL_SEC))

    # Pass 1: sample all faces + mouth movement (+ hands, if requested)
    # across the clip.
    raw_samples = []
    gesture_samples = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % sample_interval_frames == 0:
            raw_samples.append((frame_idx, _detect_faces_in_frame(landmarker, mp, frame)))
            if hand_landmarker is not None:
                gesture_samples.append((frame_idx, _hand_present_in_frame(hand_landmarker, mp, frame)))
        frame_idx += 1
    cap.release()
    total_frames = frame_idx

    speaker_samples = _select_active_speaker(raw_samples, src_w, src_h)

    max_crop_w, max_crop_h = crop_dimensions(aspect, src_w, src_h)

    def _sized(zoom: float) -> tuple[int, int]:
        w = max(2, int(max_crop_w * zoom))
        h = max(2, int(max_crop_h * zoom))
        return w - w % 2, h - h % 2

    # Zoom in from the max-size crop so there's actual room to reposition
    # vertically (see TRACK_ZOOM comment above) - ffmpeg's scale filter
    # upscales whatever we crop to the target resolution regardless of
    # size, so this just changes framing, not output resolution. This is
    # also the fixed pipe/output size the encoder gets fed, regardless of
    # zoom_on_gesture - variable-size crops get resized to match it.
    pipe_w, pipe_h = _sized(TRACK_ZOOM)

    if mode == "static":
        position = _static_position(speaker_samples)
        if position is None:
            print("  No faces detected anywhere in this clip, falling back to center crop")
            static_crop_fallback(input_path, output_path, aspect, use_gpu)
            return False
        cx, cy = position
        x = int(min(max(cx - pipe_w / 2, 0), src_w - pipe_w))
        y = int(min(max(cy - pipe_h * HEADROOM_FRACTION, 0), src_h - pipe_h))
        _fixed_crop_video(input_path, output_path, x, y, pipe_w, pipe_h, target_res, use_gpu)
        return True

    path = _build_smoothed_path(speaker_samples, total_frames, fps)
    if path is None:
        print("  No faces detected anywhere in this clip, falling back to center crop")
        static_crop_fallback(input_path, output_path, aspect, use_gpu)
        return False

    zoom_path = _build_zoom_path(gesture_samples, total_frames, fps) if hand_landmarker is not None else None

    # Pass 2: crop each frame following the smoothed path (and zoom, if
    # tracking gestures), piping raw frames into ffmpeg for encoding
    # (keeps quality/GPU-encode consistent with the rest of the pipeline
    # instead of using OpenCV's own encoder).
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{pipe_w}x{pipe_h}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(input_path),
        "-map", "0:v", "-map", "1:a?",
        "-vf", f"scale={target_res}:flags=lanczos",
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

        if zoom_path is not None:
            crop_w, crop_h = _sized(zoom_path[frame_idx] if frame_idx < len(zoom_path) else TRACK_ZOOM)
        else:
            crop_w, crop_h = pipe_w, pipe_h

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
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode} while encoding the tracked crop")
    return True
