from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InterestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    slug: str
    category: str
    is_predefined: bool


class InterestCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    category: str = "topic"


class SetUserInterestsRequest(BaseModel):
    interest_ids: list[int]
    blurb: str | None = None


class UserInterestRead(BaseModel):
    interest_id: int
    label: str
    category: str
    weight: float
    source: str
