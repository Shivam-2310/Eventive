from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = None
    headline: str | None = None
    company: str | None = None
    role: str | None = None
    timezone: str | None = None
    blurb: str | None = None
    opt_in_networking: bool = True


class UserCreate(UserBase):
    is_admin: bool = False


class UserUpdate(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    headline: str | None = None
    company: str | None = None
    role: str | None = None
    timezone: str | None = None
    blurb: str | None = None
    opt_in_networking: bool | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_admin: bool
    created_at: datetime
    last_seen_at: datetime | None = None
