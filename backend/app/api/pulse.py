from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.domain import pulse_service
from app.infra.db import get_db
from app.infra.ws_manager import manager

router = APIRouter(tags=["pulse"])


@router.get("/admin/pulse/snapshot")
def snapshot(db: Session = Depends(get_db)) -> dict:
    return pulse_service.aggregate(db)


@router.websocket("/ws/admin/pulse")
async def ws_pulse(ws: WebSocket) -> None:
    await manager.connect_channel(pulse_service.PULSE_CHANNEL, ws)
    try:
        # push a first snapshot immediately
        from app.infra.db import SessionLocal

        db = SessionLocal()
        try:
            payload = pulse_service.aggregate(db)
        finally:
            db.close()
        await ws.send_text(json.dumps({"channel": "pulse", "data": payload}, default=str))
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
        await manager.disconnect_channel(pulse_service.PULSE_CHANNEL, ws)
