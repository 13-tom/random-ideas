#!/usr/bin/env python3
"""Auto-generate a timestamps.csv of the best clip-worthy moments in a
video, ready to feed straight into cut_clips.py / run_pipeline.py - this is
the missing "which clip is best" step; everything downstream of it
(cutting, reframing, captioning) is unchanged, existing pipeline code.

Usage:
    python generate_timestamps.py raw.mp4 -o timestamps.csv
    python generate_timestamps.py raw.mp4 -o timestamps.csv --provider local --llm-model llama3.1
    python generate_timestamps.py raw.mp4 -o timestamps.csv --min-duration 20 --max-duration 90 --max-clips 8

    # then, unchanged:
    python run_pipeline.py raw.mp4 timestamps.csv -o output --aspect vertical --track-faces --caption-style highlight

How it works:
    1. Transcribes the video with faster-whisper (word-level timestamps),
       or the Hinglish model for --language hinglish.
    2. Groups words into timestamped chunks (transcript_chunking.py).
    3. Sends the chunked transcript to an LLM, asking it to pick and score
       the best clip-worthy chunk ranges (clip_scoring.py - see --provider
       for which LLM backend).
    4. Resolves chunk ranges to seconds, pads slightly, dedupes overlaps,
       and filters by target length (clip_postprocess.py).
    5. Writes the result as start,end,label rows - the exact format
       cut_clips.py and run_pipeline.py already expect.

If the LLM call fails (no API key, provider outage, bad response), falls
back to evenly-spaced unscored candidates so a job doesn't dead-end - see
clip_postprocess.fallback_candidates().
"""
import argparse
import shutil
import sys
from pathlib import Path

import add_subtitles
import gpu_utils
from clip_postprocess import fallback_candidates, resolve_and_postprocess, write_csv
from clip_scoring import ScoringConfig, get_provider
from ffmpeg_utils import get_media_duration
from transcript_chunking import chunk_transcript


def transcribe(input_path: Path, language: str, model_size: str, use_gpu: bool):
    if language == "hinglish":
        try:
            from transformers import pipeline  # noqa: F401
        except ImportError:
            sys.exit("transformers/torch not installed. Run: pip install -r requirements.txt")
        pipe = add_subtitles.load_hinglish_pipeline(use_gpu)
        words = add_subtitles.get_words_hinglish(pipe, input_path)
        return words, "hinglish"

    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")
    model = add_subtitles.load_whisper_model(model_size, use_gpu)
    whisper_language = None if language == "auto" else language
    return add_subtitles.get_words_faster_whisper(model, input_path, whisper_language)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Raw source video")
    parser.add_argument("-o", "--output", type=Path, default=Path("timestamps.csv"), help="Where to write the timestamps CSV (default: ./timestamps.csv)")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="Transcription language (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size (default: small). Ignored for --language hinglish.")
    parser.add_argument("--min-duration", type=float, default=20.0, help="Minimum clip length in seconds (default: 20)")
    parser.add_argument("--max-duration", type=float, default=90.0, help="Maximum clip length in seconds (default: 90)")
    parser.add_argument("--max-clips", type=int, default=10, help="Maximum number of clips to output (default: 10)")
    parser.add_argument("--min-score", type=float, default=0.0, help="Drop candidates scored below this, 0-100 scale (default: 0)")
    parser.add_argument("--provider", choices=["openrouter", "local"], default="openrouter", help="LLM scoring provider (default: openrouter). See clip_scoring.py.")
    parser.add_argument("--llm-model", default=None, help="Override the provider's default model (e.g. 'deepseek/deepseek-chat' for --provider openrouter, or an Ollama tag for --provider local)")
    parser.add_argument("--llm-api-key", default=None, help="API key for the scoring provider (default: OPENROUTER_API_KEY env var for --provider openrouter)")
    parser.add_argument("--llm-base-url", default=None, help="Override the provider's API base URL (e.g. a Tailscale hostname for --provider local)")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input video not found: {args.input}")
    if args.min_duration <= 0 or args.max_duration <= args.min_duration:
        sys.exit(f"--min-duration ({args.min_duration}) must be > 0 and less than --max-duration ({args.max_duration})")

    use_gpu_whisper = not args.no_gpu and gpu_utils.has_nvidia_gpu()

    print(f"=== Step 1/4: Transcribing ({args.language}) ===")
    words, detected_language = transcribe(args.input, args.language, args.model, use_gpu_whisper)
    if not words:
        sys.exit("No speech detected in the video - can't generate timestamps from an empty transcript.")
    print(f"  {len(words)} words transcribed (language: {detected_language})")

    print("=== Step 2/4: Chunking transcript ===")
    chunks = chunk_transcript(words)
    print(f"  {len(chunks)} chunks")

    video_duration = get_media_duration(args.input)
    config = ScoringConfig(
        min_duration_s=args.min_duration, max_duration_s=args.max_duration,
        target_clip_count=args.max_clips, min_score=args.min_score,
    )

    print(f"=== Step 3/4: Scoring clips (provider={args.provider}) ===")
    provider_kwargs = {}
    if args.llm_model:
        provider_kwargs["model"] = args.llm_model
    if args.llm_api_key:
        provider_kwargs["api_key"] = args.llm_api_key
    if args.llm_base_url:
        provider_kwargs["base_url"] = args.llm_base_url

    try:
        provider = get_provider(args.provider, **provider_kwargs)
        raw_candidates = provider.score_candidates(chunks, config)
        if not raw_candidates:
            raise ValueError("provider returned no candidates")
        candidates = resolve_and_postprocess(raw_candidates, chunks, video_duration, config)
        if not candidates:
            raise ValueError("no candidates survived post-processing (try loosening --min-duration/--max-duration/--min-score)")
    except Exception as e:
        print(f"  LLM scoring failed or returned nothing usable ({e}); falling back to evenly-spaced clips")
        candidates = fallback_candidates(chunks, video_duration, config)
        if not candidates:
            sys.exit("Could not generate any candidate clips, even with the fallback. Is the video too short?")

    print(f"=== Step 4/4: Writing {len(candidates)} clip(s) to {args.output} ===")
    for c in candidates:
        scored = f"score={c.score:.0f}" if c.score else "unscored (fallback)"
        print(f"  {c.label}: {c.start:.1f}s -> {c.end:.1f}s  ({scored})")
    write_csv(candidates, args.output)

    print(f"\nDone. Run this next:\n  python run_pipeline.py {args.input} {args.output} -o output --aspect vertical --track-faces --caption-style highlight")


if __name__ == "__main__":
    main()
