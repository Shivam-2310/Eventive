from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConnectionCreate(BaseModel):
    receiver_id: int
    hook_interest_id: int | None = None


class ConnectionUpdate(BaseModel):
    status: str  # accepted|declined|blocked


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requester_id: int
    receiver_id: int
    hook_interest_id: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int | None = None
    event_id: int | None = None
    title: str | None = None
    created_at: datetime
    participant_ids: list[int] = []


class MessageCreate(BaseModel):
    body: str | None = None
    kind: str = "text"
    payload: dict[str, Any] | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    sender_id: int | None = None
    body: str | None = None
    kind: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class AttendTogetherInvite(BaseModel):
    event_id: int


class MatchRead(BaseModel):
    other_user_id: int
    name: str
    headline: str | None = None
    score: float
    reasons: list[str]


class EventRecommendation(BaseModel):
    event_id: int
    title: str
    track: str | None = None
    start_time: datetime | None = None
    score: float
    reason: str
