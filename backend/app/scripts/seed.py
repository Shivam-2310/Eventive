"""Idempotent seeder. Runs on container boot and every `uv run python -m app.scripts.seed`."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sqlalchemy import func, select

from app.domain import (
    admin_service,
    event_service,
    interest_service,
    mission_service,
    reel_service,
    user_service,
)
from app.domain.ingestion.csv_importer import import_events_csv, import_speakers_csv
from app.infra.blob import blob_store
from app.infra.config import get_settings
from app.infra.db import SessionLocal, ensure_schema
from app.infra.security import hash_password
from app.models.event import Event, Speaker
from app.models.interaction import EventCardReaction, EventInteraction
from app.models.interest import Interest
from app.models.mission import Mission
from app.models.networking import Connection
from app.models.notification import Notification
from app.models.reel import Reel
from app.models.user import User
from app.schemas.mission import MissionCreate
from app.schemas.user import UserCreate
from app.workers import embeddings as emb_worker

logger = logging.getLogger(__name__)
SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed"


def seed_all() -> dict[str, int]:
    ensure_schema()
    settings = get_settings()
    db = SessionLocal()
    stats: dict[str, int] = {}
    try:
        stats["admin"] = _seed_admin(db, settings.ADMIN_EMAIL, settings.ADMIN_INITIAL_PASSWORD)
        stats["interests"] = _seed_interests(db)
        stats["speakers"] = _seed_speakers(db)
        stats["events"] = _seed_events(db)
        stats["missions"] = _seed_missions(db)
        stats["reels"] = _seed_reels(db)
        if settings.SEED_DEMO_FIXTURES:
            stats["demo_users"] = _seed_demo(db)
        # Warm up vector + RAG indexes so recommendations / Ask Eventive work out of the box.
        # Uses the currently-configured LLMProvider (stub by default -> free + deterministic).
        try:
            emb_stats = emb_worker.backfill_all(db)
            stats["embeddings_users"] = int(emb_stats.get("users", 0))
            stats["embeddings_events"] = int(emb_stats.get("events", 0))
            stats["embeddings_interests"] = int(emb_stats.get("interests", 0))
            rag_stats = emb_worker.rag_backfill(db)
            stats["rag_chunks"] = int(rag_stats.get("chunks", 0))
        except Exception as exc:  # pragma: no cover - never block boot on embeddings
            logger.warning("embeddings backfill on seed failed: %s", exc)
            stats["embeddings_users"] = 0
            stats["embeddings_events"] = 0
            stats["embeddings_interests"] = 0
            stats["rag_chunks"] = 0
        admin_service.log_admin_action(db, None, "seed_run", payload={"stats": stats})
    finally:
        db.close()
    return stats


def _seed_admin(db, email: str, password: str) -> int:
    if db.execute(select(func.count(User.id))).scalar():
        return 0
    admin = user_service.create_user(
        db,
        UserCreate(email=email, name="Eventive Admin", is_admin=True),
    )
    admin.is_admin = True
    admin.password_hash = hash_password(password)
    db.commit()
    return 1


def _seed_interests(db) -> int:
    if db.execute(select(func.count(Interest.id))).scalar():
        return 0
    path = SEED_DIR / "interests.json"
    if not path.is_file():
        return 0
    items = json.loads(path.read_text(encoding="utf-8"))
    added = interest_service.upsert_predefined(db, items)
    return added


def _seed_speakers(db) -> int:
    if db.execute(select(func.count(Speaker.id))).scalar():
        return 0
    path = SEED_DIR / "speakers.csv"
    if not path.is_file():
        return 0
    stats = import_speakers_csv(db, path.read_bytes())
    return int(stats.get("added", 0))


def _seed_events(db) -> int:
    if db.execute(select(func.count(Event.id))).scalar():
        return 0
    path = SEED_DIR / "events.csv"
    if not path.is_file():
        return 0
    stats = import_events_csv(db, path.read_bytes())
    added = int(stats.get("added", 0))
    _assign_speakers_and_interests(db)
    return added


def _assign_speakers_and_interests(db) -> None:
    # deterministic assignment: hash-based
    speakers = list(db.execute(select(Speaker).order_by(Speaker.id)).scalars().all())
    interests = list(db.execute(select(Interest).order_by(Interest.id)).scalars().all())
    events = list(db.execute(select(Event).order_by(Event.id)).scalars().all())
    if not speakers or not interests or not events:
        return
    for i, ev in enumerate(events):
        # 1-2 speakers per event
        s1 = speakers[i % len(speakers)]
        s2 = speakers[(i * 3 + 7) % len(speakers)]
        event_service.assign_speaker(db, ev.id, s1.id, "keynote" if i % 5 == 0 else "panelist")
        if s2.id != s1.id and i % 2 == 0:
            event_service.assign_speaker(db, ev.id, s2.id, "panelist")
        # 2-3 interests per event
        ids = [interests[(i * 7 + k) % len(interests)].id for k in range(3)]
        event_service.assign_interests(db, ev.id, _fake_interest_assign(ids))


def _fake_interest_assign(ids):  # noqa: ANN001
    from app.schemas.event import EventInterestAssign

    return EventInterestAssign(interest_ids=list(set(ids)))


def _seed_missions(db) -> int:
    if db.execute(select(func.count(Mission.id))).scalar():
        return 0
    missions = [
        MissionCreate(
            title="AI track streak",
            description="Attend 3 sessions on the AI track.",
            rule={"type": "attend_track", "track": "AI", "count": 3},
            points=100,
        ),
        MissionCreate(
            title="Reel enthusiast",
            description="Like 5 community reels.",
            rule={"type": "like_reels", "count": 5},
            points=50,
        ),
        MissionCreate(
            title="Connector",
            description="Make 3 accepted connections.",
            rule={"type": "make_connections", "count": 3},
            points=75,
        ),
        MissionCreate(
            title="Explorer",
            description="Like 5 different events.",
            rule={"type": "like_events", "count": 5},
            points=40,
        ),
    ]
    for m in missions:
        mission_service.create_mission(db, m)
    return len(missions)


def _seed_reels(db) -> int:
    if db.execute(select(func.count(Reel.id))).scalar():
        return 0
    reels_dir = SEED_DIR / "reels"
    if not reels_dir.is_dir():
        return 0
    admin = db.execute(select(User).where(User.is_admin.is_(True)).limit(1)).scalar_one_or_none()
    if not admin:
        return 0
    n = 0
    for f in sorted(reels_dir.glob("*.mp4")):
        key = f"reels/seed_{f.stem}.mp4"
        target = blob_store.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        r = Reel(
            user_id=admin.id,
            caption=f"Seed reel: {f.stem}",
            storage_key=key,
            status="ready",
        )
        db.add(r)
        db.flush()
        reel_service.refresh_signed_urls(r)
        n += 1
    db.commit()
    return n


def _seed_demo(db) -> int:
    from sqlalchemy import select as _sel

    if db.execute(_sel(func.count(User.id))).scalar() > 1:
        return 0
    alice = user_service.create_user(
        db,
        UserCreate(email="alice@eventive.dev", name="Alice", headline="AI Engineer", role="ML Engineer", timezone="UTC"),
    )
    bob = user_service.create_user(
        db,
        UserCreate(email="bob@eventive.dev", name="Bob", headline="Founder in GenAI", role="Founder", timezone="UTC"),
    )
    carol = user_service.create_user(
        db,
        UserCreate(
            email="carol@eventive.dev", name="Carol", headline="Backend + agents", role="Backend Engineer", timezone="UTC"
        ),
    )
    # Give every demo user the same password so the sign-in screen can pick
    # any of them to test the seeded connections / notifications / prompt reactions.
    demo_password = "eventive1234"
    for u in (alice, bob, carol):
        u.password_hash = hash_password(demo_password)
    db.commit()
    labels_for = {
        alice.id: ["GenAI", "RAG", "AI Safety", "Python", "FastAPI"],
        bob.id: ["GenAI", "Agents", "Founder", "Prompt Engineering"],
        carol.id: ["RAG", "Agents", "Backend Engineer", "Vector Search", "SQLite"],
    }
    for uid, labels in labels_for.items():
        ids = [
            row for row, in db.execute(select(Interest.id).where(Interest.label.in_(labels))).all()
        ]
        interest_service.set_user_interests(db, uid, ids, blurb=f"Here to hack on {labels[0]}")
    # a broad set of interactions so wrapped/pulse/recs aren't empty
    first_events = db.execute(select(Event.id).order_by(Event.id).limit(5)).scalars().all()
    for uid in (alice.id, bob.id, carol.id):
        for eid in first_events[:3]:
            db.add(EventInteraction(user_id=uid, event_id=eid, type="like"))
        # each demo user saves + marks-attended a different event so wrapped has variety
        if len(first_events) >= 5:
            db.add(EventInteraction(user_id=uid, event_id=first_events[3], type="save"))
            db.add(EventInteraction(user_id=uid, event_id=first_events[4], type="mark_attended"))
    # card reactions across a couple of prompt types so /events/discover shows already_liked flags
    for uid in (alice.id, bob.id, carol.id):
        for eid in first_events[:2]:
            db.add(
                EventCardReaction(
                    user_id=uid,
                    event_id=eid,
                    prompt_type="speaker",
                    prompt_ref_id=None,
                    reaction="like",
                )
            )
    # connections: alice<->bob accepted, carol<->alice pending (so notifications & recs are non-trivial)
    db.add(Connection(requester_id=alice.id, receiver_id=bob.id, status="accepted"))
    db.add(Connection(requester_id=carol.id, receiver_id=alice.id, status="pending"))
    # welcome notification per demo user so /notifications is non-empty
    for uid in (alice.id, bob.id, carol.id):
        db.add(
            Notification(
                user_id=uid,
                type="welcome",
                title="Welcome to Eventive",
                body="Explore the AI track and swipe on some event cards to get personalized picks.",
                deep_link="/events/discover",
            )
        )
    db.commit()
    return 3


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stats = seed_all()
    logger.info("seed complete: %s", stats)
    print("seed complete:", stats)


if __name__ == "__main__":
    main()
