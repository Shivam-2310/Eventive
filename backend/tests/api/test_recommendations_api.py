"""Recommendations REST: people + events + reel amplification boost."""
from __future__ import annotations

from sqlalchemy import select

from app.models.event import Event
from app.models.networking import Connection
from app.models.reel import Reel
from app.models.user import User


def test_recommend_people_shape(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/recommendations/people/2?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for row in body:
        assert "other_user_id" in row
        assert "score" in row
        assert "reasons" in row


def test_refresh_people_endpoint(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/recommendations/people/2/refresh")
    assert r.status_code == 200
    assert "generated" in r.json()


def test_recommend_events_shape(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/recommendations/events/2?limit=5")
    assert r.status_code == 200
    body = r.json()
    for row in body:
        assert "event_id" in row
        assert "score" in row
        assert row.get("reason")


def test_reel_feed_boosts_connected_users(seeded, client, db_session) -> None:  # noqa: ANN001, ARG001
    """Regression: user 2 <-> user 3 accepted; user 3's reel (for an event that
    matches user 2's liked interest track) should rank first in user 2's feed."""
    from app.models.interaction import EventInteraction

    users = db_session.execute(select(User).order_by(User.id)).scalars().all()
    # After seed, user ids are: 1 admin, 2 alice, 3 bob, 4 carol.
    alice = next(u for u in users if u.name == "Alice")
    bob = next(u for u in users if u.name == "Bob")

    # Ensure they are connected accepted.
    conn = db_session.execute(
        select(Connection).where(
            (
                (Connection.requester_id == alice.id) & (Connection.receiver_id == bob.id)
            ) | ((Connection.requester_id == bob.id) & (Connection.receiver_id == alice.id))
        )
    ).scalar_one_or_none()
    assert conn is not None and conn.status == "accepted"

    # Pick an event alice liked to align the reel event_id.
    liked_event_id = db_session.execute(
        select(EventInteraction.event_id).where(
            EventInteraction.user_id == alice.id, EventInteraction.type == "like"
        )
    ).scalars().first()
    assert liked_event_id is not None

    # Bob (connected) uploads a reel for that event.
    connected_reel = Reel(
        user_id=bob.id, event_id=liked_event_id, status="ready", storage_key="reels/bob.mp4"
    )
    # Unrelated reel from a non-connected admin user.
    admin = users[0]
    unrelated_event_id = db_session.execute(
        select(Event.id).where(Event.id != liked_event_id).order_by(Event.id)
    ).scalars().first()
    unrelated = Reel(
        user_id=admin.id, event_id=unrelated_event_id, status="ready", storage_key="reels/adm.mp4"
    )
    db_session.add_all([connected_reel, unrelated])
    db_session.commit()

    feed = client.get(f"/reels/feed?user_id={alice.id}").json()
    ids = [item["reel"]["id"] for item in feed]
    assert connected_reel.id in ids
    # bob's connected reel should outrank the admin's unrelated reel.
    assert ids.index(connected_reel.id) < ids.index(unrelated.id)
