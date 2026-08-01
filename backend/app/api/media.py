from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.infra.blob import blob_store

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/blob")
def get_signed_blob(k: str = Query(...), t: int = Query(...), s: str = Query(...)):
    if not blob_store.verify(k, t, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired signature")
    if not blob_store.exists(k):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    path = blob_store.path_for(k)
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=mime or "application/octet-stream")
