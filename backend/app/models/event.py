from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class Event(Base):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    track: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    vibe_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vibe_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Speaker(Base):
    __tablename__ = "speaker"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    headshot_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    social_links: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string


class EventSpeaker(Base):
    __tablename__ = "event_speaker"
    __table_args__ = (UniqueConstraint("event_id", "speaker_id", name="uq_event_speaker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), index=True, nullable=False)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("speaker.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="panelist", nullable=False)  # host|panelist|moderator|keynote


class EventInterest(Base):
    __tablename__ = "event_interest"
    __table_args__ = (UniqueConstraint("event_id", "interest_id", name="uq_event_interest"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), index=True, nullable=False)
    interest_id: Mapped[int] = mapped_column(ForeignKey("interest.id", ondelete="CASCADE"), index=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
