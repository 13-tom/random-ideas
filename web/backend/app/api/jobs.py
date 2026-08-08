from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user_id
from app.jobs_repo import create_job, create_job_from_youtube, get_job, get_unconsumed_upload, list_clip_candidates, list_clips, list_jobs, mark_upload_consumed
from app.queue import get_queue
from app.schemas import (
    ClipOut,
    ClipsResponse,
    CreateJobRequest,
    CreateJobResponse,
    JobListItem,
    JobListResponse,
    JobStatusResponse,
)
from app.storage import object_exists, presign_get

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=CreateJobResponse, status_code=201)
def create_job_route(body: CreateJobRequest, user_id: str = Depends(get_current_user_id)):
    if body.youtube_url:
        # Downloading the video itself happens in pipeline_runner (as part
        # of the background job), not here - a long YouTube video shouldn't
        # make this request hang. This route just records the job.
        job = create_job_from_youtube(user_id=user_id, youtube_url=body.youtube_url, options=body.options.model_dump())
        get_queue().enqueue(job.id)
        return CreateJobResponse(job_id=job.id)

    upload = get_unconsumed_upload(body.upload_id, user_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    try:
        exists = object_exists(upload.r2_key)
    except Exception:
        raise HTTPException(status_code=503, detail="Storage backend unavailable, try again shortly")
    if not exists:
        raise HTTPException(status_code=422, detail="Upload hasn't finished (file not found in storage yet)")

    job = create_job(user_id=user_id, r2_key=upload.r2_key, filename=upload.filename, options=body.options.model_dump())
    mark_upload_consumed(upload.id)
    get_queue().enqueue(job.id)
    return CreateJobResponse(job_id=job.id)


@router.get("", response_model=JobListResponse)
def list_jobs_route(user_id: str = Depends(get_current_user_id)):
    jobs = list_jobs(user_id)
    return JobListResponse(jobs=[JobListItem(id=j.id, status=j.status, created_at=j.created_at, source_filename=j.source_filename) for j in jobs])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_route(job_id: str, user_id: str = Depends(get_current_user_id)):
    job = get_job(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(id=job.id, status=job.status, progress_pct=job.progress_pct, error_message=job.error_message, created_at=job.created_at)


@router.get("/{job_id}/clips", response_model=ClipsResponse)
def get_job_clips_route(job_id: str, user_id: str = Depends(get_current_user_id)):
    job = get_job(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    clips = list_clips(job_id)
    candidates_by_id = {c.id: c for c in list_clip_candidates(job_id)}
    return ClipsResponse(clips=[
        ClipOut(
            id=c.id,
            title=c.label,
            score=candidates_by_id[c.candidate_id].score if c.candidate_id in candidates_by_id else 0.0,
            duration=c.duration,
            download_url=presign_get(c.r2_key),
            preview_url=presign_get(c.r2_key),
            thumbnail_url=presign_get(c.thumbnail_r2_key) if c.thumbnail_r2_key else None,
        )
        for c in clips
    ])
