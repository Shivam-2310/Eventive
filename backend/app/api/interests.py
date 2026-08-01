from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domain import interest_service
from app.infra.db import get_db
from app.schemas.interest import InterestCreate, InterestRead

router = APIRouter(prefix="/interests", tags=["interests"])


@router.get("", response_model=list[InterestRead])
def list_interests(category: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[InterestRead]:
    return [InterestRead.model_validate(i) for i in interest_service.list_interests(db, category=category)]


@router.post("", response_model=InterestRead, status_code=status.HTTP_201_CREATED)
def create_interest(payload: InterestCreate, db: Session = Depends(get_db)) -> InterestRead:
    row = interest_service.create_free_text_interest(db, payload.label, payload.category)
    return InterestRead.model_validate(row)


@router.get("/{interest_id}", response_model=InterestRead)
def get_interest(interest_id: int, db: Session = Depends(get_db)) -> InterestRead:
    row = interest_service.get_interest(db, interest_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "interest not found")
    return InterestRead.model_validate(row)
