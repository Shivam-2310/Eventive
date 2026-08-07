"""AI tools: like_event / rsvp / open_match / send_message_draft mutations."""
from __future__ import annotations

from sqlalchemy import select

from app.domain import event_service, user_service
from app.domain.ai import tools
from app.models.interaction import EventInteraction
from app.models.networking import Connection
from app.schemas.event import EventCreate
from app.schemas.user import UserCreate


def _mk_user(db, email: str) -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name="U"))


def test_like_event_records_interaction(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "l@eventive.dev")
    ev = event_service.create_event(db_session, EventCreate(title="E"))
    res = tools.like_event(db_session, u.id, ev.id)
    assert res["ok"] is True
    assert res["type"] == "like"
    row = db_session.execute(
        select(EventInteraction).where(EventInteraction.id == res["interaction_id"])
    ).scalar_one()
    assert row.event_id == ev.id
    assert row.type == "like"


def test_rsvp_event_records_interaction(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "r@eventive.dev")
    ev = event_service.create_event(db_session, EventCreate(title="E"))
    res = tools.rsvp_event(db_session, u.id, ev.id)
    assert res["ok"] is True
    assert res["type"] == "rsvp"


def test_open_match_creates_pending_connection(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "om-a@eventive.dev")
    b = _mk_user(db_session, "om-b@eventive.dev")
    res = tools.open_match(db_session, a.id, b.id)
    assert res["ok"] is True
    assert res["status"] == "pending"
    conn = db_session.execute(
        select(Connection).where(Connection.id == res["connection_id"])
    ).scalar_one()
    assert {conn.requester_id, conn.receiver_id} == {a.id, b.id}


def test_send_message_draft_never_touches_db() -> None:
    """`send_message_draft` returns a draft envelope without inserting anything."""
    res = tools.send_message_draft(user_id=1, other_user_id=2, body="hey")
    assert res == {"ok": True, "draft": "hey", "to_user_id": 2, "from_user_id": 1}


def test_parse_and_execute_matches_like(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "pe@eventive.dev")
    ev = event_service.create_event(db_session, EventCreate(title="E"))
    res = tools.parse_and_execute(db_session, u.id, f"please like event {ev.id}")
    assert res is not None and res["type"] == "like"


def test_parse_and_execute_matches_rsvp(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "pr@eventive.dev")
    ev = event_service.create_event(db_session, EventCreate(title="E"))
    res = tools.parse_and_execute(db_session, u.id, f"can you rsvp to event {ev.id}")
    assert res is not None and res["type"] == "rsvp"


def test_parse_and_execute_matches_open_match(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "pm-a@eventive.dev")
    b = _mk_user(db_session, "pm-b@eventive.dev")
    res = tools.parse_and_execute(db_session, a.id, f"open match with user {b.id}")
    assert res is not None and res["status"] == "pending"


def test_parse_and_execute_returns_none_for_unknown(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "u@eventive.dev")
    assert tools.parse_and_execute(db_session, u.id, "what is the weather like?") is None
