"""SQLModel persistence models. No migration framework wired up yet
(SQLModel.metadata.create_all() runs at startup - see main.py) - fine for
an MVP with a small, still-changing schema; add Alembic once the schema
stabilizes and there's real data to migrate around.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Job statuses, in pipeline order. "queued" -> ... -> "done" | "failed".
JOB_STATUSES = ("queued", "transcribing", "scoring", "cutting", "reframing", "captioning", "uploading", "done", "failed")


class Upload(SQLModel, table=True):
    """Created when POST /api/uploads issues a presigned PUT URL, so
    POST /api/jobs (which only receives upload_id, per the API contract)
    can look up the r2_key/filename and confirm the object belongs to the
    calling user before starting a job."""
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(index=True)
    r2_key: str
    filename: str
    content_type: str
    consumed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class Job(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(index=True)
    source_r2_key: str
    source_filename: str
    options: dict = Field(sa_column=Column(JSON))
    status: str = Field(default="queued", index=True)
    progress_pct: int = Field(default=0)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


class ClipCandidate(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    job_id: str = Field(index=True, foreign_key="job.id")
    start_s: float
    end_s: float
    score: float
    title: str
    reason: str
    llm_model: str | None = Field(default=None)
    prompt_version: str | None = Field(default=None)
    accepted: bool = Field(default=True)


class Clip(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    job_id: str = Field(index=True, foreign_key="job.id")
    candidate_id: str | None = Field(default=None, foreign_key="clipcandidate.id")
    label: str
    r2_key: str
    thumbnail_r2_key: str | None = Field(default=None)
    duration: float
    aspect: str
