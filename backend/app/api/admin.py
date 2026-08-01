from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domain import admin_service, reel_service
from app.infra.db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.delete("/reels/{reel_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_reel(reel_id: int, db: Session = Depends(get_db)) -> None:
    ok = reel_service.admin_delete_reel(db, reel_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reel not found")
    admin_service.log_admin_action(
        db,
        actor_user_id=None,
        action="reel_delete",
        target_type="reel",
        target_id=reel_id,
    )


@router.get("/audit-log")
def list_audit(db: Session = Depends(get_db)) -> list[dict]:
    rows = admin_service.list_audit_logs(db)
    return [
        {
            "id": r.id,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "payload": r.payload,
            "created_at": r.created_at,
        }
        for r in rows
    ]
