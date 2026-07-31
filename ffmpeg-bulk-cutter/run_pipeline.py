#!/usr/bin/env python3
"""End-to-end pipeline: raw video -> cut clips -> transcribe -> burn captions.

Usage:
    python run_pipeline.py raw.mp4 timestamps.csv -o output
    python run_pipeline.py raw.mp4 timestamps.csv -o output --language hinglish
    python run_pipeline.py raw.mp4 timestamps.csv -o output --language en --model medium --reencode

Runs cut_clips.py and add_subtitles.py back to back:
    output/clips/       - the cut clips (silent, no captions)
    output/captioned/   - matching .srt files + captioned/burned-in videos

Automatically uses an NVIDIA GPU for encoding and transcription if one is
detected, falling back to CPU otherwise (see gpu_utils.py). Use --no-gpu to
force CPU.
"""
import argparse
import shutil
import sys
from pathlib import Path

import add_subtitles
import cut_clips
import gpu_utils


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Raw source video")
    parser.add_argument("timestamps", type=Path, help="CSV file with start,end[,label] rows")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("pipeline_output"), help="Where to write clips/ and captioned/ (default: ./pipeline_output)")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="See add_subtitles.py --help for details (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size; ignored when --language hinglish is used (default: small)")
    parser.add_argument("--reencode", action="store_true", help="Frame-accurate cuts (recommended before captioning, since it lines subtitles up with clean clip boundaries)")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first: https://ffmpeg.org/download.html")
    if not args.input.exists():
        sys.exit(f"Input video not found: {args.input}")
    if not args.timestamps.exists():
        sys.exit(f"Timestamps CSV not found: {args.timestamps}")

    try:
        clip_rows = cut_clips.read_clips(args.timestamps)
        if not clip_rows:
            sys.exit("No clips found in CSV.")
        cut_clips.validate_clips(clip_rows, args.input)
    except ValueError as e:
        sys.exit(str(e))

    gpu_requested = not args.no_gpu
    use_gpu_encode = gpu_requested and gpu_utils.has_nvenc()
    use_gpu_whisper = gpu_requested and gpu_utils.has_nvidia_gpu()

    clips_dir = args.output_dir / "clips"
    captioned_dir = args.output_dir / "captioned"
    clips_dir.mkdir(parents=True, exist_ok=True)
    captioned_dir.mkdir(parents=True, exist_ok=True)

    # --- Step 1: cut ---
    print(f"=== Step 1/2: Cutting {len(clip_rows)} clip(s) "
          f"({'GPU encode' if use_gpu_encode and args.reencode else 'CPU encode' if args.reencode else 'stream copy'}) ===")
    suffix = args.input.suffix
    clip_paths = []
    for i, (start, end, label) in enumerate(clip_rows, start=1):
        name = label if label else f"clip_{i:03d}"
        output_path = clips_dir / f"{name}{suffix}"
        print(f"[{i}/{len(clip_rows)}] {cut_clips.format_timestamp(start)} -> {cut_clips.format_timestamp(end)}  =>  {output_path}")
        cut_clips.cut_clip(args.input, start, end, output_path, args.reencode, use_gpu_encode)
        clip_paths.append(output_path)

    # --- Step 2: transcribe + burn ---
    print(f"\n=== Step 2/2: Transcribing ({args.language}) and burning captions ===")
    if args.language == "hinglish":
        pipe = add_subtitles.load_hinglish_pipeline(use_gpu_whisper)
        def transcribe(video_path, srt_path):
            return add_subtitles.transcribe_to_srt_hinglish(pipe, video_path, srt_path)
    else:
        model = add_subtitles.load_whisper_model(args.model, use_gpu_whisper)
        language = None if args.language == "auto" else args.language
        def transcribe(video_path, srt_path):
            return add_subtitles.transcribe_to_srt(model, video_path, srt_path, language)

    for i, clip_path in enumerate(clip_paths, start=1):
        srt_path = captioned_dir / f"{clip_path.stem}.srt"
        print(f"[{i}/{len(clip_paths)}] Transcribing {clip_path.name}...")
        count, _ = transcribe(clip_path, srt_path)
        print(f"    -> {srt_path} ({count} lines)")

        burned_path = captioned_dir / f"{clip_path.stem}_captioned{clip_path.suffix}"
        add_subtitles.burn_subtitles(clip_path, srt_path, burned_path, use_gpu_encode)
        print(f"    -> {burned_path}")

    print(f"\nDone. Clips in {clips_dir}/, captioned videos in {captioned_dir}/")


if __name__ == "__main__":
    main()
