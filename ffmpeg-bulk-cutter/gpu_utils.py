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
