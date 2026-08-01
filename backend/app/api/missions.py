from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.domain import mission_service
from app.infra.db import get_db
from app.schemas.mission import MissionCreate, MissionRead

router = APIRouter(prefix="/missions", tags=["missions"])


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_mission(payload: MissionCreate, db: Session = Depends(get_db)) -> MissionRead:
    m = mission_service.create_mission(db, payload)
    return MissionRead.model_validate(mission_service.mission_to_dict(m))


@router.get("", response_model=list[MissionRead])
def list_missions(db: Session = Depends(get_db)) -> list[MissionRead]:
    return [MissionRead.model_validate(mission_service.mission_to_dict(m)) for m in mission_service.list_missions(db)]


@router.get("/me")
def my_missions(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[dict]:
    rows = mission_service.list_user_progress(db, user_id)
    out: list[dict] = []
    for m, p in rows:
        progress = json.loads(p.progress) if p and p.progress else None
        out.append(
            {
                "mission": mission_service.mission_to_dict(m),
                "progress": progress,
                "completed_at": p.completed_at if p else None,
                "points_awarded": p.points_awarded if p else 0,
            }
        )
    return out
