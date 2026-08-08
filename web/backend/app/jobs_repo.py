"""DB access for jobs/clip_candidates/clips. Kept as plain functions
(each opening its own short-lived session) rather than a repository class -
there's no shared state worth wrapping a class around yet.
"""
from sqlmodel import Session, create_engine, select

from app.config import settings
from app.models import Clip, ClipCandidate, Job, Upload

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db():
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)


def create_upload_record(user_id: str, r2_key: str, filename: str, content_type: str) -> Upload:
    upload = Upload(user_id=user_id, r2_key=r2_key, filename=filename, content_type=content_type)
    with Session(engine) as session:
        session.add(upload)
        session.commit()
        session.refresh(upload)
        return upload


def get_unconsumed_upload(upload_id: str, user_id: str) -> Upload | None:
    with Session(engine) as session:
        upload = session.get(Upload, upload_id)
        if upload is None or upload.user_id != user_id or upload.consumed:
            return None
        return upload


def mark_upload_consumed(upload_id: str):
    with Session(engine) as session:
        upload = session.get(Upload, upload_id)
        if upload is not None:
            upload.consumed = True
            session.add(upload)
            session.commit()


def create_job(user_id: str, r2_key: str, filename: str, options: dict) -> Job:
    job = Job(user_id=user_id, source_r2_key=r2_key, source_filename=filename, options=options)
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def create_job_from_youtube(user_id: str, youtube_url: str, options: dict) -> Job:
    job = Job(user_id=user_id, source_youtube_url=youtube_url, source_filename=youtube_url, options=options)
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def get_job(job_id: str, user_id: str) -> Job | None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != user_id:
            return None
        return job


def get_job_unscoped(job_id: str) -> Job | None:
    """Used only by the internal /internal/jobs/{id}/run endpoint, which
    isn't called with a user's JWT (it's invoked by the queue)."""
    with Session(engine) as session:
        return session.get(Job, job_id)


def list_jobs(user_id: str) -> list[Job]:
    with Session(engine) as session:
        return list(session.exec(select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc())))


def update_job_status(job_id: str, status: str | None = None, progress_pct: int | None = None, error_message: str | None = None):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if progress_pct is not None:
            job.progress_pct = progress_pct
        if error_message is not None:
            job.error_message = error_message
        session.add(job)
        session.commit()


def add_clip_candidate(job_id: str, start_s: float, end_s: float, score: float, title: str, reason: str, llm_model: str | None, prompt_version: str | None) -> ClipCandidate:
    candidate = ClipCandidate(job_id=job_id, start_s=start_s, end_s=end_s, score=score, title=title, reason=reason, llm_model=llm_model, prompt_version=prompt_version)
    with Session(engine) as session:
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        return candidate


def add_clip(job_id: str, label: str, r2_key: str, duration: float, aspect: str, candidate_id: str | None = None, thumbnail_r2_key: str | None = None) -> Clip:
    clip = Clip(job_id=job_id, candidate_id=candidate_id, label=label, r2_key=r2_key, duration=duration, aspect=aspect, thumbnail_r2_key=thumbnail_r2_key)
    with Session(engine) as session:
        session.add(clip)
        session.commit()
        session.refresh(clip)
        return clip


def list_clips(job_id: str) -> list[Clip]:
    with Session(engine) as session:
        return list(session.exec(select(Clip).where(Clip.job_id == job_id)))


def list_clip_candidates(job_id: str) -> list[ClipCandidate]:
    with Session(engine) as session:
        return list(session.exec(select(ClipCandidate).where(ClipCandidate.job_id == job_id)))
