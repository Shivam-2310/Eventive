from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.infra.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Root declarative base for all ORM models."""


def _sqlite_path_from_url(url: str) -> str | None:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    return None


def _ensure_data_dir() -> None:
    settings = get_settings()
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    db_path = _sqlite_path_from_url(settings.DATABASE_URL)
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    _ensure_data_dir()
    settings = get_settings()
    connect_args: dict = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        try:
            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("sqlite-vec load failed: %s", exc)
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
        finally:
            cur.close()

    return engine


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def reset_engine_for_tests() -> None:
    """Test-only hook: dispose the current engine and rebuild it from the current settings.

    Not called at runtime — the app process constructs a single engine on import. Tests
    that mutate ``DATABASE_URL`` / ``DATA_DIR`` between cases call this after clearing
    ``get_settings.cache_clear()`` so the next DB access picks up the new location.
    """
    global engine, SessionLocal
    try:
        engine.dispose()
    except Exception:
        pass
    engine = _build_engine()
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a database session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


EMBED_DIM = 384


def ensure_schema() -> None:
    """Convenience for tests / scripts — creates all tables directly (bypasses Alembic).

    Also creates the sqlite-vec virtual tables and the NL2SQL read-only views
    that live in the Alembic migration but are invisible to SQLAlchemy's ORM.
    """
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, key in (
            ("vec_user_profile", "user_id"),
            ("vec_event", "event_id"),
            ("vec_interest", "interest_id"),
            ("vec_document", "chunk_id"),
        ):
            conn.exec_driver_sql(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
                f"  {key} INTEGER PRIMARY KEY,"
                f"  embedding FLOAT[{EMBED_DIM}]"
                f")"
            )
        _create_ai_views(conn)


def _create_ai_views(conn) -> None:  # noqa: ANN001
    """(Re)create the read-only views that NL2SQL is allowed to SELECT from.

    Views are dropped-then-created so schema evolution (new columns, new
    joins) is picked up on the next boot without needing an Alembic migration.
    Called from both ``ensure_schema()`` and the app startup path in ``main.py``
    so a hot-reloaded backend picks up the widened set even against an
    existing seeded database.
    """
    conn.exec_driver_sql("DROP VIEW IF EXISTS ai_public_events_full")
    conn.exec_driver_sql("DROP VIEW IF EXISTS ai_public_events")
    conn.exec_driver_sql("DROP VIEW IF EXISTS ai_public_speakers")
    conn.exec_driver_sql("DROP VIEW IF EXISTS ai_public_interests")
    conn.exec_driver_sql("DROP VIEW IF EXISTS ai_public_reels")

    conn.exec_driver_sql(
        "CREATE VIEW ai_public_events AS "
        "SELECT id, title, track, start_time, end_time, location, room, capacity, "
        "status, abstract, description FROM event"
    )
    conn.exec_driver_sql(
        "CREATE VIEW ai_public_speakers AS "
        "SELECT id, name, title, company, bio FROM speaker"
    )
    conn.exec_driver_sql(
        "CREATE VIEW ai_public_interests AS "
        "SELECT id, label, category FROM interest"
    )
    # events + speakers + tags, comma-joined for NL2SQL LIKE filters.
    conn.exec_driver_sql(
        "CREATE VIEW ai_public_events_full AS "
        "SELECT e.id, e.title, e.track, e.start_time, e.end_time, e.location, e.room, "
        "e.capacity, e.status, e.abstract, e.description, "
        "COALESCE(( "
        "  SELECT GROUP_CONCAT(s.name, ', ') "
        "  FROM event_speaker es JOIN speaker s ON s.id = es.speaker_id "
        "  WHERE es.event_id = e.id "
        "), '') AS speakers, "
        "COALESCE(( "
        "  SELECT GROUP_CONCAT(LOWER(i.label), ', ') "
        "  FROM event_interest ei JOIN interest i ON i.id = ei.interest_id "
        "  WHERE ei.event_id = e.id "
        "), '') AS tags "
        "FROM event e"
    )
    conn.exec_driver_sql(
        "CREATE VIEW ai_public_reels AS "
        "SELECT r.id, u.name AS user_name, r.event_id, e.title AS event_title, "
        "r.caption, r.duration_seconds, r.status "
        "FROM reel r LEFT JOIN \"user\" u ON u.id = r.user_id "
        "LEFT JOIN event e ON e.id = r.event_id"
    )


def refresh_ai_views() -> None:
    """Public convenience for the app-startup path to keep AI views in sync."""
    with engine.begin() as conn:
        _create_ai_views(conn)


def ensure_interaction_uniqueness() -> None:
    """Idempotency backfill: dedupe legacy `event_interaction` rows then add
    a unique index on (user_id, event_id, type).

    Before this project introduced the uniqueness constraint the same button
    tap could produce multiple identical rows. New databases already have the
    constraint via SQLAlchemy metadata, but existing SQLite files created by
    older builds do not — this runs on startup so a hot-reload picks it up.
    """
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql(
                "DELETE FROM event_interaction "
                "WHERE id NOT IN ("
                "  SELECT MIN(id) FROM event_interaction "
                "  GROUP BY user_id, event_id, type"
                ")"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_event_interaction "
                "ON event_interaction(user_id, event_id, type)"
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ensure_interaction_uniqueness failed: %s", exc)


def readyz_check() -> bool:
    """Cheap read to prove DB + sqlite-vec extension are reachable."""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT vec_version()")
        return True
    except Exception as exc:
        logger.warning("readyz check failed: %s", exc)
        return False


def sqlite_path() -> str | None:
    return _sqlite_path_from_url(get_settings().DATABASE_URL)


def data_dir() -> Path:
    p = Path(get_settings().DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


# Make sure DATA_DIR/reels exists for the reels feature
os.makedirs(Path(get_settings().DATA_DIR) / "reels", exist_ok=True)
