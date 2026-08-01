from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


def _embed_user_profile_safe(db: Session, user_id: int) -> None:
    """Best-effort refresh of the user's sqlite-vec row.

    Always used at write points (create/update) so recommendations never see a
    user without a vector. Failures are swallowed to keep the primary op green.
    """
    try:
        from app.workers import embeddings as _emb_worker

        _emb_worker.embed_user_profile(db, user_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("embed_user_profile(%s) failed: %s", user_id, exc)


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    _embed_user_profile_safe(db, user.id)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def list_users(db: Session, limit: int = 100, offset: int = 0) -> list[User]:
    stmt = select(User).order_by(User.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def update_user(db: Session, user_id: int, payload: UserUpdate) -> User | None:
    user = db.get(User, user_id)
    if not user:
        return None
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> bool:
    user = db.get(User, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


def touch_last_seen(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if user:
        user.last_seen_at = datetime.utcnow()
        db.commit()
