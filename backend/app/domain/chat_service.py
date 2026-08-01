from __future__ import annotations

import json
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain.ai.llm_provider import get_provider
from app.models.chat import ChatThread, ChatThreadParticipant, Message
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.interest import Interest, UserInterest
from app.models.networking import Connection
from app.models.user import User

VALID_MESSAGE_KINDS = {"text", "attend_together_invite", "attend_together_accepted", "system", "icebreaker"}


def create_connection(db: Session, requester_id: int, receiver_id: int, hook_interest_id: int | None) -> Connection:
    if requester_id == receiver_id:
        raise ValueError("cannot connect to self")
    existing = db.execute(
        select(Connection).where(
            or_(
                and_(Connection.requester_id == requester_id, Connection.receiver_id == receiver_id),
                and_(Connection.requester_id == receiver_id, Connection.receiver_id == requester_id),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    c = Connection(
        requester_id=requester_id,
        receiver_id=receiver_id,
        hook_interest_id=hook_interest_id,
        status="pending",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_connection_status(db: Session, user_id: int, connection_id: int, status: str) -> Connection | None:
    if status not in {"accepted", "declined", "blocked", "pending"}:
        raise ValueError("invalid status")
    c = db.get(Connection, connection_id)
    if not c:
        return None
    # only the receiver can accept / decline; either party can block.
    if status in {"accepted", "declined"} and c.receiver_id != user_id:
        raise PermissionError("only the receiver can accept or decline")
    if status == "blocked" and user_id not in (c.requester_id, c.receiver_id):
        raise PermissionError("not a participant")
    prev_status = c.status
    c.status = status
    db.commit()
    db.refresh(c)
    if status == "accepted" and prev_status != "accepted":
        _ensure_thread_for(db, c)
    return c


def list_connections(db: Session, user_id: int) -> list[Connection]:
    stmt = select(Connection).where(
        (Connection.requester_id == user_id) | (Connection.receiver_id == user_id)
    ).order_by(Connection.id.desc())
    return list(db.execute(stmt).scalars().all())


def _ensure_thread_for(db: Session, connection: Connection) -> ChatThread:
    existing = db.execute(
        select(ChatThread).where(ChatThread.connection_id == connection.id)
    ).scalar_one_or_none()
    if existing:
        return existing
    a = db.get(User, connection.requester_id)
    b = db.get(User, connection.receiver_id)
    title = f"{a.name if a else 'A'} · {b.name if b else 'B'}"
    thread = ChatThread(connection_id=connection.id, title=title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    db.add_all(
        [
            ChatThreadParticipant(thread_id=thread.id, user_id=connection.requester_id),
            ChatThreadParticipant(thread_id=thread.id, user_id=connection.receiver_id),
        ]
    )
    db.commit()
    # icebreaker
    text = _icebreaker(db, connection)
    m = Message(thread_id=thread.id, sender_id=None, body=text, kind="icebreaker")
    db.add(m)
    db.commit()
    return thread


def _icebreaker(db: Session, connection: Connection) -> str:
    a_ids = {
        i.id
        for i, in db.execute(
            select(Interest).join(UserInterest, UserInterest.interest_id == Interest.id).where(
                UserInterest.user_id == connection.requester_id
            )
        ).all()
    }
    b_ids = {
        i.id
        for i, in db.execute(
            select(Interest).join(UserInterest, UserInterest.interest_id == Interest.id).where(
                UserInterest.user_id == connection.receiver_id
            )
        ).all()
    }
    shared = list(a_ids & b_ids)
    labels: list[str] = []
    if shared:
        rows = db.execute(select(Interest.label).where(Interest.id.in_(shared[:3]))).scalars().all()
        labels = list(rows)
    provider = get_provider()
    prompt = (
        "Write a 1-sentence friendly icebreaker between two hackathon attendees who both care about: "
        + ", ".join(labels or ["AI"])
        + ". Keep it under 20 words."
    )
    try:
        return provider.generate_short_text(prompt, max_words=25)
    except Exception:
        return "Hey, great to connect — what brought you here today?"


def list_threads_for_user(db: Session, user_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(ChatThread)
        .join(ChatThreadParticipant, ChatThreadParticipant.thread_id == ChatThread.id)
        .where(ChatThreadParticipant.user_id == user_id)
        .order_by(ChatThread.id.desc())
    )
    threads = list(db.execute(stmt).scalars().unique().all())
    result: list[dict[str, Any]] = []
    for t in threads:
        pids = db.execute(
            select(ChatThreadParticipant.user_id).where(ChatThreadParticipant.thread_id == t.id)
        ).scalars().all()
        result.append(
            {
                "id": t.id,
                "connection_id": t.connection_id,
                "event_id": t.event_id,
                "title": t.title,
                "created_at": t.created_at,
                "participant_ids": list(pids),
            }
        )
    return result


def user_thread_ids(db: Session, user_id: int) -> list[int]:
    return list(
        db.execute(
            select(ChatThreadParticipant.thread_id).where(ChatThreadParticipant.user_id == user_id)
        ).scalars().all()
    )


def is_participant(db: Session, thread_id: int, user_id: int) -> bool:
    row = db.execute(
        select(ChatThreadParticipant.id).where(
            ChatThreadParticipant.thread_id == thread_id,
            ChatThreadParticipant.user_id == user_id,
        )
    ).scalar_one_or_none()
    return row is not None


def list_messages(db: Session, thread_id: int) -> list[Message]:
    return list(
        db.execute(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.id.asc())
        ).scalars().all()
    )


def post_message(
    db: Session,
    thread_id: int,
    sender_id: int,
    body: str | None,
    kind: str = "text",
    payload: dict | None = None,
) -> Message:
    if kind not in VALID_MESSAGE_KINDS:
        raise ValueError(f"invalid kind: {kind}")
    m = Message(
        thread_id=thread_id,
        sender_id=sender_id,
        body=body,
        kind=kind,
        payload=json.dumps(payload) if payload is not None else None,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def attend_together_invite(db: Session, thread_id: int, sender_id: int, event_id: int) -> Message:
    ev = db.get(Event, event_id)
    if not ev:
        raise ValueError("event not found")
    body = f"Want to attend '{ev.title}' together?"
    return post_message(
        db,
        thread_id,
        sender_id,
        body,
        kind="attend_together_invite",
        payload={"event_id": event_id, "event_title": ev.title},
    )


def attend_together_accept(db: Session, thread_id: int, accepter_id: int, invite_message_id: int) -> Message:
    inv = db.get(Message, invite_message_id)
    if not inv or inv.thread_id != thread_id or inv.kind != "attend_together_invite":
        raise ValueError("invite not found")
    payload = json.loads(inv.payload) if inv.payload else {}
    event_id = int(payload.get("event_id"))
    # RSVP both participants
    pids = db.execute(
        select(ChatThreadParticipant.user_id).where(ChatThreadParticipant.thread_id == thread_id)
    ).scalars().all()
    for uid in pids:
        exists = db.execute(
            select(EventInteraction.id).where(
                EventInteraction.user_id == uid,
                EventInteraction.event_id == event_id,
                EventInteraction.type == "rsvp",
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(EventInteraction(user_id=uid, event_id=event_id, type="rsvp"))
    db.commit()
    return post_message(
        db,
        thread_id,
        accepter_id,
        f"Confirmed! Both attending event #{event_id}.",
        kind="attend_together_accepted",
        payload={"event_id": event_id, "confirmed_by": accepter_id},
    )


def message_to_dict(m: Message) -> dict[str, Any]:
    payload = None
    if m.payload:
        try:
            payload = json.loads(m.payload)
        except Exception:
            payload = None
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "sender_id": m.sender_id,
        "body": m.body,
        "kind": m.kind,
        "payload": payload,
        "created_at": m.created_at,
    }
