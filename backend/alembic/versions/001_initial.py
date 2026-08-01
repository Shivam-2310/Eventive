"""initial schema — all tables, sqlite-vec virtual tables, and ai read-only views.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-10 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBED_DIM = 768


def upgrade() -> None:
    # --- USER ---
    op.create_table(
        "user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("headline", sa.String(255)),
        sa.Column("company", sa.String(200)),
        sa.Column("role", sa.String(120)),
        sa.Column("timezone", sa.String(80)),
        sa.Column("blurb", sa.Text),
        sa.Column("opt_in_networking", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("last_seen_at", sa.DateTime),
    )
    op.create_index("ix_user_email", "user", ["email"])

    # --- INTEREST ---
    op.create_table(
        "interest",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.String(120), nullable=False, unique=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("is_predefined", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    op.create_table(
        "user_interest",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("interest_id", sa.Integer, sa.ForeignKey("interest.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("weight", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'self'")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "interest_id", name="uq_user_interest"),
    )

    # --- EVENT + SPEAKER ---
    op.create_table(
        "event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("external_id", sa.String(120), unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("abstract", sa.Text),
        sa.Column("track", sa.String(80), index=True),
        sa.Column("start_time", sa.DateTime, index=True),
        sa.Column("end_time", sa.DateTime),
        sa.Column("timezone", sa.String(80)),
        sa.Column("location", sa.String(200)),
        sa.Column("room", sa.String(120)),
        sa.Column("capacity", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("cover_image_url", sa.String(1024)),
        sa.Column("vibe_text", sa.Text),
        sa.Column("vibe_source_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "speaker",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("bio", sa.Text),
        sa.Column("headshot_url", sa.String(1024)),
        sa.Column("company", sa.String(200)),
        sa.Column("title", sa.String(200)),
        sa.Column("social_links", sa.Text),
    )
    op.create_table(
        "event_speaker",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("speaker_id", sa.Integer, sa.ForeignKey("speaker.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(40), nullable=False, server_default=sa.text("'panelist'")),
        sa.UniqueConstraint("event_id", "speaker_id", name="uq_event_speaker"),
    )
    op.create_table(
        "event_interest",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("interest_id", sa.Integer, sa.ForeignKey("interest.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("weight", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.UniqueConstraint("event_id", "interest_id", name="uq_event_interest"),
    )

    # --- INTERACTIONS ---
    op.create_table(
        "event_interaction",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "event_card_reaction",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("prompt_type", sa.String(40), nullable=False),
        sa.Column("prompt_ref_id", sa.Integer),
        sa.Column("reaction", sa.String(20), nullable=False),
        sa.Column("comment_text", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "event_id", "prompt_type", "prompt_ref_id", name="uq_event_card_reaction"),
    )

    # --- REELS ---
    op.create_table(
        "reel",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="SET NULL")),
        sa.Column("speaker_id", sa.Integer, sa.ForeignKey("speaker.id", ondelete="SET NULL")),
        sa.Column("caption", sa.String(500)),
        sa.Column("video_url", sa.String(1024)),
        sa.Column("thumbnail_url", sa.String(1024)),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'processing'")),
        sa.Column("transcript", sa.Text),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("thumbnail_key", sa.String(500)),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds <= 10.5", name="ck_reel_max_duration"),
    )
    op.create_table(
        "reel_interaction",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reel_id", sa.Integer, sa.ForeignKey("reel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("watch_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    # --- NETWORKING + MATCHES ---
    op.create_table(
        "connection",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("requester_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("receiver_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("hook_interest_id", sa.Integer, sa.ForeignKey("interest.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("requester_id", "receiver_id", name="uq_connection_pair"),
    )
    op.create_table(
        "match",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_a_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_b_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("score", sa.Float, nullable=False, server_default=sa.text("0")),
        sa.Column("reasons", sa.Text),
        sa.Column("generated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("viewed_by_a_at", sa.DateTime),
        sa.Column("viewed_by_b_at", sa.DateTime),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_match_pair"),
    )

    # --- CHAT ---
    op.create_table(
        "chat_thread",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("connection_id", sa.Integer, sa.ForeignKey("connection.id", ondelete="SET NULL"), unique=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("event.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "chat_thread_participant",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("thread_id", sa.Integer, sa.ForeignKey("chat_thread.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("joined_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("thread_id", "user_id", name="uq_thread_participant"),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("thread_id", sa.Integer, sa.ForeignKey("chat_thread.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sender_id", sa.Integer, sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text),
        sa.Column("kind", sa.String(40), nullable=False, server_default=sa.text("'text'")),
        sa.Column("payload", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    # --- AI ---
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String(40), nullable=False, index=True),
        sa.Column("source_id", sa.Integer, nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("metadata", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "ai_session",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "ai_message",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("ai_session.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("retrieved_chunks", sa.Text),
        sa.Column("tool_calls", sa.Text),
        sa.Column("intent", sa.String(40)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )

    # --- MISSIONS ---
    op.create_table(
        "mission",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("rule", sa.Text, nullable=False),
        sa.Column("points", sa.Integer, nullable=False, server_default=sa.text("10")),
        sa.Column("badge_icon_url", sa.String(1024)),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_table(
        "user_mission_progress",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("mission_id", sa.Integer, sa.ForeignKey("mission.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("progress", sa.Text),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("points_awarded", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "mission_id", name="uq_user_mission"),
    )

    # --- NOTIFICATIONS ---
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("deep_link", sa.String(500)),
        sa.Column("read_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True, server_default=sa.func.current_timestamp()),
    )

    # --- ADMIN ---
    op.create_table(
        "ingestion_job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("stats", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("finished_at", sa.DateTime),
    )
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(80)),
        sa.Column("target_id", sa.String(80)),
        sa.Column("payload", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, index=True, server_default=sa.func.current_timestamp()),
    )

    # --- SQLITE-VEC virtual tables (raw SQL because vec0 isn't an ORM thing) ---
    for table, key in (
        ("vec_user_profile", "user_id"),
        ("vec_event", "event_id"),
        ("vec_interest", "interest_id"),
        ("vec_document", "chunk_id"),
    ):
        op.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
            f"  {key} INTEGER PRIMARY KEY,"
            f"  embedding FLOAT[{EMBED_DIM}]"
            f")"
        )

    # --- Read-only views for NL2SQL ---
    op.execute(
        "CREATE VIEW IF NOT EXISTS ai_public_events AS "
        "SELECT id, title, track, start_time, end_time, location, room, capacity, status, abstract, description "
        "FROM event"
    )
    op.execute(
        "CREATE VIEW IF NOT EXISTS ai_public_speakers AS "
        "SELECT id, name, title, company, bio FROM speaker"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS ai_public_events")
    op.execute("DROP VIEW IF EXISTS ai_public_speakers")
    for t in ("vec_user_profile", "vec_event", "vec_interest", "vec_document"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    for t in (
        "admin_audit_log",
        "ingestion_job",
        "notification",
        "user_mission_progress",
        "mission",
        "ai_message",
        "ai_session",
        "document_chunk",
        "message",
        "chat_thread_participant",
        "chat_thread",
        "match",
        "connection",
        "reel_interaction",
        "reel",
        "event_card_reaction",
        "event_interaction",
        "event_interest",
        "event_speaker",
        "speaker",
        "event",
        "user_interest",
        "interest",
        "user",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t}")
