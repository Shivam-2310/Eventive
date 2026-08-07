"""Mission service: rule engine + progress + completion notification."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.domain import mission_service, user_service
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.mission import UserMissionProgress
from app.models.networking import Connection
from app.models.notification import Notification
from app.schemas.mission import MissionCreate
from app.schemas.user import UserCreate


def _mk_user(db, email: str) -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name="U"))


def test_create_mission_persists_and_lists(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    m = mission_service.create_mission(
        db_session,
        MissionCreate(
            title="Test", description="d", rule={"type": "like_events", "count": 2}, points=10
        ),
    )
    assert m.id
    all_missions = mission_service.list_missions(db_session)
    assert any(x.id == m.id for x in all_missions)


def test_like_events_rule_increments(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Under seed the 'like_events' mission target is 5; simulating 5 likes completes it."""
    user = _mk_user(db_session, "like@eventive.dev")
    events = db_session.execute(select(Event).order_by(Event.id).limit(5)).scalars().all()
    for ev in events:
        db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="like"))
    db_session.commit()

    progress = mission_service.recompute(db_session, user.id)
    assert progress
    completed = [
        p for p in progress
        if p.completed_at is not None
    ]
    assert completed, "at least one mission should be marked complete"


def test_mission_completed_pushes_notification(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _mk_user(db_session, "mn@eventive.dev")
    events = db_session.execute(select(Event).order_by(Event.id).limit(5)).scalars().all()
    for ev in events:
        db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="like"))
    db_session.commit()

    mission_service.recompute(db_session, user.id)
    notifs = db_session.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.type == "mission_completed")
    ).scalars().all()
    assert notifs, "expected at least one 'mission_completed' notification"


def test_progress_stored_as_json_string(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _mk_user(db_session, "prog@eventive.dev")
    db_session.add(EventInteraction(user_id=user.id, event_id=1, type="like"))
    db_session.commit()

    mission_service.recompute(db_session, user.id)
    rows = db_session.execute(
        select(UserMissionProgress).where(UserMissionProgress.user_id == user.id)
    ).scalars().all()
    assert rows
    for r in rows:
        parsed = json.loads(r.progress) if r.progress else {}
        assert "count" in parsed and "target" in parsed


def test_make_connections_rule_uses_accepted_only(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _mk_user(db_session, "conn@eventive.dev")
    for i in range(3):
        other = _mk_user(db_session, f"other-{i}@eventive.dev")
        db_session.add(
            Connection(requester_id=user.id, receiver_id=other.id, status="accepted")
        )
    # one pending doesn't count
    other = _mk_user(db_session, "pending@eventive.dev")
    db_session.add(Connection(requester_id=user.id, receiver_id=other.id, status="pending"))
    db_session.commit()

    mission_service.recompute(db_session, user.id)
    # Find the 'make_connections' mission — target is 3 in seed.
    from app.models.mission import Mission

    m = db_session.execute(select(Mission).where(Mission.title == "Connector")).scalar_one()
    p = db_session.execute(
        select(UserMissionProgress).where(
            UserMissionProgress.user_id == user.id, UserMissionProgress.mission_id == m.id
        )
    ).scalar_one()
    assert p.completed_at is not None


def test_list_user_progress_shape(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _mk_user(db_session, "lu@eventive.dev")
    rows = mission_service.list_user_progress(db_session, user.id)
    assert rows
    # Each row is (Mission, UserMissionProgress|None).
    for m, _ in rows:
        assert m.active is True


def test_mission_to_dict_shape() -> None:
    """Direct dict-shape guard: rule is decoded, ints preserved."""
    from app.infra.db import SessionLocal, ensure_schema

    ensure_schema()
    db = SessionLocal()
    try:
        m = mission_service.create_mission(
            db,
            MissionCreate(title="D", description="dd", rule={"type": "like_events", "count": 1}, points=7),
        )
        d = mission_service.mission_to_dict(m)
        assert d["id"] == m.id
        assert d["rule"] == {"type": "like_events", "count": 1}
        assert d["points"] == 7
    finally:
        db.close()
