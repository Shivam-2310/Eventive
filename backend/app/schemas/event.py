from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpeakerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    bio: str | None = None
    headshot_url: str | None = None
    company: str | None = None
    title: str | None = None
    social_links: dict | list | None = None


class SpeakerCreate(SpeakerBase):
    pass


class SpeakerUpdate(BaseModel):
    name: str | None = None
    bio: str | None = None
    headshot_url: str | None = None
    company: str | None = None
    title: str | None = None
    social_links: dict | list | None = None


class SpeakerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    bio: str | None = None
    headshot_url: str | None = None
    company: str | None = None
    title: str | None = None
    social_links: dict | list | None = None


class EventBase(BaseModel):
    external_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    abstract: str | None = None
    track: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    room: str | None = None
    capacity: int | None = None
    status: str = "scheduled"
    cover_image_url: str | None = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    abstract: str | None = None
    track: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    room: str | None = None
    capacity: int | None = None
    status: str | None = None
    cover_image_url: str | None = None


class EventSpeakerAssign(BaseModel):
    speaker_id: int
    role: str = "panelist"


class EventInterestAssign(BaseModel):
    interest_ids: list[int]


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vibe_text: str | None = None
    created_at: datetime
    updated_at: datetime
    speakers: list[SpeakerRead] = []
    interests: list[dict] = []


class EventCardPrompt(BaseModel):
    prompt_type: str
    prompt_ref_id: int | None = None
    label: str
    body: str | None = None
    already_liked: bool = False


class EventCard(BaseModel):
    event: EventRead
    prompts: list[EventCardPrompt]
    already_liked_speaker: bool = False


class EventReaction(BaseModel):
    prompt_type: str
    prompt_ref_id: int | None = None
    reaction: str
    comment_text: str | None = Field(default=None, max_length=280)


class EventInteractionCreate(BaseModel):
    type: str
