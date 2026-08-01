"""Deterministic event/speaker lookup."""

from __future__ import annotations

from sqlalchemy import select

from app.domain.ai import lookup
from app.models.event import Event, Speaker


def test_event_by_id_full(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    ev = db_session.execute(select(Event).limit(1)).scalars().first()
    res = lookup.event_by_id(db_session, ev.id)
    assert res["ok"] is True
    assert ev.title in res["prose"]
    assert res["citations"] and res["citations"][0]["citation"] == f"event:{ev.id}"


def test_event_by_id_missing(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    res = lookup.event_by_id(db_session, 999_999)
    assert res["ok"] is False
    assert "couldn't find" in res["prose"].lower()


def test_speaker_by_name_exact(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    s = db_session.execute(select(Speaker).limit(1)).scalars().first()
    res = lookup.speaker_by_name(db_session, s.name)
    assert res["ok"] is True
    assert s.name in res["prose"]


def test_speaker_by_name_partial(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    s = db_session.execute(select(Speaker).limit(1)).scalars().first()
    head = s.name.split()[0]
    res = lookup.speaker_by_name(db_session, head)
    assert res["ok"] is True


def test_speaker_by_name_missing(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    res = lookup.speaker_by_name(db_session, "no such person")
    assert res["ok"] is False
