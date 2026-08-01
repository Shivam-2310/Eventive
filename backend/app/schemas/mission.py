from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MissionCreate(BaseModel):
    title: str
    description: str | None = None
    rule: dict[str, Any]
    points: int = 10
    badge_icon_url: str | None = None
    active: bool = True


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    rule: dict[str, Any]
    points: int
    badge_icon_url: str | None = None
    active: bool
    created_at: datetime


class MissionProgressRead(BaseModel):
    mission: MissionRead
    progress: dict[str, Any] | None = None
    completed_at: datetime | None = None
    points_awarded: int
