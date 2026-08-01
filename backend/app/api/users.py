from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domain import user_service
from app.infra.db import get_db
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    if user_service.get_by_email(db, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
    return UserRead.model_validate(user_service.create_user(db, payload))


@router.get("", response_model=list[UserRead])
def list_users(
    limit: int = Query(100, le=500), offset: int = 0, db: Session = Depends(get_db)
) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in user_service.list_users(db, limit=limit, offset=offset)]


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserRead:
    u = user_service.get_user(db, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserRead.model_validate(u)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> UserRead:
    u = user_service.update_user(db, user_id, payload)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserRead.model_validate(u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    ok = user_service.delete_user(db, user_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")


# --- interests ---


@router.put("/{user_id}/interests")
def set_user_interests(
    user_id: int,
    payload: "SetUserInterestsRequest",  # noqa: UP037 - forward ref keeps schema import at bottom
    db: Session = Depends(get_db),
) -> dict:
    from app.domain import interest_service

    try:
        rows = interest_service.set_user_interests(db, user_id, payload.interest_ids, payload.blurb)
    except LookupError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"user_id": user_id, "count": len(rows)}


@router.get("/{user_id}/interests")
def get_user_interests(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    from app.domain import interest_service

    pairs = interest_service.get_user_interests(db, user_id)
    return [
        {
            "interest_id": i.id,
            "label": i.label,
            "category": i.category,
            "weight": ui.weight,
            "source": ui.source,
        }
        for ui, i in pairs
    ]


@router.get("/{user_id}/wrapped")
def get_wrapped(user_id: int, db: Session = Depends(get_db)) -> dict:
    from app.domain import pulse_service

    if not user_service.get_user(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return pulse_service.wrapped(db, user_id)


# --- event interactions (user-scoped reads) -----------------------------


@router.get("/{user_id}/event-interactions")
def get_event_interactions(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Compact `{event_id: [type, ...]}` map for every event the user has
    interacted with. Small enough to fetch on login and cache client-side —
    powers active/selected chip state across every screen.
    """
    from app.domain import event_service

    if not user_service.get_user(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    raw = event_service.user_interaction_map(db, user_id)
    return {"user_id": user_id, "events": {str(k): v for k, v in raw.items()}}


@router.get("/{user_id}/events")
def get_user_events(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Hydrated event lists grouped by interaction bucket.

    Powers the Profile activity sections (Saved / Liked / Upcoming RSVPs /
    My Day / Attended / Calendar). Each key is either a raw interaction type
    from `VALID_INTERACTION_TYPES` or the derived `upcoming_rsvp` bucket.
    """
    from app.domain import event_service

    if not user_service.get_user(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    buckets = event_service.user_events_by_interaction(db, user_id)
    return {"user_id": user_id, "buckets": buckets}


# late import to avoid circular
from app.schemas.interest import SetUserInterestsRequest  # noqa: E402
