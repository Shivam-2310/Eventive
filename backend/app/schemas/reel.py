from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReelInteractionCreate(BaseModel):
    type: str
    watch_ms: int | None = None


class ReelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    event_id: int | None = None
    speaker_id: int | None = None
    caption: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    status: str
    transcript: str | None = None
    error: str | None = None
    created_at: datetime


class ReelFeedItem(BaseModel):
    reel: ReelRead
    score: float
    likes: int
