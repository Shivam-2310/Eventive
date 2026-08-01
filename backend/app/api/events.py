from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domain import event_service
from app.domain.ai.router import event_vibe
from app.infra.db import get_db
from app.schemas.event import (
    EventCreate,
    EventInteractionCreate,
    EventInterestAssign,
    EventReaction,
    EventRead,
    EventSpeakerAssign,
    EventUpdate,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventRead:
    ev = event_service.create_event(db, payload)
    return EventRead.model_validate(event_service.hydrate_event(db, ev))


@router.get("", response_model=list[EventRead])
def list_events(
    status: str | None = None,
    track: str | None = None,
    day: date | None = None,
    speaker_id: int | None = None,
    interest_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[EventRead]:
    rows = event_service.list_events(
        db, status=status, track=track, day=day, speaker_id=speaker_id, interest_id=interest_id, limit=limit, offset=offset
    )
    return [EventRead.model_validate(event_service.hydrate_event(db, e)) for e in rows]


@router.get("/discover")
def discover(
    user_id: int = Query(..., description="explicit user_id until Phase 14"),
    cursor: int | None = None,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
) -> dict:
    cards, next_cursor = event_service.discover_cards(db, user_id=user_id, cursor=cursor, limit=limit)
    return {
        "cards": [c.model_dump() for c in cards],
        "next_cursor": next_cursor,
    }


@router.get("/discover/for-you")
def discover_for_you(
    user_id: int = Query(..., description="explicit user_id until Phase 14"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Interest-first discovery deck.

    Same card shape as ``/events/discover`` so the frontend can render either
    surface with the identical widget; only the *ordering* changes. Returns no
    cursor because the underlying score has no natural stable ordering across
    pages — the frontend either shows the top-N or re-requests with a bigger
    limit.
    """
    cards = event_service.for_you_cards(db, user_id=user_id, limit=limit)
    return {"cards": [c.model_dump() for c in cards], "next_cursor": None}


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventRead:
    ev = event_service.get_event(db, event_id)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return EventRead.model_validate(event_service.hydrate_event(db, ev))


@router.patch("/{event_id}", response_model=EventRead)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)) -> EventRead:
    ev = event_service.update_event(db, event_id, payload)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return EventRead.model_validate(event_service.hydrate_event(db, ev))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)) -> None:
    ok = event_service.delete_event(db, event_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")


@router.post("/{event_id}/speakers")
def add_event_speaker(event_id: int, payload: EventSpeakerAssign, db: Session = Depends(get_db)) -> dict:
    if not event_service.get_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    row = event_service.assign_speaker(db, event_id, payload.speaker_id, payload.role)
    return {"event_id": row.event_id, "speaker_id": row.speaker_id, "role": row.role}


@router.post("/{event_id}/interests")
def add_event_interests(event_id: int, payload: EventInterestAssign, db: Session = Depends(get_db)) -> dict:
    if not event_service.get_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    added = event_service.assign_interests(db, event_id, payload)
    return {"event_id": event_id, "added": added}


@router.post("/{event_id}/react")
def react_to_event_card(
    event_id: int,
    payload: EventReaction,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if not event_service.get_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    try:
        row = event_service.react_to_prompt(db, user_id, event_id, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": row.id, "reaction": row.reaction}


@router.post("/{event_id}/interactions")
def create_event_interaction(
    event_id: int,
    payload: EventInteractionCreate,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if not event_service.get_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    try:
        row = event_service.record_interaction(db, user_id, event_id, payload.type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # touch missions asynchronously (no-op on failure)
    try:
        from app.domain import mission_service

        mission_service.recompute(db, user_id)
    except Exception:
        pass
    return {"id": row.id, "type": row.type, "event_id": event_id, "active": True}


@router.delete("/{event_id}/interactions")
def delete_event_interaction(
    event_id: int,
    type: str = Query(..., description="Interaction type to remove"),
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Toggle-off endpoint for event interactions.

    Returns ``active=False`` regardless of whether a row actually existed so
    the client can call it optimistically without extra guards.
    """
    if not event_service.get_event(db, event_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    try:
        removed = event_service.remove_interaction(db, user_id, event_id, type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"event_id": event_id, "type": type, "removed": removed, "active": False}


@router.post("/{event_id}/vibe/refresh")
def refresh_vibe(event_id: int, db: Session = Depends(get_db)) -> dict:
    text = event_vibe(db, event_id)
    if text is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return {"event_id": event_id, "vibe": text}
