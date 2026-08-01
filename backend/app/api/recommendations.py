from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domain import matching_service
from app.infra.db import get_db

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/people/{user_id}")
def recommend_people(user_id: int, limit: int = Query(20, le=50), db: Session = Depends(get_db)) -> list[dict]:
    return matching_service.recommend_people(db, user_id=user_id, k=limit)


@router.post("/people/{user_id}/refresh")
def refresh_people(user_id: int, db: Session = Depends(get_db)) -> dict:
    rows = matching_service.recommend_people(db, user_id=user_id, k=20)
    return {"generated": len(rows)}


@router.get("/events/{user_id}")
def recommend_events(user_id: int, limit: int = Query(10, le=50), db: Session = Depends(get_db)) -> list[dict]:
    return matching_service.recommend_events(db, user_id=user_id, k=limit)
