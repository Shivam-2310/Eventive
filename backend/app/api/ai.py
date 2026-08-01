from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.domain.ai import router as ai_router
from app.domain.ai.speech_adapter import get_speech_adapter
from app.infra.db import SessionLocal, get_db
from app.schemas.ai import AIChatRequest
from app.workers import embeddings as emb_worker

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/suggestions")
def suggestions(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    return ai_router.suggestions_for(db, user_id)


@router.post("/chat")
async def chat(payload: AIChatRequest, user_id: int = Query(...)):
    async def _sse():
        db = SessionLocal()
        try:
            async for event in ai_router.handle_chat_stream(db, user_id, payload.message, payload.session_id):
                data = json.dumps(event["data"], default=str)
                yield f"event: {event['event']}\ndata: {data}\n\n"
        finally:
            db.close()

    return StreamingResponse(_sse(), media_type="text/event-stream")


@router.post("/rag/backfill")
def rag_backfill_route(force: bool = False, db: Session = Depends(get_db)) -> dict:
    return emb_worker.rag_backfill(db, force=force)


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket, user_id: int) -> None:  # noqa: ARG001
    await ws.accept()
    adapter = get_speech_adapter()
    if not adapter.enabled:
        await ws.send_text(json.dumps({"error": "voice_disabled"}))
        await ws.close(code=1013)
        return
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass


# --- embedding utilities (locked behind /admin in Phase 14) ---


@router.post("/embed/backfill-all")
def embed_backfill_all(force: bool = False, db: Session = Depends(get_db)) -> dict:
    return emb_worker.backfill_all(db, force=force)


@router.post("/embed/user/{user_id}")
def embed_user_route(user_id: int, db: Session = Depends(get_db)) -> dict:
    if not emb_worker.embed_user_profile(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return {"user_id": user_id, "ok": True}


@router.post("/embed/event/{event_id}")
def embed_event_route(event_id: int, db: Session = Depends(get_db)) -> dict:
    if not emb_worker.embed_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return {"event_id": event_id, "ok": True}


@router.post("/embed/interest/{interest_id}")
def embed_interest_route(interest_id: int, db: Session = Depends(get_db)) -> dict:
    if not emb_worker.embed_interest(db, interest_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "interest not found")
    return {"interest_id": interest_id, "ok": True}


@router.get("/embed/nearest/user/{user_id}")
def nearest_user_route(user_id: int, k: int = 5, db: Session = Depends(get_db)) -> list[dict]:
    rows = emb_worker.nearest(db, "vec_user_profile", "user_id", user_id, k=k)
    return [{"user_id": uid, "distance": d} for uid, d in rows]


@router.get("/embed/nearest/event/{event_id}")
def nearest_event_route(event_id: int, k: int = 5, db: Session = Depends(get_db)) -> list[dict]:
    rows = emb_worker.nearest(db, "vec_event", "event_id", event_id, k=k)
    return [{"event_id": eid, "distance": d} for eid, d in rows]
