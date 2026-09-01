#!/usr/bin/env python3
"""End-to-end fanpage/clip-account pipeline: raw video -> cut clips ->
crop-to-subject with smooth tracking -> captioned output.

Usage:
    python fanpage_pipeline.py raw.mp4 timestamps.csv -o output
    python fanpage_pipeline.py raw.mp4 timestamps.csv -o output --aspect vertical --language hinglish
    python fanpage_pipeline.py raw.mp4 timestamps.csv -o output --remove-silence --caption-style highlight

Runs cut_clips.py, (optionally) remove_silence.py, fanpage_crop.py, and
add_subtitles.py back to back:
    output/clips/       - the cut clips (silent, no captions, original aspect)
    output/jumpcut/      - silence removed (skipped unless --remove-silence)
    output/cropped/      - cropped to --aspect with fanpage-style subject tracking
    output/captioned/    - caption files + burned-in videos, ready to post

The crop step (fanpage_crop.py) is what makes this pipeline different from
run_pipeline.py --track-faces --track-mode fanpage: it always frames by how
many people are on screen - tight zoom on a lone subject, automatically
easing out to a wider crop that fits everyone the moment a 2nd person
enters frame, and back again when they leave - tuned tighter/steadier than
the general --track-faces mode (see fanpage_crop.py for the tuning
constants).

NOTE on captions: this pipeline currently just burns plain styled captions
onto the cropped video (same engine as add_subtitles.py --caption-style).
The "Ntfp1" branded template (video-in-a-box + captions-below layout) isn't
built yet - once it exists, its compose step will replace this stage.

Automatically uses a GPU encoder (NVIDIA NVENC or Mac VideoToolbox) if
one is detected, falling back to CPU otherwise (see gpu_utils.py).
Transcription GPU acceleration (CUDA) is NVIDIA-only. Use --no-gpu to
force CPU.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import add_subtitles
import cut_clips
import fanpage_crop
import gpu_utils
import reframe
import remove_silence
from captions import CaptionStyle, parse_color


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Raw source video")
    parser.add_argument("timestamps", type=Path, help="CSV file with start,end[,label] rows")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("fanpage_output"), help="Where to write clips/, cropped/, and captioned/ (default: ./fanpage_output)")
    parser.add_argument("--aspect", choices=list(reframe.ASPECT_RATIOS), default="vertical", help="vertical = 9:16 Reels/Stories/Shorts (default), square = 1:1 feed/carousel, portrait = 4:5 IG feed, landscape = 16:9 YouTube")
    parser.add_argument("--gpu-detect", action="store_true", help="Opportunistically try MediaPipe's GPU delegate for face detection (experimental, falls back to CPU automatically)")
    parser.add_argument("--language", choices=["en", "hi", "auto", "hinglish"], default="auto", help="See add_subtitles.py --help for details (default: auto)")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size for en/hi/auto; ignored when --language hinglish is used (default: small)")
    parser.add_argument("--hinglish-model", default=add_subtitles.DEFAULT_HINGLISH_MODEL, choices=add_subtitles.HINGLISH_MODEL_CHOICES, help="Which local Hinglish model size to use (only relevant with --language hinglish, no --groq): swift/tiny (default, fastest), prime/small (more accurate), apex/large (largest/most accurate).")
    parser.add_argument("--reencode", action="store_true", help="Frame-accurate cuts (recommended before captioning, since it lines subtitles up with clean clip boundaries)")
    parser.add_argument("--remove-silence", action="store_true", help="Jump-cut out silent gaps before cropping/captioning, like Descript/CapCut auto-cut. See remove_silence.py --help for details.")
    parser.add_argument("--min-silence", type=float, default=remove_silence.DEFAULT_MIN_SILENCE, help=f"Only relevant with --remove-silence: minimum gap duration (seconds) to cut (default: {remove_silence.DEFAULT_MIN_SILENCE})")
    parser.add_argument("--padding", type=float, default=remove_silence.DEFAULT_PADDING, help=f"Only relevant with --remove-silence: seconds kept just before/after each spoken segment so words aren't clipped (default: {remove_silence.DEFAULT_PADDING})")
    parser.add_argument("--noise-db", default=remove_silence.DEFAULT_NOISE_DB, help=f"Only relevant with --remove-silence: volume threshold below which audio counts as silence (default: {remove_silence.DEFAULT_NOISE_DB})")
    parser.add_argument("--caption-style", choices=["plain", "word", "highlight"], default="highlight", help="See add_subtitles.py --help for details (default: highlight)")
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
    parser.add_argument("--no-gpu", action="store_true", help="Force CPU even if a GPU encoder (NVIDIA NVENC or Mac VideoToolbox) is detected")
    parser.add_argument("--groq", action="store_true", help="Use Groq's paid hosted Whisper API instead of the free local model, for any --language. See add_subtitles.py --help for details.")
    parser.add_argument("--groq-api-key", default=None, help="Groq API key (get one at https://console.groq.com/keys). Falls back to the GROQ_API_KEY environment variable if not passed.")
    parser.add_argument("--groq-model", default=None, help="Groq Whisper model to use (default: whisper-large-v3-turbo)")
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
    use_gpu_encode = gpu_requested and gpu_utils.gpu_available()
    use_gpu_whisper = gpu_requested and gpu_utils.has_nvidia_gpu()
    use_gpu_track = gpu_requested and gpu_utils.gpu_verified()

    clips_dir = args.output_dir / "clips"
    cropped_dir = args.output_dir / "cropped"
    captioned_dir = args.output_dir / "captioned"
    clips_dir.mkdir(parents=True, exist_ok=True)
    cropped_dir.mkdir(parents=True, exist_ok=True)
    captioned_dir.mkdir(parents=True, exist_ok=True)
    total_steps = 3 if not args.remove_silence else 4
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

    # --- Step: remove silence (optional) ---
    if args.remove_silence:
        print(f"\n=== Step {step}/{total_steps}: Removing silence (jump cut) ===")
        step += 1
        jumpcut_dir = args.output_dir / "jumpcut"
        jumpcut_dir.mkdir(parents=True, exist_ok=True)
        jumpcut_paths = []
        for i, clip_path in enumerate(clip_paths, start=1):
            output_path = jumpcut_dir / clip_path.name
            old_dur, new_dur = remove_silence.remove_silence(
                clip_path, output_path, use_gpu_encode, args.min_silence, args.padding, args.noise_db
            )
            cut = old_dur - new_dur
            pct = (cut / old_dur * 100) if old_dur else 0
            print(f"[{i}/{len(clip_paths)}] {clip_path.name}: {old_dur:.1f}s -> {new_dur:.1f}s (removed {cut:.1f}s, {pct:.0f}%)  =>  {output_path}")
            jumpcut_paths.append(output_path)
        clip_paths = jumpcut_paths

    # --- Step: crop to subject(s) with fanpage-style tracking ---
    print(f"\n=== Step {step}/{total_steps}: Cropping to {args.aspect} (fanpage subject tracking) ===")
    step += 1
    target_res = reframe.ASPECT_PRESETS[args.aspect][1]
    cropped_paths = []
    for i, clip_path in enumerate(clip_paths, start=1):
        output_path = cropped_dir / clip_path.name
        print(f"[{i}/{len(clip_paths)}] {clip_path.name} -> {args.aspect}  =>  {output_path}")
        fanpage_crop.fanpage_track_and_crop(
            clip_path, output_path, args.aspect, target_res, use_gpu_track, reframe.reframe_video, args.gpu_detect
        )
        cropped_paths.append(output_path)
    clip_paths = cropped_paths

    # --- Step: transcribe + burn ---
    print(f"\n=== Step {step}/{total_steps}: Transcribing ({args.language}) and burning captions ({args.caption_style}) ===")
    common_kwargs = dict(
        caption_style=args.caption_style, style=style, max_words=args.max_words,
        burn=True, use_gpu_encode=use_gpu_encode,
    )
    is_hinglish = args.language == "hinglish"

    if args.groq:
        groq_api_key = args.groq_api_key or os.environ.get("GROQ_API_KEY")
        if not groq_api_key:
            sys.exit("--groq requires an API key: pass --groq-api-key or set the GROQ_API_KEY environment variable. Get one at https://console.groq.com/keys")
        from add_subtitles_groq import DEFAULT_GROQ_MODEL
        args.groq_model = args.groq_model or DEFAULT_GROQ_MODEL
        label = "Hinglish" if is_hinglish else args.language
        print(f"Using Groq API ({args.groq_model}) for {label} transcription (paid)")
        language = None if args.language in ("auto", "hinglish") else args.language
        for i, clip_path in enumerate(clip_paths, start=1):
            add_subtitles.process_video(clip_path, captioned_dir, i, len(clip_paths), language=language, pipe=None,
                                         groq_api_key=groq_api_key, groq_model=args.groq_model, hinglish=is_hinglish, **common_kwargs)
    elif is_hinglish:
        pipe = add_subtitles.load_hinglish_pipeline(use_gpu_whisper, args.hinglish_model)
        for i, clip_path in enumerate(clip_paths, start=1):
            add_subtitles.process_video(clip_path, captioned_dir, i, len(clip_paths), language=None, pipe=pipe, **common_kwargs)
    else:
        model = add_subtitles.load_whisper_model(args.model, use_gpu_whisper)
        language = None if args.language == "auto" else args.language
        for i, clip_path in enumerate(clip_paths, start=1):
            add_subtitles.process_video(clip_path, captioned_dir, i, len(clip_paths), language=language, model=model, **common_kwargs)

    print(f"\nDone. Final captioned videos in {captioned_dir}/")


if __name__ == "__main__":
    main()
