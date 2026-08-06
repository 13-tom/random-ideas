#!/usr/bin/env python3
"""End-to-end pipeline: raw video -> cut clips -> reframe -> burn captions.

Usage:
    python run_pipeline.py raw.mp4 timestamps.csv -o output
    python run_pipeline.py raw.mp4 timestamps.csv -o output --aspect vertical --language hinglish
    python run_pipeline.py raw.mp4 timestamps.csv -o output --caption-style highlight --highlight-color "#00FFCC"

Runs cut_clips.py, reframe.py, and add_subtitles.py back to back:
    output/clips/       - the cut clips (silent, no captions, original aspect)
    output/reframed/    - clips cropped to --aspect (skipped if --aspect original)
    output/captioned/   - caption files + burned-in videos, ready to post

Automatically uses an NVIDIA GPU for encoding and transcription if one is
detected, falling back to CPU otherwise (see gpu_utils.py). Use --no-gpu to
force CPU.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import add_subtitles
import cut_clips
import gpu_utils
import reframe
from captions import CaptionStyle, parse_color


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Raw source video")
    parser.add_argument("timestamps", type=Path, help="CSV file with start,end[,label] rows")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("pipeline_output"), help="Where to write clips/, reframed/, and captioned/ (default: ./pipeline_output)")
    parser.add_argument("--aspect", choices=["original", *reframe.ASPECT_RATIOS], default="original", help="vertical = 9:16 Reels/Stories/Shorts, square = 1:1 feed/carousel, portrait = 4:5 IG feed, landscape = 16:9 YouTube, original = skip cropping (default)")
    parser.add_argument("--track-faces", action="store_true", help="Smart subject-tracking crop instead of a static center crop (see reframe.py --help). Ignored if --aspect original.")
    parser.add_argument("--track-mode", choices=["dynamic", "static"], default="dynamic", help="dynamic = pan to follow the subject (default). static = one fixed, face-informed crop position for the whole clip - no panning, no possible camera shake. Only relevant with --track-faces.")
    parser.add_argument("--zoom-on-gesture", action="store_true", help="Ease out to a wider crop when a hand is detected (gesturing) so it doesn't get clipped, then ease back in. Only relevant with --track-faces --track-mode dynamic.")
    parser.add_argument("--gpu-detect", action="store_true", help="Opportunistically try MediaPipe's GPU delegate for face detection (experimental, falls back to CPU automatically). Only relevant with --track-faces.")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="See add_subtitles.py --help for details (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size; ignored when --language hinglish is used (default: small)")
    parser.add_argument("--reencode", action="store_true", help="Frame-accurate cuts (recommended before captioning, since it lines subtitles up with clean clip boundaries)")
    parser.add_argument("--caption-style", choices=["plain", "word", "highlight"], default="plain", help="See add_subtitles.py --help for details (default: plain)")
    parser.add_argument("--font", default="Arial", help="Font family for word/highlight caption styles (default: Arial)")
    parser.add_argument("--font-size", type=int, default=64, help="Font size for word/highlight caption styles (default: 64)")
    parser.add_argument("--text-color", default="white", help="Caption text color (default: white)")
    parser.add_argument("--highlight-color", default="yellow", help="Active-word color for --caption-style highlight/word (default: yellow)")
    parser.add_argument("--outline-color", default="black", help="Text outline color (default: black)")
    parser.add_argument("--outline-width", type=int, default=3, help="Text outline width in pixels (default: 3)")
    parser.add_argument("--no-bold", action="store_true", help="Disable bold (bold is on by default)")
    parser.add_argument("--italic", action="store_true", help="Italic text")
    parser.add_argument("--all-caps", action="store_true", help="Render captions in ALL CAPS")
    parser.add_argument("--box", action="store_true", help="Highlight the active word with a solid colored background box instead of colored text (Opus Clip style)")
    parser.add_argument("--position", choices=["bottom", "middle", "top"], default="bottom", help="Vertical placement of captions (default: bottom)")
    parser.add_argument("--max-words", type=int, default=5, help="Words per on-screen line for --caption-style highlight (default: 5)")
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if an NVIDIA GPU is detected")
    parser.add_argument("--groq", action="store_true", help="Only relevant with --language hinglish: use Groq's paid hosted Whisper API instead of the free local model. See add_subtitles.py --help for details.")
    parser.add_argument("--groq-api-key", default=None, help="Groq API key (get one at https://console.groq.com/keys). Falls back to the GROQ_API_KEY environment variable if not passed.")
    parser.add_argument("--groq-model", default=add_subtitles.DEFAULT_GROQ_MODEL, help=f"Groq Whisper model to use (default: {add_subtitles.DEFAULT_GROQ_MODEL})")
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
        style = CaptionStyle(
            font=args.font, font_size=args.font_size,
            text_rgb=parse_color(args.text_color), highlight_rgb=parse_color(args.highlight_color),
            outline_rgb=parse_color(args.outline_color), outline_width=args.outline_width,
            bold=not args.no_bold, italic=args.italic, all_caps=args.all_caps,
            box=args.box, position=args.position, margin_v=80,
        )
    except ValueError as e:
        sys.exit(str(e))

    gpu_requested = not args.no_gpu
    use_gpu_encode = gpu_requested and gpu_utils.has_nvenc()
    use_gpu_whisper = gpu_requested and gpu_utils.has_nvidia_gpu()

    clips_dir = args.output_dir / "clips"
    captioned_dir = args.output_dir / "captioned"
    clips_dir.mkdir(parents=True, exist_ok=True)
    captioned_dir.mkdir(parents=True, exist_ok=True)
    total_steps = 3 if args.aspect != "original" else 2
    step = 1

    # --- Step: cut ---
    print(f"=== Step {step}/{total_steps}: Cutting {len(clip_rows)} clip(s) "
          f"({'GPU encode' if use_gpu_encode and args.reencode else 'CPU encode' if args.reencode else 'stream copy'}) ===")
    step += 1
    suffix = args.input.suffix
    clip_paths = []
    for i, (start, end, label) in enumerate(clip_rows, start=1):
        name = label if label else f"clip_{i:03d}"
        output_path = clips_dir / f"{name}{suffix}"
        print(f"[{i}/{len(clip_rows)}] {cut_clips.format_timestamp(start)} -> {cut_clips.format_timestamp(end)}  =>  {output_path}")
        cut_clips.cut_clip(args.input, start, end, output_path, args.reencode, use_gpu_encode)
        clip_paths.append(output_path)

    # --- Step: reframe (optional) ---
    if args.aspect != "original":
        print(f"\n=== Step {step}/{total_steps}: Reframing to {args.aspect} ===")
        step += 1
        reframed_dir = args.output_dir / "reframed"
        reframed_dir.mkdir(parents=True, exist_ok=True)
        reframed_paths = []
        if args.track_faces:
            import face_tracking
            target_res = reframe.ASPECT_PRESETS[args.aspect][1]
            use_gpu_track = not args.no_gpu and gpu_utils.nvenc_works()
        for i, clip_path in enumerate(clip_paths, start=1):
            output_path = reframed_dir / clip_path.name
            suffix = " (tracking faces)" if args.track_faces else ""
            print(f"[{i}/{len(clip_paths)}] {clip_path.name} -> {args.aspect}{suffix}  =>  {output_path}")
            if args.track_faces:
                face_tracking.track_and_crop(clip_path, output_path, args.aspect, target_res, use_gpu_track, reframe.reframe_video, args.gpu_detect, args.track_mode, args.zoom_on_gesture)
            else:
                reframe.reframe_video(clip_path, output_path, args.aspect, use_gpu_encode)
            reframed_paths.append(output_path)
        clip_paths = reframed_paths

    # --- Step: transcribe + burn ---
    print(f"\n=== Step {step}/{total_steps}: Transcribing ({args.language}) and burning captions ({args.caption_style}) ===")
    common_kwargs = dict(
        caption_style=args.caption_style, style=style, max_words=args.max_words,
        burn=True, use_gpu_encode=use_gpu_encode,
    )
    if args.language == "hinglish":
        pipe = None
        groq_api_key = None
        if args.groq:
            groq_api_key = args.groq_api_key or os.environ.get("GROQ_API_KEY")
            if not groq_api_key:
                sys.exit("--groq requires an API key: pass --groq-api-key or set the GROQ_API_KEY environment variable. Get one at https://console.groq.com/keys")
            print(f"Using Groq API ({args.groq_model}) for Hinglish transcription (paid)")
        else:
            pipe = add_subtitles.load_hinglish_pipeline(use_gpu_whisper)
        for i, clip_path in enumerate(clip_paths, start=1):
            add_subtitles.process_video(clip_path, captioned_dir, i, len(clip_paths), language=None, pipe=pipe,
                                         groq_api_key=groq_api_key, groq_model=args.groq_model, **common_kwargs)
    else:
        model = add_subtitles.load_whisper_model(args.model, use_gpu_whisper)
        language = None if args.language == "auto" else args.language
        for i, clip_path in enumerate(clip_paths, start=1):
            add_subtitles.process_video(clip_path, captioned_dir, i, len(clip_paths), language=language, model=model, **common_kwargs)

    print(f"\nDone. Final captioned videos in {captioned_dir}/")


if __name__ == "__main__":
    main()
