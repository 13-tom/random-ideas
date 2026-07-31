#!/usr/bin/env python3
"""Generate free, local subtitles for one video or a whole folder of clips,
using faster-whisper (CPU-friendly, no GPU required) or a Hinglish-specific
Whisper model, and optionally burn them into the video with ffmpeg.

Usage:
    python add_subtitles.py clips/intro.mp4
    python add_subtitles.py clips/ -o subbed --burn
    python add_subtitles.py clips/ --language hi --model medium --burn
    python add_subtitles.py clips/ --language hinglish --burn

Notes on language:
    --language en       forces English transcription (faster-whisper)
    --language hi       forces Hindi transcription with faster-whisper
                        (mixed speech comes out with Hindi words in
                        Devanagari script and English words kept in Latin
                        script - this is plain Whisper's normal Hindi
                        behavior, NOT Romanized "Hinglish")
    --language auto     lets faster-whisper auto-detect the language (default)
    --language hinglish uses Oriserve/Whisper-Hindi2Hinglish-Swift, a model
                        fine-tuned to output Hindi+English code-switched
                        speech fully in Roman script (true "Hinglish" text).
                        Requires torch + transformers (see requirements.txt).
                        --model is ignored in this mode.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
HINGLISH_MODEL_ID = "Oriserve/Whisper-Hindi2Hinglish-Swift"


def format_srt_timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def get_media_duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def write_srt(srt_path: Path, entries):
    """entries: iterable of (start_seconds, end_seconds, text)"""
    with srt_path.open("w", encoding="utf-8") as f:
        count = 0
        for start, end, text in entries:
            text = text.strip()
            if not text:
                continue
            count += 1
            f.write(f"{count}\n")
            f.write(f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n")
            f.write(f"{text}\n\n")
    return count


def transcribe_to_srt(model, video_path: Path, srt_path: Path, language: str | None):
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        vad_filter=True,
    )
    count = write_srt(srt_path, ((s.start, s.end, s.text) for s in segments))
    return count, info.language


def transcribe_to_srt_hinglish(pipe, video_path: Path, srt_path: Path):
    result = pipe(
        str(video_path),
        return_timestamps=True,
        generate_kwargs={"task": "transcribe", "language": "en"},
    )
    chunks = result.get("chunks") or [{"timestamp": (0.0, None), "text": result["text"]}]
    duration = get_media_duration(video_path)

    entries = []
    for i, chunk in enumerate(chunks):
        start, end = chunk["timestamp"]
        start = start or 0.0
        if end is None:
            # Whisper sometimes doesn't predict an end timestamp for the
            # final (or a cut-off) chunk; fall back to the next chunk's
            # start, or the clip's total duration if this is the last one.
            end = chunks[i + 1]["timestamp"][0] if i + 1 < len(chunks) else duration
        entries.append((start, end, chunk["text"]))

    count = write_srt(srt_path, entries)
    return count, "hinglish"


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
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="Force a language, auto-detect, or 'hinglish' for Roman-script Hindi+English (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size (default: small - best speed/accuracy balance on CPU). Ignored when --language hinglish is used.")
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

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.language == "hinglish":
        try:
            from transformers import pipeline
        except ImportError:
            sys.exit("transformers/torch not installed. Run: pip install -r requirements.txt")

        print(f"Loading {HINGLISH_MODEL_ID} (CPU)... this only happens once per run.")
        pipe = pipeline("automatic-speech-recognition", model=HINGLISH_MODEL_ID)

        for i, video_path in enumerate(videos, start=1):
            srt_path = args.output_dir / f"{video_path.stem}.srt"
            print(f"[{i}/{len(videos)}] Transcribing {video_path.name} (hinglish)...")
            count, detected_language = transcribe_to_srt_hinglish(pipe, video_path, srt_path)
            print(f"    -> {srt_path} ({count} lines)")

            if args.burn:
                burned_path = args.output_dir / f"{video_path.stem}_captioned{video_path.suffix}"
                burn_subtitles(video_path, srt_path, burned_path)
                print(f"    -> {burned_path} (captions burned in)")

        print(f"\nDone. Output in {args.output_dir}/")
        return

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")

    print(f"Loading Whisper '{args.model}' model (CPU, int8)... this only happens once per run.")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

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
