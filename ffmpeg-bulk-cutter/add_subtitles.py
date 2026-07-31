#!/usr/bin/env python3
"""Generate free, local subtitles for one video or a whole folder of clips,
using faster-whisper (CPU-friendly, no GPU required), and optionally burn
them into the video with ffmpeg.

Usage:
    python add_subtitles.py clips/intro.mp4
    python add_subtitles.py clips/ -o subbed --burn
    python add_subtitles.py clips/ --language hi --model medium --burn

Notes on language:
    --language en   forces English transcription
    --language hi   forces Hindi transcription (mixed speech comes out with
                    Hindi words in Devanagari script and English words kept
                    in Latin script - this is NOT Romanized "Hinglish", just
                    plain Whisper's normal Hindi behavior)
    --language auto lets Whisper detect the language per file (default)
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def format_srt_timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe_to_srt(model, video_path: Path, srt_path: Path, language: str | None):
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        vad_filter=True,
    )
    with srt_path.open("w", encoding="utf-8") as f:
        count = 0
        for segment in segments:
            count += 1
            f.write(f"{count}\n")
            f.write(f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}\n")
            f.write(f"{segment.text.strip()}\n\n")
    return count, info.language


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path):
    # ffmpeg's subtitles filter needs the path escaped for its internal parser
    escaped_srt = str(srt_path).replace("\\", "\\\\").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={escaped_srt}",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("subtitled"), help="Where to write .srt files (and burned videos) (default: ./subtitled)")
    parser.add_argument("--language", choices=["en", "hi", "auto"], default="auto", help="Force a language, or auto-detect per file (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size (default: small - best speed/accuracy balance on CPU)")
    parser.add_argument("--burn", action="store_true", help="Also produce a copy of the video with subtitles burned in")
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

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")

    print(f"Loading Whisper '{args.model}' model (CPU, int8)... this only happens once per run.")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    language = None if args.language == "auto" else args.language

    for i, video_path in enumerate(videos, start=1):
        srt_path = args.output_dir / f"{video_path.stem}.srt"
        print(f"[{i}/{len(videos)}] Transcribing {video_path.name}...")
        count, detected_language = transcribe_to_srt(model, video_path, srt_path, language)
        print(f"    -> {srt_path} ({count} lines, language: {detected_language})")

        if args.burn:
            burned_path = args.output_dir / f"{video_path.stem}_captioned{video_path.suffix}"
            burn_subtitles(video_path, srt_path, burned_path)
            print(f"    -> {burned_path} (captions burned in)")

    print(f"\nDone. Output in {args.output_dir}/")


if __name__ == "__main__":
    main()
