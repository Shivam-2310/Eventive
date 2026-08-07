"""APScheduler beat functions: call directly, mock the clock with monkeypatch.

The `beat_event_starting_soon` beat has three intentionally-different
behaviours we want to lock down here:

  * `rsvp` → fires TWO notifications per event (30-min heads-up + 10-min
    alarm). Hard commitment gets loud reminders.
  * `save` (without RSVP) → fires ONE notification, 10 min out, tagged
    `event_saved_reminder`. Soft intent gets a soft nudge.
  * `like` → fires NOTHING. It's an implicit taste signal from the swipe
    deck, not a user-managed shortlist.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain import user_service
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.networking import Match
from app.models.notification import Notification
from app.schemas.user import UserCreate


class _FrozenDateTime(datetime):
    """`datetime` shim whose `utcnow()` is monkey-patched to a fixed instant.

    Sub-classing lets any other `datetime.now()` etc. call work unchanged.
    """

    _now: datetime = datetime(2026, 7, 11, 9, 0, 0)

    @classmethod
    def utcnow(cls) -> datetime:  # type: ignore[override]
        return cls._now


@pytest.fixture(autouse=True)
def _clear_fired_dedupe() -> None:
    """`beats._fired` is a module-global set — reset per test."""
    from app.workers import beats

    beats._fired.clear()
    yield
    beats._fired.clear()


def _freeze(monkeypatch, now: datetime) -> None:
    from app.workers import beats

    _FrozenDateTime._now = now
    monkeypatch.setattr(beats, "datetime", _FrozenDateTime)


def _notifs_for(db_session, user_id: int, type_: str) -> list[Notification]:
    return list(
        db_session.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.type == type_
            )
        )
        .scalars()
        .all()
    )


# --- RSVP: firm reminders --------------------------------------------------


def test_rsvp_fires_10min_alarm(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Event 5 min out + RSVP → single 'Starting soon' push."""
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="rsvp10@eventive.dev", name="R"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Alarm", track="AI", status="scheduled", start_time=now + timedelta(minutes=5))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="rsvp"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    notifs = _notifs_for(db_session, user.id, "event_starting_soon")
    assert len(notifs) == 1
    assert "Starting soon" in notifs[0].title
    assert "Alarm" in notifs[0].title


def test_rsvp_fires_30min_headsup(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Event 20 min out + RSVP → 'Get ready' heads-up (only)."""
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="rsvp30@eventive.dev", name="R"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="HeadsUp", track="AI", status="scheduled", start_time=now + timedelta(minutes=20))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="rsvp"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    notifs = _notifs_for(db_session, user.id, "event_starting_soon")
    assert len(notifs) == 1
    assert "Get ready" in notifs[0].title
    assert "HeadsUp" in notifs[0].title


def test_rsvp_fires_both_pushes_across_windows(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """The two windows compose: first tick 20 min out → heads-up, later tick
    5 min out → alarm. Total for one event: two pushes.
    """
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="rsvpboth@eventive.dev", name="R"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Both", track="AI", status="scheduled", start_time=now + timedelta(minutes=20))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="rsvp"))
    db_session.commit()

    # Tick 1: 20 min before start → in heads-up window.
    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    # Tick 2: 15 min later, event is now 5 min out → in alarm window.
    _freeze(monkeypatch, now + timedelta(minutes=15))
    beats.beat_event_starting_soon()

    notifs = _notifs_for(db_session, user.id, "event_starting_soon")
    assert len(notifs) == 2
    titles = {n.title for n in notifs}
    assert any("Get ready" in t for t in titles), titles
    assert any("Starting soon" in t for t in titles), titles


# --- Save: soft nudge ------------------------------------------------------


def test_save_only_fires_soft_nudge_10min(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Save (without RSVP) → 'Still want to catch...?' 10-min reminder."""
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="save@eventive.dev", name="S"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Nudged", track="AI", status="scheduled", start_time=now + timedelta(minutes=5))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="save"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    # Firm alarm channel must be empty; soft-nudge channel gets exactly one.
    assert _notifs_for(db_session, user.id, "event_starting_soon") == []
    nudges = _notifs_for(db_session, user.id, "event_saved_reminder")
    assert len(nudges) == 1
    assert "Still want to catch" in nudges[0].title


def test_save_gets_no_30min_headsup(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Save-only users must not get the 30-min RSVP heads-up — only the
    10-min soft nudge is theirs.
    """
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="saveonly30@eventive.dev", name="S"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Faraway", track="AI", status="scheduled", start_time=now + timedelta(minutes=20))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="save"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    assert _notifs_for(db_session, user.id, "event_starting_soon") == []
    assert _notifs_for(db_session, user.id, "event_saved_reminder") == []


def test_rsvp_suppresses_save_nudge(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """A user who both saved AND RSVP'd gets the firm RSVP messaging, never
    the softer 'Still want to catch...?' nudge — the RSVP wins.
    """
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="both@eventive.dev", name="B"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Overlap", track="AI", status="scheduled", start_time=now + timedelta(minutes=5))
    db_session.add(ev)
    db_session.commit()
    db_session.add_all([
        EventInteraction(user_id=user.id, event_id=ev.id, type="save"),
        EventInteraction(user_id=user.id, event_id=ev.id, type="rsvp"),
    ])
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    # One firm push and zero soft nudges — the RSVP path takes precedence.
    assert len(_notifs_for(db_session, user.id, "event_starting_soon")) == 1
    assert _notifs_for(db_session, user.id, "event_saved_reminder") == []


# --- Like: implicit taste signal, no push ---------------------------------


def test_like_alone_fires_nothing(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Regression guard for the new intent: `like` is telemetry, not a
    reminder. A user who only liked an event must get zero pushes.
    """
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="like@eventive.dev", name="L"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Silent", track="AI", status="scheduled", start_time=now + timedelta(minutes=5))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="like"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    assert _notifs_for(db_session, user.id, "event_starting_soon") == []
    assert _notifs_for(db_session, user.id, "event_saved_reminder") == []


# --- Cross-cutting behaviour ----------------------------------------------


def test_event_starting_soon_dedupes_per_process(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Second call within the same window must not push a duplicate."""
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="dd@eventive.dev", name="B"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    ev = Event(title="Once", track="AI", status="scheduled", start_time=now + timedelta(minutes=3))
    db_session.add(ev)
    db_session.commit()
    db_session.add(EventInteraction(user_id=user.id, event_id=ev.id, type="rsvp"))
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()
    beats.beat_event_starting_soon()

    # Event is only in the 10-min alarm window (not the 30-min heads-up
    # window), so the total is exactly one push, not two.
    assert len(_notifs_for(db_session, user.id, "event_starting_soon")) == 1


def test_event_starting_soon_ignores_events_outside_window(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """Events > 30 min out or already in the past must not trigger anything."""
    from app.workers import beats

    user = user_service.create_user(db_session, UserCreate(email="w@eventive.dev", name="B"))
    now = datetime(2026, 7, 11, 9, 0, 0)
    later = Event(title="Later", track="AI", status="scheduled", start_time=now + timedelta(hours=2))
    past = Event(title="Past", track="AI", status="scheduled", start_time=now - timedelta(hours=2))
    db_session.add_all([later, past])
    db_session.commit()
    db_session.add_all([
        EventInteraction(user_id=user.id, event_id=later.id, type="rsvp"),
        EventInteraction(user_id=user.id, event_id=past.id, type="rsvp"),
    ])
    db_session.commit()

    _freeze(monkeypatch, now)
    beats.beat_event_starting_soon()

    assert _notifs_for(db_session, user.id, "event_starting_soon") == []
    assert _notifs_for(db_session, user.id, "event_saved_reminder") == []


# --- Unrelated beats ------------------------------------------------------


def test_beat_nightly_matches_repopulates_matches(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """Nightly beat: call directly and expect the `match` table to be repopulated."""
    from app.workers import beats

    db_session.query(Match).delete()
    db_session.commit()

    beats.beat_nightly_matches()
    remaining = db_session.execute(select(Match)).scalars().all()
    assert remaining, "nightly beat should have produced at least one match row"


def test_beat_pulse_snapshot_broadcasts(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """`beat_pulse_snapshot` is an async wrapper — verify it invokes `broadcast_pulse`."""
    from app.domain import pulse_service
    from app.workers import beats

    called: list[bool] = []

    async def _fake_broadcast() -> None:
        called.append(True)

    monkeypatch.setattr(pulse_service, "broadcast_pulse", _fake_broadcast)

    import asyncio

    asyncio.run(beats.beat_pulse_snapshot())
    assert called == [True]


def test_beat_pulse_snapshot_swallows_errors(monkeypatch) -> None:  # noqa: ANN001
    """Broadcast failures must not propagate out of the beat."""
    from app.domain import pulse_service
    from app.workers import beats

    async def _boom() -> None:
        raise RuntimeError("nope")

    monkeypatch.setattr(pulse_service, "broadcast_pulse", _boom)

    import asyncio

    asyncio.run(beats.beat_pulse_snapshot())
