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
