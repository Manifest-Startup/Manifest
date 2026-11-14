"""Account settings REST helpers (e.g. profile image upload)."""

import uuid

from app.db.database import create_database_client
from app.routes.dependencies import require_user_id
from app.utils.idea_utils import (
    GENERATED_PDF_ROOT,
    _supabase_configured,
    upload_bytes_to_supabase,
)
from app.utils.logger import logger
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/account", tags=["account"])

_MAX_BYTES = 3 * 1024 * 1024
_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.post("/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
):
    """Store an avatar image and persist its URL on the user row.

    Uses durable Supabase Storage when configured (required on stateless hosts),
    otherwise the local generated-files web root (local development).
    """
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    ext = _ALLOWED_TYPES.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported or missing image type")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 3MB)")

    safe_user = "".join(c for c in user_id if c.isalnum() or c in "-_")
    if not safe_user:
        raise HTTPException(status_code=400, detail="Invalid user id")

    filename = f"{uuid.uuid4().hex}{ext}"
    if _supabase_configured():
        public_path = upload_bytes_to_supabase(
            data, "profile-pictures", f"{safe_user}/{filename}", content_type
        )
        logger.info("Stored profile picture in Supabase Storage for user %s", safe_user)
    else:
        relative = f"profile-pictures/{safe_user}/{filename}"
        dest = GENERATED_PDF_ROOT / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("Stored profile picture at %s", dest)
        public_path = f"/generated/pdfs/{relative}"
    db = create_database_client()
    response = (
        db.table("users")
        .update({"profile_picture_url": public_path})
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data or (isinstance(response.data, list) and len(response.data) == 0):
        raise HTTPException(status_code=500, detail="Failed to update profile")

    return {"profilePictureUrl": public_path}
