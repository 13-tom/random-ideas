"""R2 (S3-compatible) object storage helpers. Uploads/downloads never
proxy video bytes through this API process - the frontend PUTs directly
to a presigned URL, and clip downloads are presigned GET URLs the
frontend fetches straight from R2. This process only touches bytes on
disk while a background job is actively running ffmpeg/Whisper on them.
"""
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def presign_put(key: str, content_type: str) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.presigned_url_expiry_seconds,
    )


def presign_get(key: str, expires: int | None = None) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key},
        ExpiresIn=expires or settings.presigned_download_expiry_seconds,
    )


def object_exists(key: str) -> bool:
    """False only means "confirmed not there" (a real 404 from the storage
    API) - any other failure (e.g. the endpoint being unreachable) re-raises
    instead of being silently treated as "doesn't exist", so callers can
    tell "not uploaded yet" apart from "storage backend is down"."""
    client = get_s3_client()
    try:
        client.head_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def download_file(key: str, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    get_s3_client().download_file(settings.r2_bucket_name, key, str(local_path))


def upload_file(local_path: Path, key: str, content_type: str | None = None):
    extra_args = {"ContentType": content_type} if content_type else {}
    get_s3_client().upload_file(str(local_path), settings.r2_bucket_name, key, ExtraArgs=extra_args)
