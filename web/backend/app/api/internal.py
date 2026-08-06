"""Internal-only endpoint the job queue calls (see queue.py) - not part of
the public API contract, never called by the frontend directly. No auth
dependency here since it's not reached with a user's Supabase JWT; in
production this should sit behind network-level protection (e.g. Cloud
Run's built-in OIDC verification for Cloud Tasks push targets) rather than
being reachable from the public internet unauthenticated.
"""
from fastapi import APIRouter, BackgroundTasks

from app.pipeline_runner import run_job

router = APIRouter(prefix="/internal/jobs", tags=["internal"])


@router.post("/{job_id}/run", status_code=202)
def run_job_route(job_id: str, background_tasks: BackgroundTasks):
    # Runs after the response is sent, so the queue's HTTP call returns
    # immediately instead of blocking for the job's full duration.
    background_tasks.add_task(run_job, job_id)
    return {"accepted": True}
