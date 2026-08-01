from __future__ import annotations

from pydantic import BaseModel


class AIChatRequest(BaseModel):
    message: str
    session_id: int | None = None


class AISuggestion(BaseModel):
    prompt: str
    intent: str


class RetrievedChunk(BaseModel):
    chunk_id: int
    source_type: str
    source_id: int
    text: str
    distance: float
