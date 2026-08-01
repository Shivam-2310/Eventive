from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class ChatThread(Base):
    __tablename__ = "chat_thread"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connection.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ChatThreadParticipant(Base):
    __tablename__ = "chat_thread_participant"
    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_thread_participant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("chat_thread.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("chat_thread.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="text", nullable=False)
    # text | attend_together_invite | attend_together_accepted | system | icebreaker
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
