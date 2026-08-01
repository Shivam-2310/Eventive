"""Pulse service: aggregate() shape + wrapped() for a demo user."""
from __future__ import annotations

from sqlalchemy import select

from app.domain import pulse_service
from app.models.user import User


def _get_user_by_name(db, name: str) -> User:  # noqa: ANN001
    return db.execute(select(User).where(User.name == name)).scalar_one()


def test_aggregate_returns_expected_keys(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    payload = pulse_service.aggregate(db_session)
    for key in (
        "generated_at",
        "likes_today",
        "reel_likes_today",
        "total_users",
        "total_accepted_connections",
        "active_dm_threads_last_24h",
        "trending_events",
        "avg_interactions_per_event",
    ):
        assert key in payload, f"missing pulse key: {key}"
    assert isinstance(payload["trending_events"], list)


def test_aggregate_counters_are_nonzero_after_seed(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    payload = pulse_service.aggregate(db_session)
    # seed pre-populates likes on 3 events per demo user, so likes_today > 0.
    assert payload["likes_today"] >= 1
    assert payload["total_users"] >= 4  # admin + 3 demo users


def test_wrapped_for_alice(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    alice = _get_user_by_name(db_session, "Alice")
    w = pulse_service.wrapped(db_session, alice.id)
    assert w["sessions_attended"] >= 1
    assert w["connections_made"] >= 1  # alice ↔ bob accepted
    assert isinstance(w["top_topics"], list)
    assert w["top_topics"], "top_topics should be non-empty for alice (interactions primed)"


def test_wrapped_missing_user_returns_zeros(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    w = pulse_service.wrapped(db_session, 999_999)
    assert w["sessions_attended"] == 0
    assert w["connections_made"] == 0
    assert w["top_topics"] == []


def test_wrapped_includes_notifications_count(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    alice = _get_user_by_name(db_session, "Alice")
    w = pulse_service.wrapped(db_session, alice.id)
    # seed pushes a welcome notification per demo user.
    assert w["notifications_received"] >= 1
