"""JSON bundle importer: nested speakers+events with speaker refs."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.domain.ingestion.json_importer import import_json_bundle
from app.models.event import Event, EventSpeaker, Speaker


def test_json_bundle_happy_path(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()

    payload = {
        "speakers": [
            {"name": "Grace Hopper", "title": "Rear Admiral", "company": "US Navy"},
            {"name": "Barbara Liskov", "title": "Professor", "company": "MIT"},
        ],
        "events": [
            {
                "external_id": "j-1",
                "title": "History of Compilers",
                "track": "Systems",
                "start_time": "2026-07-11T09:00:00Z",
                "end_time": "2026-07-11T10:00:00Z",
                "speakers": [
                    {"name": "Grace Hopper", "role": "keynote"},
                    {"name": "Barbara Liskov", "role": "panelist"},
                ],
            },
            {
                "external_id": "j-2",
                "title": "SOLID Revisited",
                "speakers": ["Barbara Liskov"],
            },
        ],
    }
    stats = import_json_bundle(db_session, json.dumps(payload).encode())
    assert stats["events_added"] == 2
    assert stats["events_updated"] == 0
    assert stats["speakers_added"] == 2
    assert stats["failed"] == 0

    ev = db_session.execute(select(Event).where(Event.external_id == "j-1")).scalar_one()
    joins = db_session.execute(
        select(EventSpeaker).where(EventSpeaker.event_id == ev.id)
    ).scalars().all()
    assert len(joins) == 2
    roles = sorted(j.role for j in joins)
    assert roles == ["keynote", "panelist"]


def test_json_bundle_invalid_payload_returns_error(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()

    stats = import_json_bundle(db_session, b"not-json")
    assert stats["failed"] == 0
    assert stats["errors"] and "invalid json" in stats["errors"][0]


def test_json_bundle_missing_title_fails_event(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()

    payload = {"events": [{"external_id": "no-title"}]}
    stats = import_json_bundle(db_session, json.dumps(payload).encode())
    assert stats["failed"] == 1
    assert stats["events_added"] == 0


def test_json_bundle_creates_missing_speaker_reference(db_session) -> None:  # noqa: ANN001
    """If an event lists a speaker not defined in `speakers[]`, importer creates a stub."""
    from app.infra.db import ensure_schema

    ensure_schema()
    payload = {
        "events": [
            {
                "external_id": "auto-1",
                "title": "Auto-created speaker",
                "speakers": ["Unlisted Person"],
            }
        ]
    }
    stats = import_json_bundle(db_session, json.dumps(payload).encode())
    assert stats["events_added"] == 1
    speaker = db_session.execute(
        select(Speaker).where(Speaker.name == "Unlisted Person")
    ).scalar_one()
    assert speaker.name == "Unlisted Person"


def test_json_bundle_upsert_second_pass_updates(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    payload_v1 = {"events": [{"external_id": "up-1", "title": "v1"}]}
    payload_v2 = {"events": [{"external_id": "up-1", "title": "v2"}]}
    import_json_bundle(db_session, json.dumps(payload_v1).encode())
    stats = import_json_bundle(db_session, json.dumps(payload_v2).encode())
    assert stats["events_updated"] == 1
    ev = db_session.execute(select(Event).where(Event.external_id == "up-1")).scalar_one()
    assert ev.title == "v2"
