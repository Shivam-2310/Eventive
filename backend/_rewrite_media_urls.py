"""One-shot: checkpoint WAL into eventive.db and strip the localhost prefix from
`speaker.headshot_url` and `event.cover_image_url` so the same DB works in any
deployment (Flutter web is served same-origin as the API in prod, so a relative
`/media/blob?...` URL resolves correctly).

Kept in-tree per project convention; safe to re-run — the UPDATE is idempotent."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "eventive.db"
PREFIX = "http://localhost:8000"


def main() -> None:
    if not DB.is_file():
        raise SystemExit(f"eventive.db not found at {DB}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        before_speakers = conn.execute(
            "SELECT COUNT(*) FROM speaker WHERE headshot_url LIKE ?",
            (f"{PREFIX}%",),
        ).fetchone()[0]
        before_events = conn.execute(
            "SELECT COUNT(*) FROM event WHERE cover_image_url LIKE ?",
            (f"{PREFIX}%",),
        ).fetchone()[0]

        conn.execute(
            "UPDATE speaker SET headshot_url = substr(headshot_url, ?) "
            "WHERE headshot_url LIKE ?",
            (len(PREFIX) + 1, f"{PREFIX}%"),
        )
        conn.execute(
            "UPDATE event SET cover_image_url = substr(cover_image_url, ?) "
            "WHERE cover_image_url LIKE ?",
            (len(PREFIX) + 1, f"{PREFIX}%"),
        )
        conn.commit()

        after_speakers = conn.execute(
            "SELECT COUNT(*) FROM speaker WHERE headshot_url LIKE '/media/blob%'"
        ).fetchone()[0]
        after_events = conn.execute(
            "SELECT COUNT(*) FROM event WHERE cover_image_url LIKE '/media/blob%'"
        ).fetchone()[0]

        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        sample_speaker = conn.execute(
            "SELECT id, name, headshot_url FROM speaker ORDER BY id LIMIT 1"
        ).fetchone()
        sample_event = conn.execute(
            "SELECT id, title, cover_image_url FROM event ORDER BY id LIMIT 1"
        ).fetchone()
        alembic = conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

        print(f"stripped prefix from {before_speakers} speaker rows (now {after_speakers} relative)")
        print(f"stripped prefix from {before_events} event rows (now {after_events} relative)")
        if sample_speaker:
            print(f"sample speaker: id={sample_speaker['id']} name={sample_speaker['name']!r} url={sample_speaker['headshot_url']!r}")
        if sample_event:
            print(f"sample event:   id={sample_event['id']} title={sample_event['title'][:30]!r} url={sample_event['cover_image_url']!r}")
        if alembic:
            print(f"alembic version: {alembic['version_num']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
