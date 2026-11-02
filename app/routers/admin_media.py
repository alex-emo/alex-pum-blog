"""管理员图片上传接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import media as media_service
from app import models, schemas
from app.config import settings
from app.deps import require_admin_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-media"])


@router.post("/media", response_model=schemas.MediaOut)
async def upload_media(
    file: UploadFile = File(...),
    admin: models.AdminUser = Depends(require_admin_csrf),
):
    raw = await file.read()
    if len(raw) > settings.upload_max_bytes:
        limit_mb = settings.upload_max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"图片超过 {limit_mb}MB 限制")
    try:
        saved = media_service.save_image(raw, file.filename or "")
    except media_service.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.MediaOut(
        url=saved.url, thumb_url=saved.thumb_url,
        width=saved.width, height=saved.height,
    )
