"""Request/response shapes - kept in exact lockstep with web/API_CONTRACT.md,
the source of truth shared with the frontend."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Aspect = Literal["original", "vertical", "square", "portrait", "landscape"]
CaptionStyle = Literal["plain", "word", "highlight"]
Language = Literal["en", "hi", "auto", "hinglish"]


class UploadRequest(BaseModel):
    filename: str
    content_type: str


class UploadResponse(BaseModel):
    upload_id: str
    put_url: str
    r2_key: str


class JobOptions(BaseModel):
    aspect: Aspect = "vertical"
    track_faces: bool = False
    caption_style: CaptionStyle = "highlight"
    language: Language = "auto"
    min_duration: float = Field(default=20.0, gt=0)
    max_duration: float = Field(default=90.0, gt=0)
    max_clips: int = Field(default=10, gt=0, le=50)


class CreateJobRequest(BaseModel):
    upload_id: str
    options: JobOptions = JobOptions()


class CreateJobResponse(BaseModel):
    job_id: str


class JobListItem(BaseModel):
    id: str
    status: str
    created_at: datetime
    source_filename: str


class JobListResponse(BaseModel):
    jobs: list[JobListItem]


class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress_pct: int
    error_message: str | None
    created_at: datetime


class ClipOut(BaseModel):
    id: str
    title: str
    score: float
    duration: float
    download_url: str
    preview_url: str
    thumbnail_url: str | None


class ClipsResponse(BaseModel):
    clips: list[ClipOut]
