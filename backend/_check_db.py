"""Sanity check on backend/data/eventive.db: does it already carry a full seeded
dataset (users, events, reels, interactions), so dropping the boot-time seed
won't strip the demo?"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "eventive.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    for tbl in [
        "user",
        "interest",
        "speaker",
        "event",
        "mission",
        "reel",
        "reel_interaction",
        "event_interaction",
        "event_card_reaction",
        "connection",
        "notification",
        "chat_thread",
        "message",
    ]:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl:22s} {n}")
        except sqlite3.OperationalError as exc:
            print(f"  {tbl:22s} <missing: {exc}>")
    print()
    print("sample users:")
    for row in conn.execute(
        "SELECT id, email, name, is_admin FROM user ORDER BY id LIMIT 8"
    ):
        print(" ", row)
    print()
    print("reels — first 5:")
    for row in conn.execute(
        "SELECT id, caption, storage_key, video_url FROM reel ORDER BY id LIMIT 5"
    ):
        print(" ", row)
    print()
    print("alembic:", conn.execute("SELECT version_num FROM alembic_version").fetchone())
    conn.close()


if __name__ == "__main__":
    main()
