from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.domain import notification_service
from app.infra.db import get_db
from app.infra.ws_manager import manager
from app.schemas.notification import NotificationRead

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(
    user_id: int = Query(...),
    unread_only: bool = False,
    db: Session = Depends(get_db),
) -> list[NotificationRead]:
    return [
        NotificationRead.model_validate(n)
        for n in notification_service.list_notifications(db, user_id, unread_only=unread_only)
    ]


@router.post("/notifications/{notif_id}/read")
def read_notification(notif_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    ok = notification_service.mark_read(db, user_id, notif_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    return {"ok": True}


@router.websocket("/ws/notifications")
async def ws_notifications(ws: WebSocket, user_id: int) -> None:
    await manager.connect_user(user_id, ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except TimeoutError:
                try:
                    await ws.send_text(json.dumps({"channel": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_user(user_id, ws)
