from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.db import SessionLocal
from app.infra.ws_manager import manager
from app.models.chat import Message
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.networking import Connection
from app.models.notification import Notification
from app.models.reel import ReelInteraction
from app.models.user import User

logger = logging.getLogger(__name__)

PULSE_CHANNEL = "admin:pulse"


def aggregate(db: Session) -> dict:
    now = datetime.utcnow()
    today = now - timedelta(hours=24)
    likes_today = db.execute(
        select(func.count(EventInteraction.id)).where(
            EventInteraction.type == "like", EventInteraction.created_at >= today
        )
    ).scalar() or 0
    reel_likes_today = db.execute(
        select(func.count(ReelInteraction.id)).where(
            ReelInteraction.type == "like", ReelInteraction.created_at >= today
        )
    ).scalar() or 0
    total_users = db.execute(select(func.count(User.id))).scalar() or 0
    total_connections = db.execute(
        select(func.count(Connection.id)).where(Connection.status == "accepted")
    ).scalar() or 0
    active_threads = db.execute(
        select(func.count(func.distinct(Message.thread_id))).where(Message.created_at >= today)
    ).scalar() or 0
    trending_rows = db.execute(
        select(EventInteraction.event_id, func.count(EventInteraction.id).label("c"))
        .where(EventInteraction.created_at >= today)
        .group_by(EventInteraction.event_id)
        .order_by(func.count(EventInteraction.id).desc())
        .limit(5)
    ).all()
    trending: list[dict] = []
    for eid, c in trending_rows:
        ev = db.get(Event, eid)
        if ev:
            trending.append({"event_id": ev.id, "title": ev.title, "interactions": int(c)})
    avg = 0.0
    total_events = db.execute(select(func.count(Event.id))).scalar() or 0
    if total_events:
        total_iact = db.execute(select(func.count(EventInteraction.id))).scalar() or 0
        avg = round(total_iact / total_events, 2)
    return {
        "generated_at": now.isoformat(),
        "likes_today": int(likes_today),
        "reel_likes_today": int(reel_likes_today),
        "total_users": int(total_users),
        "total_accepted_connections": int(total_connections),
        "active_dm_threads_last_24h": int(active_threads),
        "trending_events": trending,
        "avg_interactions_per_event": avg,
    }


async def broadcast_pulse() -> None:
    db = SessionLocal()
    try:
        payload = aggregate(db)
    finally:
        db.close()
    await manager.broadcast_channel(PULSE_CHANNEL, {"channel": "pulse", "data": payload})


def wrapped(db: Session, user_id: int) -> dict:
    now = datetime.utcnow()
    sessions_attended = db.execute(
        select(func.count(EventInteraction.id)).where(
            EventInteraction.user_id == user_id, EventInteraction.type == "mark_attended"
        )
    ).scalar() or 0
    connections_made = db.execute(
        select(func.count(Connection.id)).where(
            ((Connection.requester_id == user_id) | (Connection.receiver_id == user_id))
            & (Connection.status == "accepted")
        )
    ).scalar() or 0
    from app.models.reel import Reel

    reels_posted = db.execute(select(func.count(Reel.id)).where(Reel.user_id == user_id)).scalar() or 0
    total_watch_ms = db.execute(
        select(func.coalesce(func.sum(ReelInteraction.watch_ms), 0)).where(ReelInteraction.user_id == user_id)
    ).scalar() or 0
    unique_rooms = db.execute(
        select(func.count(func.distinct(Event.room)))
        .join(EventInteraction, EventInteraction.event_id == Event.id)
        .where(EventInteraction.user_id == user_id, Event.room.isnot(None))
    ).scalar() or 0
    # favorite speaker: most interacted through event_interaction
    fav_speaker = None
    try:
        row = db.execute(
            select(func.count().label("c"), Event.id)
            .join(EventInteraction, EventInteraction.event_id == Event.id)
            .where(EventInteraction.user_id == user_id)
            .group_by(Event.id)
            .order_by(func.count().desc())
            .limit(1)
        ).first()
        if row:
            _, top_event_id = row
            from app.domain.event_service import event_speakers

            speakers = event_speakers(db, int(top_event_id))
            if speakers:
                fav_speaker = speakers[0].name
    except Exception:
        pass

    # top_topics: infer from liked events' interests
    from app.models.event import EventInterest
    from app.models.interest import Interest

    top_topics = [
        label
        for label, _ in db.execute(
            select(Interest.label, func.count(EventInterest.id))
            .join(EventInterest, EventInterest.interest_id == Interest.id)
            .join(EventInteraction, EventInteraction.event_id == EventInterest.event_id)
            .where(EventInteraction.user_id == user_id, EventInteraction.type.in_(["like", "save", "rsvp"]))
            .group_by(Interest.label)
            .order_by(func.count(EventInterest.id).desc())
            .limit(3)
        ).all()
    ]
    notifications_received = db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == user_id)
    ).scalar() or 0

    return {
        "generated_at": now.isoformat(),
        "sessions_attended": int(sessions_attended),
        "connections_made": int(connections_made),
        "reels_posted": int(reels_posted),
        "total_watch_ms": int(total_watch_ms),
        "unique_rooms_visited": int(unique_rooms),
        "favorite_speaker": fav_speaker,
        "top_topics": top_topics,
        "notifications_received": int(notifications_received),
    }
