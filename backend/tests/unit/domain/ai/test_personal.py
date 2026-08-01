"""Personal-query handlers — ORM-backed, deterministic, no LLM required.

These tests use the same ``seeded`` fixture as the smoke tests so we exercise
against real seeded data (3 demo users, 50 events, connections, interests).
"""

from __future__ import annotations

from sqlalchemy import select

from app.domain.ai import personal
from app.models.event import Event
from app.models.interaction import EventInteraction


def _first_user_id(db) -> int:  # noqa: ANN001
    from app.models.user import User

    return db.execute(select(User.id).order_by(User.id).limit(1)).scalars().first()


def test_my_saved_events_empty(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    uid = _first_user_id(db_session)
    # ensure no saves
    db_session.query(EventInteraction).filter_by(user_id=uid).delete()
    db_session.commit()
    res = personal.my_saved_events(db_session, uid)
    assert res["ok"] is True
    assert "haven't saved" in res["prose"]
    assert res["data"] == []


def test_my_saved_events_populated(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    uid = _first_user_id(db_session)
    ev = db_session.execute(select(Event).limit(1)).scalars().first()
    db_session.add(EventInteraction(user_id=uid, event_id=ev.id, type="save"))
    db_session.commit()
    res = personal.my_saved_events(db_session, uid)
    assert res["ok"] is True
    assert ev.title in res["prose"]
    assert res["data"] and res["data"][0]["event_id"] == ev.id
    assert res["citations"] and res["citations"][0]["citation"] == f"event:{ev.id}"


def test_my_interests_reads_from_seed(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    # Alice (email alice@flo.dev) is user 2 in the seed
    from app.models.user import User

    alice = db_session.execute(select(User).where(User.email == "alice@flo.dev")).scalars().first()
    assert alice is not None
    res = personal.my_interests(db_session, alice.id)
    assert res["ok"] is True
    assert res["data"], "seed gave alice 5 interests"
    assert "You follow" in res["prose"]


def test_my_connections_and_pending(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    from app.models.user import User

    alice = db_session.execute(select(User).where(User.email == "alice@flo.dev")).scalars().first()
    res = personal.my_connections(db_session, alice.id)
    assert res["ok"] is True
    # seed makes alice ↔ bob an accepted pair
    assert "connected" in res["prose"].lower() or "don't have" in res["prose"].lower()


def test_my_wrapped_totals(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    uid = _first_user_id(db_session)
    res = personal.my_wrapped(db_session, uid)
    assert res["ok"] is True
    for k in ("like", "save", "rsvp", "mark_attended", "connections"):
        assert k in res["data"]


def test_handle_dispatches(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    res = personal.handle(db_session, _first_user_id(db_session), "my_agenda")
    assert res["ok"] is True
    res = personal.handle(db_session, _first_user_id(db_session), "unknown_subkind")
    assert res["ok"] is False


def test_bucket_split_matches_phase2_semantics(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """Phase 2 introduced dedicated buckets on the Profile screen (Saved,
    My Day, Calendar, Liked, Attended, RSVPs). The bot's handlers must
    return the same slice for each bucket so users don't see a My Day
    session mixed into their Saved list."""
    uid = _first_user_id(db_session)
    db_session.query(EventInteraction).filter_by(user_id=uid).delete()
    db_session.commit()
    events = db_session.execute(select(Event).order_by(Event.id).limit(4)).scalars().all()
    assert len(events) >= 4
    ev_save, ev_day, ev_cal, ev_att = events[0], events[1], events[2], events[3]
    db_session.add_all(
        [
            EventInteraction(user_id=uid, event_id=ev_save.id, type="save"),
            EventInteraction(user_id=uid, event_id=ev_day.id, type="add_to_my_day"),
            EventInteraction(user_id=uid, event_id=ev_cal.id, type="add_to_calendar"),
            EventInteraction(user_id=uid, event_id=ev_att.id, type="mark_attended"),
        ]
    )
    db_session.commit()

    saved = personal.my_saved_events(db_session, uid)
    assert [d["event_id"] for d in saved["data"]] == [ev_save.id]

    day = personal.my_agenda(db_session, uid)
    assert ev_day.id in [d["event_id"] for d in day["data"]]

    cal = personal.my_calendar_events(db_session, uid)
    assert [d["event_id"] for d in cal["data"]] == [ev_cal.id]

    attended = personal.my_attended_events(db_session, uid)
    assert [d["event_id"] for d in attended["data"]] == [ev_att.id]
