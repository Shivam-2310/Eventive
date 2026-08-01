from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.domain import reel_service
from app.infra.db import get_db
from app.schemas.reel import ReelInteractionCreate, ReelRead
from app.workers.transcode import process_reel

router = APIRouter(prefix="/reels", tags=["reels"])


def _to_read(reel) -> ReelRead:  # noqa: ANN001
    reel_service.refresh_signed_urls(reel)
    return ReelRead.model_validate(reel)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_reel(
    background: BackgroundTasks,
    user_id: int = Query(...),
    event_id: int | None = Form(default=None),
    speaker_id: int | None = Form(default=None),
    caption: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    reel = reel_service.create_reel(
        db, user_id=user_id, filename=file.filename or "upload.mp4", content=content,
        event_id=event_id, speaker_id=speaker_id, caption=caption,
    )
    background.add_task(process_reel, reel.id)
    return {"reel_id": reel.id, "status": reel.status}


@router.get("/feed")
def feed(user_id: int = Query(...), cursor: int | None = None, limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    items = reel_service.list_feed(db, user_id=user_id, cursor=cursor, limit=limit)
    return [
        {
            "reel": _to_read(item["reel"]).model_dump(),
            "score": item["score"],
            "likes": item["likes"],
        }
        for item in items
    ]


@router.get("/{reel_id}", response_model=ReelRead)
def get_reel(reel_id: int, db: Session = Depends(get_db)) -> ReelRead:
    r = reel_service.get_reel(db, reel_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reel not found")
    return _to_read(r)


@router.post("/{reel_id}/interactions")
def record_reel_interaction(
    reel_id: int,
    payload: ReelInteractionCreate,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if not reel_service.get_reel(db, reel_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reel not found")
    try:
        row = reel_service.record_interaction(db, user_id, reel_id, payload.type, payload.watch_ms)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": row.id, "type": row.type}


@router.delete("/{reel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reel(reel_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> None:
    ok = reel_service.delete_own_reel(db, user_id, reel_id)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not owner or not found")
