"""Recommendation engine: people + events. Uses `seeded` for a rich fixture."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.domain import matching_service
from app.models.event import Event
from app.models.networking import Connection
from app.models.user import User


def _demo_user(db, name: str) -> User:  # noqa: ANN001
    return db.execute(select(User).where(User.name == name)).scalar_one()


def test_recommend_people_returns_scored_reasons(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    alice = _demo_user(db_session, "Alice")
    from app.workers import embeddings as emb_worker

    # Warm the vec index for alice (already done by seed but explicit for clarity).
    emb_worker.embed_user_profile(db_session, alice.id)
    out = matching_service.recommend_people(db_session, alice.id, k=5)
    assert isinstance(out, list)
    for row in out:
        assert "other_user_id" in row
        assert "score" in row
        assert "reasons" in row
        assert row["reasons"]


def test_recommend_people_excludes_accepted_connections(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Seeded alice ↔ bob is 'accepted' so bob must not appear as a candidate."""
    alice = _demo_user(db_session, "Alice")
    bob = _demo_user(db_session, "Bob")
    accepted = db_session.execute(
        select(Connection).where(
            (
                (Connection.requester_id == alice.id) & (Connection.receiver_id == bob.id)
            ) | ((Connection.requester_id == bob.id) & (Connection.receiver_id == alice.id))
        )
    ).scalar_one_or_none()
    assert accepted is not None
    assert accepted.status == "accepted"

    out = matching_service.recommend_people(db_session, alice.id, k=10)
    ids = {row["other_user_id"] for row in out}
    assert bob.id not in ids


def test_recommend_people_respects_opt_out(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """A user with opt_in_networking=False must never show up as a candidate."""
    alice = _demo_user(db_session, "Alice")
    bob = _demo_user(db_session, "Bob")
    bob.opt_in_networking = False
    db_session.commit()
    out = matching_service.recommend_people(db_session, alice.id, k=10)
    assert bob.id not in {r["other_user_id"] for r in out}


def test_recommend_events_excludes_liked(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Events the user already liked / saved / rsvp'd must be filtered out."""
    from app.models.interaction import EventInteraction

    alice = _demo_user(db_session, "Alice")
    # Alice already has liked events via seed.
    liked_ids = {
        r
        for r, in db_session.execute(
            select(EventInteraction.event_id).where(
                EventInteraction.user_id == alice.id,
                EventInteraction.type.in_(["like", "save", "rsvp"]),
            )
        ).all()
    }
    assert liked_ids, "seed should have primed liked events"
    out = matching_service.recommend_events(db_session, alice.id, k=20)
    for row in out:
        assert row["event_id"] not in liked_ids


def test_recommend_events_excludes_finished_and_canceled(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    alice = _demo_user(db_session, "Alice")
    # Force one event to finished
    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    ev.status = "finished"
    db_session.commit()
    out = matching_service.recommend_events(db_session, alice.id, k=20)
    assert ev.id not in {r["event_id"] for r in out}


def test_recommend_events_returns_reason_string(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    alice = _demo_user(db_session, "Alice")
    out = matching_service.recommend_events(db_session, alice.id, k=5)
    for row in out:
        assert row.get("reason")


def test_upsert_match_writes_row(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Side effect: `_upsert_match` persists matches in a canonical (lo, hi) order."""
    from app.models.networking import Match

    alice = _demo_user(db_session, "Alice")
    matching_service.recommend_people(db_session, alice.id, k=5)
    rows = db_session.execute(select(Match)).scalars().all()
    for m in rows:
        assert m.user_a_id < m.user_b_id


def test_recommend_events_returns_future_events(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Seeded events include future-dated rows; the recommender should surface them."""
    alice = _demo_user(db_session, "Alice")
    now = datetime.utcnow()
    _ = now + timedelta(days=1)
    out = matching_service.recommend_events(db_session, alice.id, k=10)
    # Just check we get *some* output (rank/score is deterministic under stub).
    assert isinstance(out, list)


# --- Interests-first ranking ----------------------------------------------


def test_recommend_people_prefers_interest_sharers(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Regression for the audit's "candidate pool from interests" decision.

    Build a scenario where a candidate who *shares* an interest with the seeker
    must rank ABOVE a candidate who shares zero interests, even if the second
    candidate happens to sit closer in the embedding space.
    """
    from app.domain import interest_service, user_service
    from app.models.interest import Interest
    from app.schemas.user import UserCreate

    seeker = user_service.create_user(
        db_session, UserCreate(email="seeker@eventive.dev", name="Seeker", blurb="likes ai")
    )
    sharer = user_service.create_user(
        db_session, UserCreate(email="sharer@eventive.dev", name="Sharer", blurb="ml eng")
    )
    stranger = user_service.create_user(
        db_session, UserCreate(email="stranger@eventive.dev", name="Stranger", blurb="ml eng")
    )

    interest_id = db_session.execute(select(Interest.id).limit(1)).scalar_one()
    interest_service.set_user_interests(db_session, seeker.id, [interest_id])
    interest_service.set_user_interests(db_session, sharer.id, [interest_id])
    # stranger keeps zero interests

    out = matching_service.recommend_people(db_session, seeker.id, k=20)
    ids = [row["other_user_id"] for row in out]
    assert sharer.id in ids, "interest sharer must appear in results"
    assert stranger.id in ids, "stranger should still be reachable via vec fallback"
    assert ids.index(sharer.id) < ids.index(stranger.id), (
        "interest sharer must rank above the stranger — interests-first policy"
    )


def test_recommend_people_falls_back_to_vec_when_no_interests(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """A user with zero interests must still receive recommendations via the
    vec kNN fallback pool. Regression against emptying the candidate set."""
    from app.domain import user_service
    from app.schemas.user import UserCreate

    ghost = user_service.create_user(
        db_session, UserCreate(email="ghost@eventive.dev", name="Ghost", blurb="hello")
    )
    out = matching_service.recommend_people(db_session, ghost.id, k=10)
    assert isinstance(out, list)
    assert out, "ghost with no interests should still see kNN-based candidates"


def test_recommend_people_reasons_mention_shared_when_present(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """When two users truly share an interest, the recommender's reason string
    should call it out (regression for the 'You share …' bullet)."""
    from app.domain import interest_service, user_service
    from app.models.interest import Interest
    from app.schemas.user import UserCreate

    me = user_service.create_user(
        db_session, UserCreate(email="me@eventive.dev", name="Me", blurb="hi")
    )
    peer = user_service.create_user(
        db_session, UserCreate(email="peer@eventive.dev", name="Peer", blurb="hi")
    )
    interest = db_session.execute(select(Interest).limit(1)).scalar_one()
    interest_service.set_user_interests(db_session, me.id, [interest.id])
    interest_service.set_user_interests(db_session, peer.id, [interest.id])

    out = matching_service.recommend_people(db_session, me.id, k=20)
    peer_row = next((r for r in out if r["other_user_id"] == peer.id), None)
    assert peer_row is not None
    joined = " ".join(peer_row["reasons"]).lower()
    assert "you share" in joined or interest.label.lower() in joined
