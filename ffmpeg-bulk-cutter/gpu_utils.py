"""Shared hardware-acceleration detection. No GPU present -> everything
falls back to CPU automatically; nothing here assumes a GPU exists.

Two encoder families are supported: NVIDIA's h264_nvenc (Windows/Linux
with an NVIDIA GPU) and Apple's h264_videotoolbox (every Mac - Intel or
Apple Silicon, no discrete GPU required, it's part of the OS). Callers
generally shouldn't care which one is in play - use gpu_available()/
gpu_verified() to decide whether to attempt GPU encoding at all, and
encoder_name() for which -c:v value to actually pass.
"""
import shutil
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def has_nvidia_gpu() -> bool:
    """True if an NVIDIA driver is present (nvidia-smi runs successfully).
    Only meaningful for CUDA-based acceleration (e.g. faster-whisper) -
    VideoToolbox on Mac has no equivalent "is a GPU present" check of its
    own, since it's always available as part of the OS rather than tied
    to a specific driver."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=10).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@lru_cache(maxsize=1)
def _ffmpeg_encoders() -> str:
    if shutil.which("ffmpeg") is None:
        return ""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


@lru_cache(maxsize=1)
def has_nvenc() -> bool:
    """True if this ffmpeg build has the h264_nvenc hardware encoder."""
    return "h264_nvenc" in _ffmpeg_encoders()


@lru_cache(maxsize=1)
def has_videotoolbox() -> bool:
    """True if this ffmpeg build has the h264_videotoolbox hardware
    encoder (macOS only - Homebrew's ffmpeg has this compiled in by
    default, no extra setup needed)."""
    return "h264_videotoolbox" in _ffmpeg_encoders()


def _throwaway_encode_works(encoder: str) -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
             "-c:v", encoder, "-frames:v", "1", "-f", "null", "-"],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@lru_cache(maxsize=1)
def nvenc_works() -> bool:
    """Real functional check, not just "is it compiled in": has_nvenc() can
    be True on a machine with no usable GPU/driver at runtime (confirmed:
    ffmpeg builds can report h264_nvenc available and still fail with
    'Cannot load libcuda.so.1'). Frame-by-frame pipelines like smart-crop
    are too expensive to redo from scratch on a late GPU failure, so this
    does one cheap throwaway encode upfront instead of finding out late."""
    return has_nvenc() and _throwaway_encode_works("h264_nvenc")


@lru_cache(maxsize=1)
def videotoolbox_works() -> bool:
    """Same real functional check as nvenc_works(), for VideoToolbox -
    it's normally reliable on Mac since it's an OS framework rather than
    a driver, but sandboxed/headless/CI environments have been known to
    reject hardware encode requests, so this still verifies rather than
    assuming."""
    return has_videotoolbox() and _throwaway_encode_works("h264_videotoolbox")


@lru_cache(maxsize=1)
def gpu_available() -> bool:
    """Cheap "is some GPU encoder compiled in" check - only safe to use
    where a runtime fallback to CPU exists downstream (e.g. via
    _run_with_gpu_fallback), same caveat as has_nvenc() alone had."""
    return has_nvenc() or has_videotoolbox()


@lru_cache(maxsize=1)
def gpu_verified() -> bool:
    """Expensive "does it actually encode right now" check - required
    before any pipe-based/frame-by-frame encoder that has no runtime
    fallback of its own."""
    return nvenc_works() or videotoolbox_works()


@lru_cache(maxsize=1)
def encoder_name() -> str:
    """Which -c:v value to actually use. Prefers nvenc when (hypothetically)
    both are compiled in, but in practice a machine has at most one of
    these - NVIDIA GPUs don't ship in Macs, and VideoToolbox is Mac-only.
    Falls back to libx264 (CPU) if called on a machine with neither -
    callers should still gate on gpu_available()/gpu_verified() first."""
    if has_nvenc():
        return "h264_nvenc"
    if has_videotoolbox():
        return "h264_videotoolbox"
    return "libx264"
