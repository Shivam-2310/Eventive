from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import notification_service
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.mission import Mission, UserMissionProgress
from app.models.networking import Connection
from app.models.reel import ReelInteraction
from app.schemas.mission import MissionCreate


def create_mission(db: Session, payload: MissionCreate) -> Mission:
    m = Mission(
        title=payload.title,
        description=payload.description,
        rule=json.dumps(payload.rule),
        points=payload.points,
        badge_icon_url=payload.badge_icon_url,
        active=payload.active,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def list_missions(db: Session, active_only: bool = True) -> list[Mission]:
    stmt = select(Mission).order_by(Mission.id)
    if active_only:
        stmt = stmt.where(Mission.active.is_(True))
    return list(db.execute(stmt).scalars().all())


def mission_to_dict(m: Mission) -> dict[str, Any]:
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "rule": json.loads(m.rule) if m.rule else {},
        "points": m.points,
        "badge_icon_url": m.badge_icon_url,
        "active": m.active,
        "created_at": m.created_at,
    }


def _get_progress(db: Session, user_id: int, mission_id: int) -> UserMissionProgress:
    row = db.execute(
        select(UserMissionProgress).where(
            UserMissionProgress.user_id == user_id, UserMissionProgress.mission_id == mission_id
        )
    ).scalar_one_or_none()
    if row:
        return row
    row = UserMissionProgress(user_id=user_id, mission_id=mission_id, progress=json.dumps({"count": 0}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def recompute(db: Session, user_id: int) -> list[UserMissionProgress]:
    updated: list[UserMissionProgress] = []
    missions = list_missions(db)
    for m in missions:
        rule = json.loads(m.rule) if m.rule else {}
        rtype = rule.get("type")
        target = int(rule.get("count", 1))
        current = 0
        if rtype == "attend_track":
            track = rule.get("track")
            current = db.execute(
                select(EventInteraction).join(Event, Event.id == EventInteraction.event_id).where(
                    EventInteraction.user_id == user_id,
                    EventInteraction.type == "mark_attended",
                    Event.track == track if track else True,
                )
            ).scalars().all().__len__()
        elif rtype == "like_reels":
            current = db.execute(
                select(ReelInteraction).where(
                    ReelInteraction.user_id == user_id, ReelInteraction.type == "like"
                )
            ).scalars().all().__len__()
        elif rtype == "make_connections":
            current = db.execute(
                select(Connection).where(
                    ((Connection.requester_id == user_id) | (Connection.receiver_id == user_id))
                    & (Connection.status == "accepted")
                )
            ).scalars().all().__len__()
        elif rtype == "like_events":
            current = db.execute(
                select(EventInteraction).where(
                    EventInteraction.user_id == user_id, EventInteraction.type == "like"
                )
            ).scalars().all().__len__()

        prog = _get_progress(db, user_id, m.id)
        prog.progress = json.dumps({"count": current, "target": target})
        was_complete = prog.completed_at is not None
        if current >= target and not was_complete:
            prog.completed_at = datetime.utcnow()
            prog.points_awarded = m.points
            db.commit()
            notification_service.push(
                db,
                user_id,
                type_="mission_completed",
                title=f"Mission complete: {m.title}",
                body=f"You earned {m.points} points.",
                deep_link=f"/missions/{m.id}",
            )
        else:
            db.commit()
        updated.append(prog)
    return updated


def list_user_progress(db: Session, user_id: int) -> list[tuple[Mission, UserMissionProgress]]:
    rows = db.execute(
        select(Mission, UserMissionProgress)
        .outerjoin(
            UserMissionProgress,
            (UserMissionProgress.mission_id == Mission.id) & (UserMissionProgress.user_id == user_id),
        )
        .where(Mission.active.is_(True))
        .order_by(Mission.id)
    ).all()
    return [(m, p) for m, p in rows]
