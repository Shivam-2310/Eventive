"""Switch to 384-dim local embeddings (bge-small-en-v1.5).

Previous vec_* virtual tables were declared FLOAT[768] to match Gemini's
truncated output. The new fastembed-based LocalEmbedProvider ships a 384-dim
model, so the sqlite-vec tables must be dropped and recreated at the new
width — sqlite-vec has no ALTER for column dimension.

Also truncates `document_chunk` because its rows are keyed 1:1 with the old
`vec_document` blobs; keeping them would leave dangling chunk_ids that never
resolve. The RAG backfill will rebuild these lazily on the next seed run.

Revision ID: 004_local_embeddings
Revises: 003_relax_reel_duration
Create Date: 2026-07-12 03:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004_local_embeddings"
down_revision: str | Sequence[str] | None = "003_relax_reel_duration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_DIM = 384
_OLD_DIM = 768

_VEC_TABLES: tuple[tuple[str, str], ...] = (
    ("vec_user_profile", "user_id"),
    ("vec_event", "event_id"),
    ("vec_interest", "interest_id"),
    ("vec_document", "chunk_id"),
)


def _recreate_vec_tables(dim: int) -> None:
    conn = op.get_bind()
    # sqlite-vec ships an extension that has to be loaded before any of the
    # virtual-table statements run. It's already loaded by db.py's engine
    # listener in the app, and Alembic reuses that engine here.
    for table, key in _VEC_TABLES:
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
        conn.exec_driver_sql(
            f"CREATE VIRTUAL TABLE {table} USING vec0("
            f"  {key} INTEGER PRIMARY KEY,"
            f"  embedding FLOAT[{dim}]"
            f")"
        )


def upgrade() -> None:
    # Drop all RAG chunks. Their ids used to point at vec_document rows that
    # will no longer exist after the DROP; leaving them would orphan the
    # search index. RAG backfill regenerates them next run.
    op.execute("DELETE FROM document_chunk")
    _recreate_vec_tables(_NEW_DIM)


def downgrade() -> None:
    op.execute("DELETE FROM document_chunk")
    _recreate_vec_tables(_OLD_DIM)
