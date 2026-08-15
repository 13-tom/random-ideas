"""Small shared ffmpeg/ffprobe helpers used by both cut_clips.py and
add_subtitles.py.
"""
import json
import subprocess
from pathlib import Path


def get_media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def get_video_resolution(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return stream["width"], stream["height"]


def get_video_fps(path: Path) -> str:
    """Returns the source's frame rate as an ffmpeg-friendly 'num/den'
    string (e.g. '30000/1001' for 29.97fps), straight from r_frame_rate -
    lets callers match a generated/lavfi stream's rate to it exactly."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["streams"][0]["r_frame_rate"]
