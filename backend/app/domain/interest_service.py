from __future__ import annotations

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.interest import Interest, UserInterest
from app.models.user import User

logger = logging.getLogger(__name__)


def _slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "interest"


def list_interests(db: Session, category: str | None = None) -> list[Interest]:
    stmt = select(Interest).order_by(Interest.category, Interest.label)
    if category:
        stmt = stmt.where(Interest.category == category)
    return list(db.execute(stmt).scalars().all())


def get_interest(db: Session, interest_id: int) -> Interest | None:
    return db.get(Interest, interest_id)


def create_free_text_interest(db: Session, label: str, category: str = "topic") -> Interest:
    slug = _slugify(label)
    existing = db.execute(select(Interest).where(Interest.slug == slug)).scalar_one_or_none()
    if existing:
        return existing
    interest = Interest(label=label.strip(), slug=slug, category=category, is_predefined=False)
    db.add(interest)
    db.commit()
    db.refresh(interest)
    return interest


def set_user_interests(
    db: Session, user_id: int, interest_ids: list[int], blurb: str | None = None
) -> list[UserInterest]:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("user not found")
    # Refuse to wipe existing rows when the caller sent a non-empty payload
    # whose ids all reference missing interests — otherwise a stale/garbage
    # payload silently deletes the user's whole interest profile.
    valid_ids: list[int] = []
    for iid in interest_ids:
        if db.get(Interest, iid):
            valid_ids.append(iid)
    if interest_ids and not valid_ids:
        raise LookupError("no valid interest_ids in payload")
    db.execute(delete(UserInterest).where(UserInterest.user_id == user_id))
    rows: list[UserInterest] = [
        UserInterest(user_id=user_id, interest_id=iid, source="self") for iid in valid_ids
    ]
    db.add_all(rows)
    if blurb is not None:
        user.blurb = blurb
    db.commit()
    # Refresh the user's sqlite-vec row synchronously so recommendations pick
    # up the new interest set on the next call. Without this the vec_user_profile
    # blob stays stale until someone manually POSTs /ai/embed/user/{id}.
    # Kept best-effort so a broken embedder never fails an interest save.
    try:
        from app.workers import embeddings as _emb_worker

        _emb_worker.embed_user_profile(db, user_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("embed_user_profile after set_user_interests failed: %s", exc)
    return rows


def get_user_interests(db: Session, user_id: int) -> list[tuple[UserInterest, Interest]]:
    stmt = (
        select(UserInterest, Interest)
        .join(Interest, Interest.id == UserInterest.interest_id)
        .where(UserInterest.user_id == user_id)
        .order_by(Interest.category, Interest.label)
    )
    return [(ui, i) for ui, i in db.execute(stmt).all()]


def upsert_predefined(db: Session, items: list[dict]) -> int:
    """Seed helper. items = [{label, slug?, category}]. Returns rows inserted."""
    added = 0
    for item in items:
        label = item["label"].strip()
        slug = item.get("slug") or _slugify(label)
        existing = db.execute(select(Interest).where(Interest.slug == slug)).scalar_one_or_none()
        if existing:
            continue
        db.add(Interest(label=label, slug=slug, category=item.get("category", "topic"), is_predefined=True))
        added += 1
    db.commit()
    return added
