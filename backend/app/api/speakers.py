from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domain import event_service
from app.domain.event_service import _speaker_row_to_dict
from app.infra.db import get_db
from app.schemas.event import SpeakerCreate, SpeakerRead, SpeakerUpdate

router = APIRouter(prefix="/speakers", tags=["speakers"])


@router.post("", response_model=SpeakerRead, status_code=status.HTTP_201_CREATED)
def create_speaker(payload: SpeakerCreate, db: Session = Depends(get_db)) -> dict:
    row = event_service.create_speaker(db, payload)
    return _speaker_row_to_dict(row)


@router.get("", response_model=list[SpeakerRead])
def list_speakers(db: Session = Depends(get_db)) -> list[dict]:
    return [_speaker_row_to_dict(s) for s in event_service.list_speakers(db)]


@router.get("/{speaker_id}", response_model=SpeakerRead)
def get_speaker(speaker_id: int, db: Session = Depends(get_db)) -> dict:
    s = event_service.get_speaker(db, speaker_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "speaker not found")
    return _speaker_row_to_dict(s)


@router.patch("/{speaker_id}", response_model=SpeakerRead)
def update_speaker(speaker_id: int, payload: SpeakerUpdate, db: Session = Depends(get_db)) -> dict:
    s = event_service.update_speaker(db, speaker_id, payload)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "speaker not found")
    return _speaker_row_to_dict(s)


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker(speaker_id: int, db: Session = Depends(get_db)) -> None:
    ok = event_service.delete_speaker(db, speaker_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "speaker not found")
