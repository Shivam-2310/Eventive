"""CSV importers: seed fixtures + malformed regression guards."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from app.domain.ingestion.csv_importer import import_events_csv, import_speakers_csv
from app.models.event import Event, Speaker

SEED_DIR = Path(__file__).resolve().parents[4] / "seed"


def test_events_csv_happy_path_adds_fifty(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    csv_bytes = (SEED_DIR / "events.csv").read_bytes()
    stats = import_events_csv(db_session, csv_bytes)
    assert stats["failed"] == 0, stats
    assert stats["added"] == 50
    assert stats["updated"] == 0
    total = db_session.execute(select(func.count(Event.id))).scalar()
    assert total == 50


def test_events_csv_upsert_second_pass_updates(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    csv_bytes = (SEED_DIR / "events.csv").read_bytes()
    import_events_csv(db_session, csv_bytes)
    stats = import_events_csv(db_session, csv_bytes)
    assert stats["added"] == 0
    assert stats["updated"] == 50


def test_events_csv_malformed_row_is_counted_but_does_not_crash(db_session) -> None:  # noqa: ANN001
    """Regression guard for the events.csv quoting fix (title with commas)."""
    from app.infra.db import ensure_schema

    ensure_schema()
    body = (
        b"external_id,title,track,start_time,end_time,timezone,status\n"
        b"probe-bad,,AI,2026-07-11T09:00:00,2026-07-11T10:00:00,UTC,scheduled\n"
        b"probe-good,Valid Session,AI,2026-07-11T09:00:00,2026-07-11T10:00:00,UTC,scheduled\n"
    )
    stats = import_events_csv(db_session, body)
    assert stats["failed"] >= 1
    assert stats["added"] == 1
    # Error trail is informative — includes the offending row number.
    assert stats["errors"] and any("row" in e for e in stats["errors"])


def test_events_csv_capacity_int_parsing(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    body = (
        b"external_id,title,capacity,start_time,end_time,timezone,status\n"
        b"cap-1,Capacity Session,250,2026-07-11T09:00:00,2026-07-11T10:00:00,UTC,scheduled\n"
    )
    stats = import_events_csv(db_session, body)
    assert stats == {"added": 1, "updated": 0, "failed": 0, "errors": []}
    ev = db_session.execute(select(Event).where(Event.external_id == "cap-1")).scalar_one()
    assert ev.capacity == 250


def test_speakers_csv_seed_loads_all_rows(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    csv_bytes = (SEED_DIR / "speakers.csv").read_bytes()
    stats = import_speakers_csv(db_session, csv_bytes)
    assert stats["failed"] == 0, stats
    assert stats["added"] == 20
    total = db_session.execute(select(func.count(Speaker.id))).scalar()
    assert total == 20


def test_speakers_csv_upsert_updates_bio(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    body_first = (
        b"name,bio,company\n"
        b"Ada Lovelace,Original,ADA Corp\n"
    )
    body_update = (
        b"name,bio,company\n"
        b"Ada Lovelace,Updated bio,ADA Corp v2\n"
    )
    import_speakers_csv(db_session, body_first)
    stats = import_speakers_csv(db_session, body_update)
    assert stats["updated"] == 1
    assert stats["added"] == 0
    row = db_session.execute(select(Speaker).where(Speaker.name == "Ada Lovelace")).scalar_one()
    assert row.bio == "Updated bio"
    assert row.company == "ADA Corp v2"


def test_speakers_csv_missing_name_fails_row(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    body = b"name,bio\n,orphan\nJane Q Public,ok\n"
    stats = import_speakers_csv(db_session, body)
    assert stats["failed"] == 1
    assert stats["added"] == 1
