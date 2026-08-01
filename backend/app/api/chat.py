from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.domain import chat_service, notification_service
from app.infra.db import get_db
from app.infra.ws_manager import manager
from app.models.networking import Connection as ConnectionModel
from app.schemas.networking import (
    AttendTogetherInvite,
    ConnectionCreate,
    ConnectionRead,
    ConnectionUpdate,
    MessageCreate,
    MessageRead,
    ThreadRead,
)

router = APIRouter(tags=["chat"])


@router.post("/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ConnectionCreate,
    requester_id: int = Query(...),
    db: Session = Depends(get_db),
) -> ConnectionRead:
    # Detect whether this POST will actually create a new row, so we only push
    # the notification once even if a client retries the same request.
    from sqlalchemy import and_, or_
    from sqlalchemy import select as _select

    pre_existing = db.execute(
        _select(ConnectionModel).where(
            or_(
                and_(
                    ConnectionModel.requester_id == requester_id,
                    ConnectionModel.receiver_id == payload.receiver_id,
                ),
                and_(
                    ConnectionModel.requester_id == payload.receiver_id,
                    ConnectionModel.receiver_id == requester_id,
                ),
            )
        )
    ).scalar_one_or_none()
    try:
        c = chat_service.create_connection(db, requester_id, payload.receiver_id, payload.hook_interest_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if pre_existing is None:
        from app.domain import user_service

        requester = user_service.get_user(db, requester_id)
        notification_service.push(
            db,
            user_id=payload.receiver_id,
            type_="connection_request",
            title="New connection request",
            body=f"{requester.name if requester else 'Someone'} wants to connect",
            deep_link=f"/connections/{c.id}",
        )
    return ConnectionRead.model_validate(c)


@router.patch("/connections/{connection_id}", response_model=ConnectionRead)
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> ConnectionRead:
    # Snapshot the prior status so we can suppress the notification when the
    # PATCH is a no-op (e.g. accepting an already-accepted row).
    prior = db.get(ConnectionModel, connection_id)
    prior_status = prior.status if prior else None
    try:
        c = chat_service.update_connection_status(db, user_id, connection_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    if payload.status == "accepted" and prior_status != "accepted":
        notification_service.push(
            db,
            user_id=c.requester_id,
            type_="connection_accepted",
            title="Connection accepted",
            body="You can start chatting now",
            deep_link="/threads",
        )
    return ConnectionRead.model_validate(c)


@router.get("/connections", response_model=list[ConnectionRead])
def list_connections(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[ConnectionRead]:
    return [ConnectionRead.model_validate(c) for c in chat_service.list_connections(db, user_id)]


@router.get("/threads", response_model=list[ThreadRead])
def list_threads(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[ThreadRead]:
    return [ThreadRead.model_validate(t) for t in chat_service.list_threads_for_user(db, user_id)]


@router.get("/threads/{thread_id}/messages", response_model=list[MessageRead])
def list_messages(thread_id: int, user_id: int = Query(...), db: Session = Depends(get_db)) -> list[MessageRead]:
    if not chat_service.is_participant(db, thread_id, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a participant")
    return [MessageRead.model_validate(chat_service.message_to_dict(m)) for m in chat_service.list_messages(db, thread_id)]


@router.post("/threads/{thread_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def post_message(
    thread_id: int,
    payload: MessageCreate,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> MessageRead:
    if not chat_service.is_participant(db, thread_id, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a participant")
    try:
        m = chat_service.post_message(db, thread_id, user_id, payload.body, payload.kind, payload.payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    msg_dict = chat_service.message_to_dict(m)
    # broadcast to all other participants
    from sqlalchemy import select

    from app.models.chat import ChatThreadParticipant

    others = db.execute(
        select(ChatThreadParticipant.user_id).where(
            ChatThreadParticipant.thread_id == thread_id, ChatThreadParticipant.user_id != user_id
        )
    ).scalars().all()
    for uid in others:
        _fire(manager.send_to_user(uid, {"channel": "chat", "data": msg_dict}))
        notification_service.push(
            db,
            user_id=uid,
            type_="dm_new",
            title="New message",
            body=(payload.body or "…")[:140],
            deep_link=f"/threads/{thread_id}",
        )
    return MessageRead.model_validate(msg_dict)


@router.post("/threads/{thread_id}/attend-together", response_model=MessageRead)
def attend_together(
    thread_id: int,
    payload: AttendTogetherInvite,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> MessageRead:
    if not chat_service.is_participant(db, thread_id, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a participant")
    try:
        m = chat_service.attend_together_invite(db, thread_id, user_id, payload.event_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MessageRead.model_validate(chat_service.message_to_dict(m))


@router.post("/threads/{thread_id}/attend-together/{message_id}/accept", response_model=MessageRead)
def attend_together_accept(
    thread_id: int,
    message_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> MessageRead:
    if not chat_service.is_participant(db, thread_id, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a participant")
    try:
        m = chat_service.attend_together_accept(db, thread_id, user_id, message_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MessageRead.model_validate(chat_service.message_to_dict(m))


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket, user_id: int) -> None:
    await manager.connect_user(user_id, ws)
    try:
        while True:
            # Keep the socket open; server pushes messages via manager.
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


def _fire(coro) -> None:  # noqa: ANN001
    """Best-effort WS delivery from either sync or async context."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
        return
    except RuntimeError:
        pass
    try:
        import anyio.from_thread

        async def _runner() -> None:
            await coro

        anyio.from_thread.run(_runner)
    except Exception:
        pass
