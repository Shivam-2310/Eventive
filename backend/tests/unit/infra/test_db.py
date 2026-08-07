"""DB engine bootstrap: PRAGMAs, sqlite-vec, schema + view creation, readyz."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text


def test_pragmas_and_vec_extension_loaded() -> None:
    """Every new connection must have WAL, FK on, and sqlite-vec loaded."""
    from app.infra.db import engine

    with engine.connect() as conn:
        journal = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
        vec_version = conn.exec_driver_sql("SELECT vec_version()").scalar()
    # For file-backed SQLite journal_mode is 'wal'; some builds report 'memory' for :memory:.
    assert str(journal).lower() in {"wal", "memory"}
    assert int(fk) == 1
    assert vec_version is not None


def test_ensure_schema_creates_orm_tables_and_vec_and_views() -> None:
    """`ensure_schema()` covers ORM tables + `vec_*` virtuals + NL2SQL views."""
    from app.infra.db import engine, ensure_schema

    ensure_schema()
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for expected in (
        "user",
        "interest",
        "user_interest",
        "event",
        "speaker",
        "event_speaker",
        "event_interest",
        "event_interaction",
        "event_card_reaction",
        "reel",
        "reel_interaction",
        "connection",
        "match",
        "chat_thread",
        "chat_thread_participant",
        "message",
        "document_chunk",
        "ai_session",
        "ai_message",
        "mission",
        "user_mission_progress",
        "notification",
        "ingestion_job",
        "admin_audit_log",
    ):
        assert expected in tables, f"missing ORM table: {expected}"

    with engine.connect() as conn:
        for vec in ("vec_user_profile", "vec_event", "vec_interest", "vec_document"):
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE name = :n"), {"n": vec}
            ).first()
            assert row is not None, f"missing vec table: {vec}"
        for view in ("ai_public_events", "ai_public_speakers"):
            row = conn.execute(
                text("SELECT type FROM sqlite_master WHERE name = :n"), {"n": view}
            ).first()
            assert row is not None and row[0] == "view", f"missing view: {view}"


def test_ensure_schema_is_idempotent() -> None:
    """Second call must not raise even though vec + view already exist."""
    from app.infra.db import ensure_schema

    ensure_schema()
    ensure_schema()


def test_readyz_check_reports_true_when_healthy() -> None:
    from app.infra.db import readyz_check

    assert readyz_check() is True


def test_sqlite_path_and_data_dir_helpers(tmp_data_dir: Path) -> None:
    from app.infra.db import data_dir, sqlite_path

    assert data_dir() == tmp_data_dir
    path = sqlite_path()
    assert path is not None
    # The tmp_data_dir path should be the parent of the sqlite file.
    assert Path(path).parent == tmp_data_dir


def test_reset_engine_for_tests_repoints_engine(tmp_data_dir: Path) -> None:
    """The test hook must dispose the current engine and pick up new settings."""
    from app.infra import db as db_module
    from app.infra.config import get_settings

    ensure_1_path = tmp_data_dir / "eventive.db"
    db_module.ensure_schema()
    assert ensure_1_path.exists()

    # Point the engine at a fresh URL and confirm the module rebinds.
    new_dir = tmp_data_dir / "swap"
    new_dir.mkdir()
    new_url = f"sqlite:///{(new_dir / 'other.db').as_posix()}"
    import os

    os.environ["DATABASE_URL"] = new_url
    get_settings.cache_clear()
    db_module.reset_engine_for_tests()
    db_module.ensure_schema()

    # SessionLocal now yields sessions bound to the new engine.
    session = db_module.SessionLocal()
    try:
        assert session.bind is db_module.engine
    finally:
        session.close()
    assert (new_dir / "other.db").exists()
