"""Chat service: connection lifecycle, thread + icebreaker, attend-together."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.domain import chat_service, user_service
from app.models.chat import ChatThread, ChatThreadParticipant, Message
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.networking import Connection
from app.schemas.event import EventCreate
from app.schemas.user import UserCreate


def _mk_user(db, email: str) -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name="U"))


def _mk_event(db, title: str = "e") -> Event:  # noqa: ANN001
    from app.domain import event_service

    return event_service.create_event(db, EventCreate(title=title, status="scheduled"))


def test_create_connection_pending(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "a@eventive.dev")
    b = _mk_user(db_session, "b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, hook_interest_id=None)
    assert c.status == "pending"
    # calling again returns the existing row (idempotent).
    c2 = chat_service.create_connection(db_session, a.id, b.id, hook_interest_id=None)
    assert c2.id == c.id


def test_create_connection_self_raises(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "self@eventive.dev")
    with pytest.raises(ValueError):
        chat_service.create_connection(db_session, a.id, a.id, None)


def test_accept_creates_thread_and_icebreaker(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "acc-a@eventive.dev")
    b = _mk_user(db_session, "acc-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    updated = chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    assert updated.status == "accepted"

    thread = db_session.execute(
        select(ChatThread).where(ChatThread.connection_id == c.id)
    ).scalar_one()
    participants = db_session.execute(
        select(ChatThreadParticipant.user_id).where(ChatThreadParticipant.thread_id == thread.id)
    ).scalars().all()
    assert set(participants) == {a.id, b.id}

    messages = db_session.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.id)
    ).scalars().all()
    # Message 0 is the icebreaker.
    assert messages
    assert messages[0].kind == "icebreaker"
    assert messages[0].body


def test_only_receiver_can_accept(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "r1@eventive.dev")
    b = _mk_user(db_session, "r2@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    with pytest.raises(PermissionError):
        chat_service.update_connection_status(db_session, a.id, c.id, "accepted")


def test_invalid_status_raises(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "s1@eventive.dev")
    b = _mk_user(db_session, "s2@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    with pytest.raises(ValueError):
        chat_service.update_connection_status(db_session, b.id, c.id, "banana")


def test_post_message_writes_row(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "m1@eventive.dev")
    b = _mk_user(db_session, "m2@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    m = chat_service.post_message(db_session, thread.id, a.id, "hi there")
    assert m.id and m.body == "hi there"
    assert m.kind == "text"


def test_post_message_invalid_kind_raises(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "k1@eventive.dev")
    b = _mk_user(db_session, "k2@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    with pytest.raises(ValueError):
        chat_service.post_message(db_session, thread.id, a.id, "hi", kind="unknown")


def test_is_participant(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "p1@eventive.dev")
    b = _mk_user(db_session, "p2@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    assert chat_service.is_participant(db_session, thread.id, a.id) is True
    other = _mk_user(db_session, "other@eventive.dev")
    assert chat_service.is_participant(db_session, thread.id, other.id) is False


def test_attend_together_flow_rsvps_both(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "at-a@eventive.dev")
    b = _mk_user(db_session, "at-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    ev = _mk_event(db_session, "AttendTogether")

    invite = chat_service.attend_together_invite(db_session, thread.id, a.id, ev.id)
    assert invite.kind == "attend_together_invite"

    accepted = chat_service.attend_together_accept(db_session, thread.id, b.id, invite.id)
    assert accepted.kind == "attend_together_accepted"

    # Both participants now have an rsvp interaction for the event.
    rsvps = db_session.execute(
        select(EventInteraction).where(
            EventInteraction.event_id == ev.id, EventInteraction.type == "rsvp"
        )
    ).scalars().all()
    rsvp_users = {r.user_id for r in rsvps}
    assert rsvp_users == {a.id, b.id}


def test_attend_together_missing_event_raises(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "mt-a@eventive.dev")
    b = _mk_user(db_session, "mt-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    with pytest.raises(ValueError):
        chat_service.attend_together_invite(db_session, thread.id, a.id, 99_999)


def test_message_to_dict_parses_payload_json(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "md-a@eventive.dev")
    b = _mk_user(db_session, "md-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    m = chat_service.post_message(db_session, thread.id, a.id, "hi", payload={"k": "v"})
    d = chat_service.message_to_dict(m)
    assert d["payload"] == {"k": "v"}
    assert d["thread_id"] == thread.id


def test_list_threads_for_user(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "lt-a@eventive.dev")
    b = _mk_user(db_session, "lt-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")

    threads = chat_service.list_threads_for_user(db_session, a.id)
    assert threads
    t = threads[0]
    assert set(t["participant_ids"]) == {a.id, b.id}


def test_list_connections_by_user(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "lc-a@eventive.dev")
    b = _mk_user(db_session, "lc-b@eventive.dev")
    conn = chat_service.create_connection(db_session, a.id, b.id, None)
    rows = chat_service.list_connections(db_session, a.id)
    assert any(r.id == conn.id for r in rows)


def test_attend_together_accept_wrong_message_id_raises(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "w-a@eventive.dev")
    b = _mk_user(db_session, "w-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    with pytest.raises(ValueError):
        chat_service.attend_together_accept(db_session, thread.id, b.id, 99_999)


def test_existing_connection_returned_across_reverse_pair(db_session) -> None:  # noqa: ANN001
    """`create_connection(a,b)` after `create_connection(b,a)` returns the existing row."""
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "rv-a@eventive.dev")
    b = _mk_user(db_session, "rv-b@eventive.dev")
    forward = chat_service.create_connection(db_session, a.id, b.id, None)
    reverse = chat_service.create_connection(db_session, b.id, a.id, None)
    assert forward.id == reverse.id
    # Only one Connection row across the (a,b) pair.
    rows = db_session.execute(
        select(Connection).where(
            (Connection.requester_id.in_([a.id, b.id]))
            & (Connection.receiver_id.in_([a.id, b.id]))
        )
    ).scalars().all()
    assert len(rows) == 1


def test_post_message_payload_json_roundtrip_serialized(db_session) -> None:  # noqa: ANN001
    """`payload` stored as JSON string, decoded on read."""
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "json-a@eventive.dev")
    b = _mk_user(db_session, "json-b@eventive.dev")
    c = chat_service.create_connection(db_session, a.id, b.id, None)
    chat_service.update_connection_status(db_session, b.id, c.id, "accepted")
    thread = db_session.execute(select(ChatThread).where(ChatThread.connection_id == c.id)).scalar_one()
    m = chat_service.post_message(db_session, thread.id, a.id, None, kind="system", payload={"foo": [1, 2]})
    stored = db_session.execute(select(Message).where(Message.id == m.id)).scalar_one()
    assert json.loads(stored.payload) == {"foo": [1, 2]}
