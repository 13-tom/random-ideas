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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import gpu_utils
from captions import CaptionStyle, Word, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_media_duration, get_video_resolution

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
HINGLISH_MODEL_ID = "Oriserve/Whisper-Hindi2Hinglish-Swift"


def load_whisper_model(model_size: str, use_gpu: bool):
    from faster_whisper import WhisperModel

    if use_gpu:
        try:
            model = WhisperModel(model_size, device="cuda", compute_type="float16")
            print(f"Loaded Whisper '{model_size}' on GPU (CUDA, float16)")
            return model
        except Exception as e:
            print(f"GPU load failed ({e}); falling back to CPU")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"Loaded Whisper '{model_size}' on CPU (int8)")
    return model


def load_hinglish_pipeline(use_gpu: bool):
    from transformers import pipeline
    import torch

    # chunk_length_s/stride_length_s: Whisper's encoder only handles ~30s of
    # audio per pass. Without these, transformers doesn't chunk longer clips
    # itself, and on anything past ~30s the pipeline can silently come back
    # with an empty transcript instead of erroring - explicit chunking (with
    # a little overlap via stride) makes clips of any length transcribe
    # reliably, at the cost of chunk boundaries needing the overlap to stitch
    # words back together (which the pipeline already handles internally).
    if use_gpu:
        try:
            pipe = pipeline("automatic-speech-recognition", model=HINGLISH_MODEL_ID, device=0, torch_dtype=torch.float16, chunk_length_s=30, stride_length_s=5)
            print(f"Loaded {HINGLISH_MODEL_ID} on GPU (CUDA, float16)")
            return pipe
        except Exception as e:
            print(f"GPU load failed ({e}); falling back to CPU")
    pipe = pipeline("automatic-speech-recognition", model=HINGLISH_MODEL_ID, device=-1, torch_dtype=torch.float32, chunk_length_s=30, stride_length_s=5)
    print(f"Loaded {HINGLISH_MODEL_ID} on CPU")
    return pipe


def format_srt_timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


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


def _extract_wav(video_path: Path):
    """Decode a video's audio to a standalone 16kHz mono WAV file.

    The Hinglish pipeline reads its input by piping raw file bytes into
    ffmpeg over stdin, which requires ffmpeg to seek to the MP4 'moov atom
    - if that atom lands at the end of the file (common; depends on the
    encoder that wrote it), stdin can't be sought and ffmpeg silently
    produces zero audio bytes, which the pipeline then reports as "soundfile
    is malformed". Extracting to a real WAV file on disk first sidesteps
    this entirely, since ffmpeg can then open it normally (with seeking).
    """
    # mkstemp returns an open file descriptor as well as the path - it must
    # be closed here (we don't write through it; ffmpeg writes to the path
    # directly). Leaving it open is harmless on Linux but on Windows the
    # dangling handle blocks ffmpeg/the pipeline from writing to or later
    # deleting the file ("[WinError 32] The process cannot access the file
    # because it is being used by another process").
    fd, wav_path_str = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    wav_path = Path(wav_path_str)
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(wav_path)],
        check=True, capture_output=True,
    )
    return wav_path


def _detect_silences(video_path: Path, noise_db: str = "-35dB", min_duration: float = 0.6) -> list[tuple[float, float]]:
    """Analysis-only pass (ffmpeg's silencedetect filter doesn't modify the
    audio, so timestamps stay aligned with the original clip) to find silent
    ranges. Used to filter out Whisper's well-known hallucination habit of
    repeating the last-heard word/phrase over and over during actual
    silence, since the Hinglish pipeline has no VAD of its own (unlike
    faster-whisper's vad_filter=True)."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(video_path), "-af", f"silencedetect=noise={noise_db}:d={min_duration}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silences = []
    start = None
    for line in result.stderr.splitlines():
        if "silence_start" in line:
            try:
                start = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                start = None
        elif "silence_end" in line and start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split("|")[0].strip())
                silences.append((start, end))
            except (IndexError, ValueError):
                pass
            start = None
    return silences


def _in_silence(start: float, end: float, silences: list[tuple[float, float]]) -> bool:
    return any(start >= s and end <= e for s, e in silences)


def transcribe_to_srt_hinglish(pipe, video_path: Path, srt_path: Path):
    wav_path = _extract_wav(video_path)
    try:
        result = pipe(
            str(wav_path),
            return_timestamps=True,
            generate_kwargs={"task": "transcribe", "language": "en"},
        )
    finally:
        wav_path.unlink(missing_ok=True)
    chunks = result.get("chunks") or [{"timestamp": (0.0, None), "text": result["text"]}]
    duration = get_media_duration(video_path)
    silences = _detect_silences(video_path)

    entries = []
    for i, chunk in enumerate(chunks):
        start, end = chunk["timestamp"]
        start = start or 0.0
        if end is None:
            # Whisper sometimes doesn't predict an end timestamp for the
            # final (or a cut-off) chunk; fall back to the next chunk's
            # start, or the clip's total duration if this is the last one.
            end = chunks[i + 1]["timestamp"][0] if i + 1 < len(chunks) else duration
        if _in_silence(start, end, silences):
            continue
        entries.append((start, end, chunk["text"]))

    count = write_srt(srt_path, entries)
    return count, "hinglish"


def get_words_faster_whisper(model, video_path: Path, language: str | None) -> tuple[list[Word], str]:
    segments, info = model.transcribe(
        str(video_path),
        language=language,
        vad_filter=True,
        word_timestamps=True,
    )
    words = []
    for segment in segments:
        for w in segment.words:
            text = w.word.strip()
            if text:
                words.append(Word(w.start, w.end, text))
    return words, info.language


def get_words_hinglish(pipe, video_path: Path) -> list[Word]:
    """This fine-tuned checkpoint doesn't support true word-level alignment
    (it has no Whisper alignment-head metadata, so return_timestamps='word'
    crashes). Instead, take its sentence-level chunk timestamps and
    interpolate per-word timing proportionally by character length -
    approximate, but reads fine for on-screen captions.
    """
    wav_path = _extract_wav(video_path)
    try:
        result = pipe(
            str(wav_path),
            return_timestamps=True,
            generate_kwargs={"task": "transcribe", "language": "en"},
        )
    finally:
        wav_path.unlink(missing_ok=True)
    chunks = result.get("chunks") or [{"timestamp": (0.0, None), "text": result["text"]}]
    duration = get_media_duration(video_path)
    silences = _detect_silences(video_path)

    words = []
    for i, chunk in enumerate(chunks):
        start, end = chunk["timestamp"]
        start = start or 0.0
        if end is None:
            end = chunks[i + 1]["timestamp"][0] if i + 1 < len(chunks) else duration
        if _in_silence(start, end, silences):
            continue
        chunk_words = chunk["text"].strip().split()
        if not chunk_words:
            continue
        total_chars = sum(len(w) for w in chunk_words) or 1
        span = end - start
        cursor = start
        for w in chunk_words:
            portion = (len(w) / total_chars) * span
            word_start, word_end = cursor, cursor + portion
            if not _in_silence(word_start, word_end, silences):
                words.append(Word(word_start, word_end, w))
            cursor += portion
    return words


def _escape_subtitles_path(srt_path: Path) -> str:
    # ffmpeg's -vf filtergraph parser treats ':' as an option separator and
    # '\' as its own escape character, so a doubled-backslash escape gets
    # consumed by the parser instead of surviving to the file path (breaks
    # Windows paths like output\captioned\clip.srt). Using forward slashes
    # sidesteps backslash escaping entirely; only a drive-letter colon
    # (e.g. "F:") still needs escaping.
    path_str = str(srt_path).replace("\\", "/")
    return path_str.replace(":", "\\:")


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, use_gpu: bool = False):
    escaped_srt = _escape_subtitles_path(srt_path)
    base_cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-vf", f"subtitles={escaped_srt}"]

    if use_gpu:
        gpu_cmd = base_cmd + ["-c:v", "h264_nvenc", "-c:a", "copy", str(output_path)]
        result = subprocess.run(gpu_cmd, capture_output=True)
        if result.returncode == 0:
            return
        print("  GPU encode failed at runtime, falling back to CPU (libx264)")

    cpu_cmd = base_cmd + ["-c:v", "libx264", "-c:a", "copy", str(output_path)]
    subprocess.run(cpu_cmd, check=True)


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, caption_style: str,
                   language, model=None, pipe=None, style: CaptionStyle = None,
                   max_words: int, burn: bool, use_gpu_encode: bool):
    print(f"[{i}/{total}] Transcribing {video_path.name}...")

    if caption_style == "plain":
        caption_path = output_dir / f"{video_path.stem}.srt"
        if pipe is not None:
            count, _ = transcribe_to_srt_hinglish(pipe, video_path, caption_path)
        else:
            count, detected = transcribe_to_srt(model, video_path, caption_path, language)
        print(f"    -> {caption_path} ({count} lines)")
    else:
        words = get_words_hinglish(pipe, video_path) if pipe is not None else get_words_faster_whisper(model, video_path, language)[0]
        video_res = get_video_resolution(video_path)
        caption_path = output_dir / f"{video_path.stem}.ass"
        if caption_style == "word":
            count = write_ass_word_mode(words, caption_path, video_res, style)
        else:
            count = write_ass_highlight_mode(words, caption_path, video_res, style, max_words)
        print(f"    -> {caption_path} ({count} lines)")

    if burn:
        burned_path = output_dir / f"{video_path.stem}_captioned{video_path.suffix}"
        burn_subtitles(video_path, caption_path, burned_path, use_gpu_encode)
        print(f"    -> {burned_path} (captions burned in)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="A video file, or a folder of video clips")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("subtitled"), help="Where to write caption files (and burned videos) (default: ./subtitled)")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="Force a language, auto-detect, or 'hinglish' for Roman-script Hindi+English (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size (default: small - best speed/accuracy balance on CPU). Ignored when --language hinglish is used.")
    parser.add_argument("--burn", action="store_true", help="Also produce a copy of the video with subtitles burned in")
    parser.add_argument("--caption-style", choices=["plain", "word", "highlight"], default="plain",
                         help="plain = one .srt line per sentence (default, matches Premiere/Resolve import). "
                              "word = one word on screen at a time (TikTok/CapCut style). "
                              "highlight = full line shown with the currently-spoken word highlighted (Opus Clip style).")
    parser.add_argument("--font", default="Arial", help="Font family for word/highlight caption styles (default: Arial). Must be installed on this system.")
    parser.add_argument("--font-size", type=int, default=64, help="Font size for word/highlight caption styles (default: 64)")
    parser.add_argument("--text-color", default="white", help="Caption text color: a name (white/yellow/black/red/green/cyan/blue/orange) or hex like #FFCC00 (default: white)")
    parser.add_argument("--highlight-color", default="yellow", help="Active-word color for --caption-style highlight/word (default: yellow)")
    parser.add_argument("--outline-color", default="black", help="Text outline color (default: black)")
    parser.add_argument("--outline-width", type=int, default=3, help="Text outline width in pixels (default: 3)")
    parser.add_argument("--no-bold", action="store_true", help="Disable bold (bold is on by default, matching most Reels caption styles)")
    parser.add_argument("--italic", action="store_true", help="Italic text")
    parser.add_argument("--all-caps", action="store_true", help="Render captions in ALL CAPS")
    parser.add_argument("--box", action="store_true", help="Highlight the active word with a solid colored background box instead of just colored text (closer to Opus Clip's look). Uses --highlight-color as the box fill.")
    parser.add_argument("--position", choices=["bottom", "middle", "top"], default="bottom", help="Vertical placement of captions (default: bottom)")
    parser.add_argument("--max-words", type=int, default=5, help="Words per on-screen line for --caption-style highlight (default: 5)")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    try:
        style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position=args.position, margin_v=80,
        )
    except ValueError as e:
        sys.exit(str(e))

    if args.input.is_dir():
        videos = sorted(p for p in args.input.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    else:
        videos = [args.input]

    if not videos:
        sys.exit(f"No video files found in {args.input}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    gpu_requested = not args.no_gpu
    use_gpu_whisper = gpu_requested and gpu_utils.has_nvidia_gpu()
    use_gpu_encode = gpu_requested and gpu_utils.has_nvenc()

    common_kwargs = dict(
        caption_style=args.caption_style, style=style, max_words=args.max_words,
        burn=args.burn, use_gpu_encode=use_gpu_encode,
    )

    if args.language == "hinglish":
        try:
            from transformers import pipeline  # noqa: F401
        except ImportError:
            sys.exit("transformers/torch not installed. Run: pip install -r requirements.txt")

        pipe = load_hinglish_pipeline(use_gpu_whisper)
        for i, video_path in enumerate(videos, start=1):
            process_video(video_path, args.output_dir, i, len(videos), language=None, pipe=pipe, **common_kwargs)
    else:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError:
            sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")

        model = load_whisper_model(args.model, use_gpu_whisper)
        language = None if args.language == "auto" else args.language
        for i, video_path in enumerate(videos, start=1):
            process_video(video_path, args.output_dir, i, len(videos), language=language, model=model, **common_kwargs)

    print(f"\nDone. Output in {args.output_dir}/")


if __name__ == "__main__":
    main()
