from __future__ import annotations

import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.blob import blob_store
from app.models.networking import Connection
from app.models.reel import Reel, ReelInteraction

VALID_INTERACTION_TYPES = {"view", "like", "share", "save", "skip", "complete_watch"}


def create_reel(
    db: Session,
    user_id: int,
    filename: str,
    content: bytes,
    event_id: int | None = None,
    speaker_id: int | None = None,
    caption: str | None = None,
) -> Reel:
    suffix = Path(filename).suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".webm", ".mkv", ".m4v"}:
        suffix = ".mp4"
    key = f"reels/raw_{uuid.uuid4().hex}{suffix}"
    blob_store.save_bytes(content, key)
    reel = Reel(
        user_id=user_id,
        event_id=event_id,
        speaker_id=speaker_id,
        caption=caption,
        storage_key=key,
        status="processing",
    )
    db.add(reel)
    db.commit()
    db.refresh(reel)
    return reel


def get_reel(db: Session, reel_id: int) -> Reel | None:
    return db.get(Reel, reel_id)


def delete_own_reel(db: Session, user_id: int, reel_id: int) -> bool:
    r = db.get(Reel, reel_id)
    if not r or r.user_id != user_id:
        return False
    _delete(db, r)
    return True


def admin_delete_reel(db: Session, reel_id: int) -> bool:
    r = db.get(Reel, reel_id)
    if not r:
        return False
    _delete(db, r)
    return True


def _delete(db: Session, r: Reel) -> None:
    for key in (r.storage_key, r.thumbnail_key):
        if key:
            blob_store.delete(key)
    db.delete(r)
    db.commit()


def record_interaction(db: Session, user_id: int, reel_id: int, type_: str, watch_ms: int | None) -> ReelInteraction:
    if type_ not in VALID_INTERACTION_TYPES:
        raise ValueError(f"invalid type: {type_}")
    row = ReelInteraction(user_id=user_id, reel_id=reel_id, type=type_, watch_ms=watch_ms)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_feed(
    db: Session, user_id: int, cursor: int | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    stmt = select(Reel).where(Reel.status == "ready").order_by(Reel.created_at.desc(), Reel.id.desc())
    if cursor:
        stmt = stmt.where(Reel.id < cursor)
    reels = list(db.execute(stmt.limit(limit * 3)).scalars().all())

    like_counts = dict(
        db.execute(
            select(ReelInteraction.reel_id, func.count(ReelInteraction.id))
            .where(ReelInteraction.type == "like")
            .group_by(ReelInteraction.reel_id)
        ).all()
    )
    connected = _connected_user_ids(db, user_id)
    now = datetime.utcnow()

    # try personalized cosine boost from vec_user_profile/vec_event when available
    user_cos: dict[int, float] = {}
    try:
        from sqlalchemy import text as sql_text

        rows = db.execute(
            sql_text(
                "SELECT r.id, 1 - vec_distance_cosine(vp.embedding, ve.embedding) "
                "FROM reel r "
                "JOIN vec_event ve ON ve.event_id = r.event_id "
                "JOIN vec_user_profile vp ON vp.user_id = :uid "
                "WHERE r.event_id IS NOT NULL"
            ),
            {"uid": user_id},
        ).all()
        for rid, sim in rows:
            user_cos[int(rid)] = float(sim or 0.0)
    except Exception:
        user_cos = {}

    ranked: list[tuple[float, Reel]] = []
    for r in reels:
        age_h = max(0.0, (now - (r.created_at or now)).total_seconds() / 3600.0)
        recency = math.exp(-age_h / 24.0)
        likes = float(like_counts.get(r.id, 0))
        live_boost = 0.2 if r.event_id else 0.0
        connection_boost = 0.4 if r.user_id in connected else 0.0
        cosine = user_cos.get(r.id, 0.0) * 0.6
        score = recency + math.log1p(likes) * 0.3 + live_boost + connection_boost + cosine
        ranked.append((score, r))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [{"reel": r, "score": s, "likes": int(like_counts.get(r.id, 0))} for s, r in ranked[:limit]]


def _connected_user_ids(db: Session, user_id: int) -> set[int]:
    stmt = select(Connection).where(
        ((Connection.requester_id == user_id) | (Connection.receiver_id == user_id))
        & (Connection.status == "accepted")
    )
    ids: set[int] = set()
    for c in db.execute(stmt).scalars().all():
        ids.add(c.receiver_id if c.requester_id == user_id else c.requester_id)
    return ids


def refresh_signed_urls(reel: Reel) -> Reel:
    if reel.storage_key:
        reel.video_url = blob_store.signed_url(reel.storage_key)
    if reel.thumbnail_key:
        reel.thumbnail_url = blob_store.signed_url(reel.thumbnail_key)
    return reel
