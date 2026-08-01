"""Relax the reel duration CHECK constraint from 10.5s to 60.5s.

Reels are still short-form but the 10-second cap was too tight for demo clips.

SQLite has no `ALTER TABLE DROP CONSTRAINT`. The canonical workaround via
`batch_alter_table` is fragile for CHECK constraints because SQLAlchemy's
reflection of CHECK expressions on SQLite is name-only, so we use the
documented `writable_schema` pragma to rewrite the constraint text in place.
Faster than a full table recreate and preserves all row data.

Revision ID: 003_relax_reel_duration
Revises: 002_auth_refresh
Create Date: 2026-07-12 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_relax_reel_duration"
down_revision: str | Sequence[str] | None = "002_auth_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _swap_check(old_expr: str, new_expr: str) -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect != "sqlite":
        # For other backends we could use op.drop_constraint / create_check_constraint
        # here, but this project only ships SQLite. Bail loudly if that changes.
        raise RuntimeError(f"unsupported dialect for CHECK swap: {dialect}")

    row = conn.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name='reel'")
    ).first()
    if row is None:
        return
    old_sql: str = row[0]
    if old_expr not in old_sql:
        # Constraint text isn't what we expected — probably already swapped or
        # created via a different code path. Nothing to do.
        return
    new_sql = old_sql.replace(old_expr, new_expr)

    conn.exec_driver_sql("PRAGMA writable_schema = 1")
    conn.execute(
        sa.text(
            "UPDATE sqlite_master SET sql = :sql "
            "WHERE type = 'table' AND name = 'reel'"
        ),
        {"sql": new_sql},
    )
    # Bump the schema cookie so every open connection (uvicorn's pool included)
    # invalidates its cached schema and re-parses on the next query.
    current_ver = conn.execute(sa.text("PRAGMA schema_version")).scalar() or 0
    conn.exec_driver_sql(f"PRAGMA schema_version = {int(current_ver) + 1}")
    conn.exec_driver_sql("PRAGMA writable_schema = 0")

    integrity = conn.execute(sa.text("PRAGMA integrity_check")).scalar()
    if integrity != "ok":
        raise RuntimeError(f"integrity_check failed after CHECK swap: {integrity!r}")


def upgrade() -> None:
    _swap_check(
        "duration_seconds IS NULL OR duration_seconds <= 10.5",
        "duration_seconds IS NULL OR duration_seconds <= 60.5",
    )


def downgrade() -> None:
    _swap_check(
        "duration_seconds IS NULL OR duration_seconds <= 60.5",
        "duration_seconds IS NULL OR duration_seconds <= 10.5",
    )
