"""Env-driven settings. Every value has a sane local-dev default so the
backend runs out of the box against a local Postgres/MinIO without any
cloud account - see web/backend/.env.example for what to override for a
real deployment.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./kalakaar.db"

    # Supabase auth. New projects sign session JWTs asymmetrically (ES256)
    # by default - verified via supabase_url's JWKS endpoint, no secret
    # needed. supabase_jwt_secret is only used as a fallback for tokens
    # that come in signed HS256 (older projects still on a static secret,
    # or not-yet-expired tokens from before a project migrated) - see
    # app/auth.py for how the two paths are chosen.
    supabase_url: str = "https://project-ref.supabase.co"
    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"

    # R2 (S3-compatible) object storage
    r2_endpoint_url: str = "http://localhost:9000"  # MinIO for local dev
    r2_access_key_id: str = "minioadmin"
    r2_secret_access_key: str = "minioadmin"
    r2_bucket_name: str = "kalakaar-dev"
    presigned_url_expiry_seconds: int = 3600
    presigned_download_expiry_seconds: int = 900

    # Video pipeline
    ffmpeg_bulk_cutter_dir: Path = Path(__file__).resolve().parents[3] / "ffmpeg-bulk-cutter"
    clip_scoring_provider: str = "openrouter"  # or "local" for a self-hosted dev LLM
    openrouter_api_key: str | None = None
    local_llm_base_url: str | None = None

    # Job queue: "local" fires the internal endpoint in-process (dev,
    # single-instance); "cloud_tasks" enqueues a real push task (prod, scale-to-zero).
    queue_backend: str = "local"
    internal_base_url: str = "http://localhost:8000"  # where /internal/jobs/{id}/run is reachable from the queue
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    cloud_tasks_queue_name: str | None = None


settings = Settings()
