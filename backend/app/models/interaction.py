from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class EventInteraction(Base):
    __tablename__ = "event_interaction"
    __table_args__ = (
        # Every (user, event, type) triplet is unique — the same person cannot
        # save/like/rsvp the same event twice. Enforced at the DB layer so the
        # frontend can retry safely and never produce duplicate profile items.
        UniqueConstraint("user_id", "event_id", "type", name="uq_event_interaction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # like|save|add_to_my_day|mark_attended|add_to_calendar|rsvp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class EventCardReaction(Base):
    __tablename__ = "event_card_reaction"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_id",
            "prompt_type",
            "prompt_ref_id",
            name="uq_event_card_reaction",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), index=True, nullable=False)
    prompt_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # cover|speaker|topic|when_where|vibe|who_is_going
    prompt_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reaction: Mapped[str] = mapped_column(String(20), nullable=False)  # like|comment|pass
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
