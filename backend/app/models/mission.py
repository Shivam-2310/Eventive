from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class Mission(Base):
    __tablename__ = "mission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    points: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    badge_icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class UserMissionProgress(Base):
    __tablename__ = "user_mission_progress"
    __table_args__ = (UniqueConstraint("user_id", "mission_id", name="uq_user_mission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    mission_id: Mapped[int] = mapped_column(ForeignKey("mission.id", ondelete="CASCADE"), index=True, nullable=False)
    progress: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
