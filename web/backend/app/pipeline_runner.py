"""Orchestrates a job end to end by running generate_timestamps.py and
run_pipeline.py as subprocesses of the existing, unmodified CLI scripts in
ffmpeg-bulk-cutter/ - not by importing their internals into this
long-lived API process. That keeps a crash in mediapipe/torch/ffmpeg
scoped to one job's subprocess instead of taking down the service, and
lets each job get a hard-boundaried temp workdir that's always cleaned up.

Both scripts already print "=== Step i/N: ... ===" lines for their own
CLI users - reused here as a free progress signal instead of needing any
callback/library refactor of that tested code.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.jobs_repo import add_clip, add_clip_candidate, get_job_unscoped, update_job_status
from app.storage import download_file, upload_file

# Reuse ffmpeg_utils.get_media_duration instead of duplicating an ffprobe
# call - same PYTHONPATH-extension approach the Dockerfile uses to let this
# service import from ffmpeg-bulk-cutter/ without vendoring or packaging it.
if str(settings.ffmpeg_bulk_cutter_dir) not in sys.path:
    sys.path.insert(0, str(settings.ffmpeg_bulk_cutter_dir))
from ffmpeg_utils import get_media_duration  # noqa: E402

STEP_RE = re.compile(r"=== Step (\d+)/(\d+):")

# Coarse phase weighting across the whole job: timestamp generation is
# ~step 1 of the two subprocesses, the cut/reframe/caption pipeline is the
# much heavier ~step 2 - split progress accordingly rather than evenly.
GENERATE_TIMESTAMPS_PCT_SPAN = (0, 25)
RUN_PIPELINE_PCT_SPAN = (25, 90)


def run_job(job_id: str):
    job = get_job_unscoped(job_id)
    if job is None:
        print(f"[pipeline_runner] job {job_id} not found, skipping")
        return

    workdir = Path(tempfile.mkdtemp(prefix=f"katgaireel_job_{job_id}_"))
    try:
        _run(job_id, job, workdir)
    except Exception as e:
        print(f"[pipeline_runner] job {job_id} failed: {e}")
        update_job_status(job_id, status="failed", error_message=str(e))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _run(job_id: str, job, workdir: Path):
    options = job.options

    source_path = _acquire_source(job_id, job, workdir)

    update_job_status(job_id, status="transcribing", progress_pct=10 if job.source_youtube_url else 0)
    timestamps_csv = workdir / "timestamps.csv"
    metadata_json = workdir / "timestamps_metadata.json"
    generate_cmd = [
        "python", "generate_timestamps.py", str(source_path),
        "-o", str(timestamps_csv),
        "--metadata-json", str(metadata_json),
        "--language", options["language"],
        "--min-duration", str(options["min_duration"]),
        "--max-duration", str(options["max_duration"]),
        "--max-clips", str(options["max_clips"]),
        "--provider", settings.clip_scoring_provider,
    ]
    _run_and_track(generate_cmd, job_id, GENERATE_TIMESTAMPS_PCT_SPAN, status_for_step={1: "transcribing", 2: "transcribing", 3: "scoring", 4: "scoring"})

    update_job_status(job_id, status="cutting", progress_pct=RUN_PIPELINE_PCT_SPAN[0])
    output_dir = workdir / "output"
    pipeline_cmd = [
        "python", "run_pipeline.py", str(source_path), str(timestamps_csv),
        "-o", str(output_dir),
        "--aspect", options["aspect"],
        "--caption-style", options["caption_style"],
        "--language", options["language"],
        "--reencode",
    ]
    if options.get("track_faces"):
        pipeline_cmd += ["--track-faces"]
    _run_and_track(pipeline_cmd, job_id, RUN_PIPELINE_PCT_SPAN, status_for_step={1: "cutting", 2: "reframing", 3: "captioning"})

    update_job_status(job_id, status="uploading", progress_pct=90)
    _upload_results(job_id, job, output_dir, metadata_json)
    update_job_status(job_id, status="done", progress_pct=100)


def _acquire_source(job_id: str, job, workdir: Path) -> Path:
    """Gets the raw source video onto local disk, from wherever it comes
    from - an R2 upload, or (job.source_youtube_url set) a YouTube link the
    backend downloads itself. Either way, generate_timestamps.py/
    run_pipeline.py downstream just see a local file path - they don't
    know or care which source type this job was."""
    dest_dir = workdir / "source"
    dest_dir.mkdir(parents=True, exist_ok=True)

    if job.source_youtube_url:
        update_job_status(job_id, status="downloading", progress_pct=0)
        return _download_youtube(job.source_youtube_url, dest_dir, job_id)

    source_path = dest_dir / Path(job.source_r2_key).name
    download_file(job.source_r2_key, source_path)
    return source_path


def _download_youtube(url: str, dest_dir: Path, job_id: str) -> Path:
    output_template = str(dest_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",  # YouTube's extraction increasingly needs a JS runtime to solve signature challenges
        "-f", "mp4/bestvideo+bestaudio",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", output_template,
        url,
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        print(f"[job {job_id}] [yt-dlp] {line.rstrip()}")
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"yt-dlp failed to download {url} (exit {returncode}) - is the link valid/public?")

    downloaded = [p for p in dest_dir.iterdir() if p.suffix == ".mp4"]
    if not downloaded:
        raise RuntimeError(f"yt-dlp reported success but produced no .mp4 file for {url}")
    return downloaded[0]


def _run_and_track(cmd: list[str], job_id: str, pct_span: tuple[int, int], status_for_step: dict[int, str]):
    base_pct, end_pct = pct_span
    process = subprocess.Popen(cmd, cwd=settings.ffmpeg_bulk_cutter_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        print(f"[job {job_id}] {line.rstrip()}")
        match = STEP_RE.search(line)
        if not match:
            continue
        step, total = int(match.group(1)), int(match.group(2))
        pct = base_pct + int((end_pct - base_pct) * (step - 1) / total)
        status = status_for_step.get(step)
        update_job_status(job_id, status=status, progress_pct=pct)

    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"Command exited {returncode}: {' '.join(cmd)}")


def _upload_results(job_id: str, job, output_dir: Path, metadata_json: Path):
    metadata_by_label = {}
    if metadata_json.exists():
        metadata_by_label = {entry["label"]: entry for entry in json.loads(metadata_json.read_text())}

    captioned_dir = output_dir / "captioned"
    videos = sorted(captioned_dir.glob("*_captioned.*")) if captioned_dir.exists() else []
    for video_path in videos:
        label = video_path.stem.removesuffix("_captioned")
        meta = metadata_by_label.get(label, {})

        candidate = add_clip_candidate(
            job_id=job_id,
            start_s=meta.get("start", 0.0),
            end_s=meta.get("end", 0.0),
            score=meta.get("score", 0.0),
            title=meta.get("title") or label,
            reason=meta.get("reason", ""),
            llm_model=meta.get("llm_model"),
            prompt_version=meta.get("prompt_version"),
        )

        clip_key = f"results/{job.user_id}/{job_id}/{video_path.name}"
        upload_file(video_path, clip_key, content_type="video/mp4")
        add_clip(
            job_id=job_id,
            candidate_id=candidate.id,
            label=meta.get("title") or label,
            r2_key=clip_key,
            duration=get_media_duration(video_path),
            aspect=job.options["aspect"],
        )
