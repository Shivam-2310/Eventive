"""Event service unit tests: CRUD, filters, discover, reactions, interactions."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.domain import event_service, user_service
from app.models.event import Event
from app.models.interaction import EventCardReaction, EventInteraction
from app.schemas.event import (
    EventCreate,
    EventInterestAssign,
    EventReaction,
    EventUpdate,
    SpeakerCreate,
    SpeakerUpdate,
)
from app.schemas.user import UserCreate


def _mk_event(db, title: str = "Sample", track: str | None = "AI", days_ahead: int = 1) -> Event:  # noqa: ANN001
    start = datetime.utcnow() + timedelta(days=days_ahead)
    ev = event_service.create_event(
        db,
        EventCreate(
            external_id=f"ext-{title}",
            title=title,
            track=track,
            start_time=start,
            end_time=start + timedelta(hours=1),
            location="Hall",
            room="R1",
            capacity=100,
            status="scheduled",
        ),
    )
    return ev


def test_create_and_get_event(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    ev = _mk_event(db_session, title="Keynote")
    fetched = event_service.get_event(db_session, ev.id)
    assert fetched is not None and fetched.title == "Keynote"


def test_upsert_by_external_id_created_then_updated(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    payload = {"external_id": "up-1", "title": "v1", "track": "AI", "status": "scheduled"}
    ev1, created1 = event_service.upsert_event_by_external_id(db_session, payload)
    assert created1 is True
    payload["title"] = "v2"
    ev2, created2 = event_service.upsert_event_by_external_id(db_session, payload)
    assert created2 is False
    assert ev1.id == ev2.id
    assert ev2.title == "v2"


def test_update_event_returns_none_when_missing(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    assert event_service.update_event(db_session, 99_999, EventUpdate(title="x")) is None


def test_delete_event(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    ev = _mk_event(db_session, title="ToDelete")
    assert event_service.delete_event(db_session, ev.id) is True
    assert event_service.get_event(db_session, ev.id) is None
    assert event_service.delete_event(db_session, ev.id) is False


def test_list_events_filters(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    ev_ai = _mk_event(db_session, title="AI Talk", track="AI")
    _mk_event(db_session, title="Web Talk", track="Web")
    ai_only = event_service.list_events(db_session, track="AI")
    assert all(e.track == "AI" for e in ai_only)
    assert ev_ai.id in [e.id for e in ai_only]
    scheduled = event_service.list_events(db_session, status="scheduled")
    assert all(e.status == "scheduled" for e in scheduled)


def test_list_events_by_day_window(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    today = _mk_event(db_session, title="Today", days_ahead=0)
    _mk_event(db_session, title="Tomorrow", days_ahead=2)
    same_day = event_service.list_events(db_session, day=datetime.utcnow().date())
    ids = [e.id for e in same_day]
    assert today.id in ids


def test_assign_speaker_creates_and_updates_role(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    ev = _mk_event(db_session, title="With Speaker")
    speaker = event_service.create_speaker(db_session, SpeakerCreate(name="Sp"))
    row = event_service.assign_speaker(db_session, ev.id, speaker.id, "keynote")
    assert row.role == "keynote"
    # Re-assign with new role: idempotent (same row updated).
    row2 = event_service.assign_speaker(db_session, ev.id, speaker.id, "panelist")
    assert row2.id == row.id
    assert row2.role == "panelist"


def test_assign_interests_replaces_existing(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    ev = _mk_event(db_session, title="For Interests")
    from app.models.interest import Interest

    ids = db_session.execute(select(Interest.id).limit(3)).scalars().all()
    added = event_service.assign_interests(db_session, ev.id, EventInterestAssign(interest_ids=list(ids)))
    assert added == 3
    added2 = event_service.assign_interests(db_session, ev.id, EventInterestAssign(interest_ids=list(ids[:1])))
    assert added2 == 1
    assert len(event_service.event_interests(db_session, ev.id)) == 1


def test_hydrate_event_populates_speakers_and_interests(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    hydrated = event_service.hydrate_event(db_session, ev)
    assert hydrated["id"] == ev.id
    assert isinstance(hydrated["speakers"], list)
    assert isinstance(hydrated["interests"], list)


# --- Discover cards --------------------------------------------------------


def test_discover_returns_cards_with_all_prompts(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="disc@eventive.dev", name="Disc"))
    cards, next_cursor = event_service.discover_cards(db_session, user.id, cursor=None, limit=3)
    assert cards, "expected at least one card"
    prompt_types = {p.prompt_type for p in cards[0].prompts}
    assert {"cover", "topic", "when_where", "vibe", "who_is_going"}.issubset(prompt_types)


def test_discover_pagination_cursor(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="pag@eventive.dev", name="Pag"))
    first, cur = event_service.discover_cards(db_session, user.id, cursor=None, limit=2)
    if cur:
        second, _ = event_service.discover_cards(db_session, user.id, cursor=cur, limit=2)
        first_ids = {c.event.id for c in first}
        second_ids = {c.event.id for c in second}
        assert first_ids.isdisjoint(second_ids)


# --- Reactions + interactions ---------------------------------------------


def test_react_upsert_stays_one_row(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="react@eventive.dev", name="React"))
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()

    r1 = event_service.react_to_prompt(
        db_session, user.id, ev.id, EventReaction(prompt_type="topic", reaction="like")
    )
    r2 = event_service.react_to_prompt(
        db_session, user.id, ev.id, EventReaction(prompt_type="topic", reaction="like")
    )
    assert r1.id == r2.id
    count = db_session.execute(
        select(func.count(EventCardReaction.id))
        .where(EventCardReaction.user_id == user.id, EventCardReaction.event_id == ev.id)
    ).scalar()
    assert count == 1


def test_react_invalid_prompt_type_raises(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="bad@eventive.dev", name="Bad"))
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    with pytest.raises(ValueError):
        event_service.react_to_prompt(
            db_session, user.id, ev.id, EventReaction(prompt_type="not-a-slot", reaction="like")
        )


def test_record_interaction_valid_types(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="int@eventive.dev", name="Int"))
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    row = event_service.record_interaction(db_session, user.id, ev.id, "like")
    assert row.type == "like"
    saved = db_session.execute(
        select(EventInteraction).where(EventInteraction.id == row.id)
    ).scalar_one()
    assert saved.event_id == ev.id


def test_record_interaction_invalid_type_raises(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="badint@eventive.dev", name="X"))
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    with pytest.raises(ValueError):
        event_service.record_interaction(db_session, user.id, ev.id, "hug")


# --- Speakers -------------------------------------------------------------


def test_speaker_crud(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    s = event_service.create_speaker(db_session, SpeakerCreate(name="Dr. Test", social_links={"tw": "x"}))
    assert s.id and s.name == "Dr. Test"

    updated = event_service.update_speaker(db_session, s.id, SpeakerUpdate(bio="new bio"))
    assert updated is not None and updated.bio == "new bio"

    assert event_service.get_speaker(db_session, s.id) is not None
    assert event_service.delete_speaker(db_session, s.id) is True
    assert event_service.get_speaker(db_session, s.id) is None


# --- Re-embed hooks --------------------------------------------------------


def test_assign_interests_reembeds_event(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """`assign_interests` must trigger `embed_event` so vec_event stays in sync.

    We embed the event with zero tags, snapshot its vec blob, then assign
    interests — the blob must change (stub embedder is deterministic).
    """
    from sqlalchemy import text as sql_text

    from app.models.interest import Interest
    from app.workers import embeddings as emb_worker

    ev = _mk_event(db_session, title="Reembed Test")
    emb_worker.embed_event(db_session, ev.id)  # baseline (no tags)
    blob1 = bytes(
        db_session.execute(
            sql_text("SELECT embedding FROM vec_event WHERE event_id = :k"), {"k": ev.id}
        ).scalar_one()
    )
    interest_ids = db_session.execute(select(Interest.id).limit(2)).scalars().all()
    event_service.assign_interests(
        db_session, ev.id, EventInterestAssign(interest_ids=list(interest_ids))
    )
    blob2 = bytes(
        db_session.execute(
            sql_text("SELECT embedding FROM vec_event WHERE event_id = :k"), {"k": ev.id}
        ).scalar_one()
    )
    assert blob1 != blob2, "vec_event did not refresh after assign_interests"


def test_assign_speaker_reembeds_event(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """`assign_speaker` must trigger `embed_event` — the embedded body already
    contains speaker bios so a new speaker must move the vector."""
    from sqlalchemy import text as sql_text

    from app.workers import embeddings as emb_worker

    ev = _mk_event(db_session, title="Speaker Reembed Test")
    emb_worker.embed_event(db_session, ev.id)  # baseline
    blob1 = bytes(
        db_session.execute(
            sql_text("SELECT embedding FROM vec_event WHERE event_id = :k"), {"k": ev.id}
        ).scalar_one()
    )
    speaker = event_service.create_speaker(
        db_session, SpeakerCreate(name="Unique Speaker Name", bio="A very unique bio")
    )
    event_service.assign_speaker(db_session, ev.id, speaker.id, "keynote")
    blob2 = bytes(
        db_session.execute(
            sql_text("SELECT embedding FROM vec_event WHERE event_id = :k"), {"k": ev.id}
        ).scalar_one()
    )
    assert blob1 != blob2, "vec_event did not refresh after assign_speaker"


def test_reembed_failure_does_not_break_writes(seeded: dict, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """A broken embedder must never fail the write path."""
    from app.workers import embeddings as emb_worker

    def _boom(*_a, **_kw):
        raise RuntimeError("embedder down")

    monkeypatch.setattr(emb_worker, "embed_event", _boom)

    ev = _mk_event(db_session, title="Broken Embedder Event")
    speaker = event_service.create_speaker(db_session, SpeakerCreate(name="Spk"))
    row = event_service.assign_speaker(db_session, ev.id, speaker.id, "panelist")
    assert row.id


# --- For You deck ----------------------------------------------------------


def test_for_you_cards_returns_full_prompt_structure(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """`for_you_cards` shares the same card layout as `discover_cards` so the
    frontend can render either surface with the same widget."""
    from app.domain import interest_service

    user = user_service.create_user(
        db_session,
        UserCreate(email="foryou@eventive.dev", name="ForYou", blurb="loves ai"),
    )
    interest_ids = [i.id for i in interest_service.list_interests(db_session)[:3]]
    interest_service.set_user_interests(db_session, user.id, interest_ids)

    cards = event_service.for_you_cards(db_session, user.id, limit=3)
    assert cards, "expected at least one interest-matched card"
    prompt_types = {p.prompt_type for p in cards[0].prompts}
    assert {"cover", "topic", "when_where", "vibe", "who_is_going"}.issubset(prompt_types)


def test_for_you_cards_empty_for_missing_user(db_session) -> None:  # noqa: ANN001
    """Missing user id → empty list, no exception."""
    from app.infra.db import ensure_schema

    ensure_schema()
    assert event_service.for_you_cards(db_session, 999_999, limit=5) == []
