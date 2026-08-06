#!/usr/bin/env python3
"""Generate Hinglish subtitles using Groq's paid hosted Whisper API - a
focused, simpler alternative to `add_subtitles.py --language hinglish
--groq` for when Groq is the only backend you ever use.

Usage:
    python add_subtitles_groq.py clips/intro.mp4
    python add_subtitles_groq.py clips -o subtitled --burn --caption-style highlight
    python add_subtitles_groq.py clips -o subtitled --burn --groq-api-key gsk_...

Needs an API key from https://console.groq.com/keys - pass it with
--groq-api-key or set a GROQ_API_KEY environment variable so you don't have
to pass it every time.

Known limitation: Groq's stock whisper-large-v3-turbo isn't fine-tuned for
Hinglish transliteration the way the free local model (see add_subtitles.py
--language hinglish, no --groq) is. This module forces "language=en"
decoding plus a style-biasing prompt (GROQ_HINGLISH_PROMPT below) asking
for phonetic Roman-script transliteration instead of translation - this
gets real Hinglish output on genuinely code-switched speech, but it's
steering a model that wasn't built for the task, so treat quality as
"usually good, not guaranteed" and compare against the free local model if
results look off.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import gpu_utils
from add_subtitles import VIDEO_EXTENSIONS, _detect_silences, _extract_wav, _in_silence, burn_subtitles, write_srt
from captions import CaptionStyle, Word, parse_color, write_ass_highlight_mode, write_ass_word_mode
from ffmpeg_utils import get_video_resolution

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3-turbo"

GROQ_HINGLISH_PROMPT = (
    "Transcript is Hinglish: Hindi and English words mixed together in the same "
    "sentences, written entirely in Roman/English script, never Devanagari. "
    "Hindi words: spell them out phonetically as spoken, do not translate them "
    "into English. English words: keep their normal, correct, standard English "
    "spelling exactly as usual - do not spell them phonetically or simplify "
    "them. Example: mujhe office jana hai lekin traffic bahut zyada hai, main "
    "kal presentation aur meditation technique ke baare mein baat karunga."
)


def _groq_transcribe(video_path: Path, api_key: str, model: str, *, word_timestamps: bool, prompt: str = GROQ_HINGLISH_PROMPT) -> dict:
    """Sends the clip's audio to Groq's hosted Whisper API. Real per-word
    timestamps come back directly from the API when word_timestamps=True
    (better than any proportional-interpolation guess)."""
    import requests

    # Defends against a very easy copy-paste mistake: pasting extra text or
    # line breaks along with the key (e.g. into a $env:GROQ_API_KEY= value)
    # produces a key with embedded whitespace, which requests then rejects
    # outright with an opaque "Invalid leading whitespace... in header
    # value" error. A real Groq key is one unbroken token, so take just the
    # first whitespace-delimited chunk of whatever was passed in.
    api_key = api_key.strip().split()[0] if api_key and api_key.strip() else api_key

    wav_path = _extract_wav(video_path)
    try:
        data = {"model": model, "language": "en", "response_format": "verbose_json"}
        if word_timestamps:
            data["timestamp_granularities[]"] = "word"
        if prompt:
            data["prompt"] = prompt
        with wav_path.open("rb") as f:
            response = requests.post(
                GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (wav_path.name, f, "audio/wav")},
                data=data,
                timeout=180,
            )
    finally:
        wav_path.unlink(missing_ok=True)
    if response.status_code != 200:
        raise RuntimeError(f"Groq API error {response.status_code}: {response.text[:500]}")
    return response.json()


def get_words_hinglish_groq(video_path: Path, api_key: str, model: str = DEFAULT_GROQ_MODEL) -> list[Word]:
    result = _groq_transcribe(video_path, api_key, model, word_timestamps=True)
    silences = _detect_silences(video_path)
    words = []
    for w in result.get("words", []):
        text = w.get("word", "").strip()
        start, end = w.get("start"), w.get("end")
        if text and start is not None and end is not None and not _in_silence(start, end, silences):
            words.append(Word(start, end, text))
    return words


def transcribe_to_srt_hinglish_groq(video_path: Path, srt_path: Path, api_key: str, model: str = DEFAULT_GROQ_MODEL):
    result = _groq_transcribe(video_path, api_key, model, word_timestamps=False)
    silences = _detect_silences(video_path)
    entries = []
    for seg in result.get("segments", []):
        start, end, text = seg.get("start"), seg.get("end"), seg.get("text", "")
        if start is None or end is None or _in_silence(start, end, silences):
            continue
        entries.append((start, end, text))
    count = write_srt(srt_path, entries)
    return count, "hinglish-groq"


def process_video(video_path: Path, output_dir: Path, i: int, total: int, *, api_key: str, model: str,
                   caption_style: str, style: CaptionStyle, max_words: int, burn: bool, use_gpu_encode: bool):
    print(f"[{i}/{total}] Transcribing {video_path.name} (Groq, {model})...")

    if caption_style == "plain":
        caption_path = output_dir / f"{video_path.stem}.srt"
        count, _ = transcribe_to_srt_hinglish_groq(video_path, caption_path, api_key, model)
        print(f"    -> {caption_path} ({count} lines)")
    else:
        words = get_words_hinglish_groq(video_path, api_key, model)
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
    parser.add_argument("--groq-api-key", default=None, help="Groq API key (get one at https://console.groq.com/keys). Falls back to the GROQ_API_KEY environment variable if not passed.")
    parser.add_argument("--groq-model", default=DEFAULT_GROQ_MODEL, help=f"Groq Whisper model to use (default: {DEFAULT_GROQ_MODEL})")
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
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected (only affects burning, not transcription - that always runs on Groq's servers)")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    api_key = args.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("An API key is required: pass --groq-api-key or set the GROQ_API_KEY environment variable. Get one at https://console.groq.com/keys")
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("requests is not installed. Run: pip install requests")

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

    use_gpu_encode = not args.no_gpu and gpu_utils.has_nvenc()

    print(f"Using Groq API ({args.groq_model}) for Hinglish transcription (paid)")
    failures = []
    for i, video_path in enumerate(videos, start=1):
        try:
            process_video(
                video_path, args.output_dir, i, len(videos), api_key=api_key, model=args.groq_model,
                caption_style=args.caption_style, style=style, max_words=args.max_words,
                burn=args.burn, use_gpu_encode=use_gpu_encode,
            )
        except Exception as e:
            print(f"    FAILED: {video_path.name}: {e}")
            failures.append(video_path.name)

    print(f"\nDone. Output in {args.output_dir}/")
    if failures:
        print(f"{len(failures)}/{len(videos)} clip(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
