"""Shared hardware-acceleration detection. No GPU present -> everything
falls back to CPU automatically; nothing here assumes a GPU exists.
"""
import shutil
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def has_nvidia_gpu() -> bool:
    """True if an NVIDIA driver is present (nvidia-smi runs successfully)."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=10).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@lru_cache(maxsize=1)
def has_nvenc() -> bool:
    """True if this ffmpeg build has the h264_nvenc hardware encoder."""
    if shutil.which("ffmpeg") is None:
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
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
    if not has_nvenc():
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
             "-c:v", "h264_nvenc", "-frames:v", "1", "-f", "null", "-"],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
