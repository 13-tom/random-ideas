import uuid

from fastapi import APIRouter, Depends

from app.auth import get_current_user_id
from app.jobs_repo import create_upload_record
from app.schemas import UploadRequest, UploadResponse
from app.storage import presign_put

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("", response_model=UploadResponse)
def create_upload(body: UploadRequest, user_id: str = Depends(get_current_user_id)):
    r2_key = f"uploads/{user_id}/{uuid.uuid4()}/{body.filename}"
    put_url = presign_put(r2_key, body.content_type)
    # Persisted (rather than deriving r2_key from upload_id later) so
    # POST /api/jobs, which per the API contract only receives upload_id,
    # can look up the key and confirm it belongs to the calling user.
    upload = create_upload_record(user_id=user_id, r2_key=r2_key, filename=body.filename, content_type=body.content_type)
    return UploadResponse(upload_id=upload.id, put_url=put_url, r2_key=r2_key)
