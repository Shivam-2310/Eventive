"""Bulk demo seed: 30 users, avatars, interests, reels, interactions, connections, threads.

Idempotent — if the target user cohort already exists (matched by email), the script
short-circuits and only backfills whatever piece is missing (reels / interactions /
connections). Safe to re-run.

Usage (host):
    cd backend
    uv run python -m app.scripts.seed_bulk

The base seeder (`seed.py`) must have already populated the interest catalog and
event catalog; if it hasn't, this script runs it first.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import interest_service, user_service
from app.infra.db import SessionLocal, ensure_schema
from app.infra.security import hash_password
from app.models.chat import ChatThread, ChatThreadParticipant, Message
from app.models.event import Event
from app.models.interaction import EventCardReaction, EventInteraction
from app.models.interest import Interest
from app.models.networking import Connection
from app.models.notification import Notification
from app.models.reel import Reel, ReelInteraction
from app.models.user import User
from app.schemas.user import UserCreate
from app.scripts import seed as base_seed
from app.workers import embeddings as emb_worker

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "flo1234"

# 30 hand-crafted demo profiles. Anyone with `has_avatar=True` gets a stable pravatar
# image keyed off their email so the same photo appears on every reload.
USER_PROFILES: list[dict] = [
    dict(email="maya.iyer@flo.dev", name="Maya Iyer", role="ML Engineer", company="Kaleido AI",
         headline="Evals + RLHF + coffee.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["GenAI", "RAG", "Model Evaluation", "Python", "PyTorch"],
         blurb="Building eval harnesses for RAG at Kaleido. Ex-Google Brain."),
    dict(email="dev.sharma@flo.dev", name="Dev Sharma", role="Founder", company="Sift Labs",
         headline="Founder / building agents for legal ops.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Agents", "GenAI", "Founder", "Prompt Engineering", "TypeScript"],
         blurb="0→1 founder. Second attempt. Looking for a technical cofounder."),
    dict(email="riya.patel@flo.dev", name="Riya Patel", role="Backend Engineer", company="Numera",
         headline="Turning Postgres into a vector DB, one CTE at a time.", timezone="Asia/Kolkata",
         has_avatar=True,
         interests=["Vector Search", "Postgres", "Python", "FastAPI", "Backend Engineer"],
         blurb="pgvector nerd. Happy to talk indexing tricks."),
    dict(email="arjun.k@flo.dev", name="Arjun Krishnan", role="Researcher", company="IISc",
         headline="PhD candidate. Interpretability + safety.", timezone="Asia/Kolkata",
         has_avatar=False,
         interests=["AI Safety", "AI Ethics", "Model Evaluation", "Researcher"],
         blurb="Currently poking holes in aligned models."),
    dict(email="ananya.rao@flo.dev", name="Ananya Rao", role="Product Manager", company="Flip",
         headline="PM on the AI copilot. Ex-Zomato.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Product Manager", "GenAI", "Developer Tools"],
         blurb="If you've thought about pricing your AI feature, we should talk."),
    dict(email="karthik.n@flo.dev", name="Karthik Nair", role="ML Engineer", company="Poser",
         headline="Serving 3B params on a Jetson.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Edge AI", "PyTorch", "MLOps", "Rust", "Observability"],
         blurb="Edge inference + quantization + custom kernels."),
    dict(email="priya.s@flo.dev", name="Priya Shetty", role="Frontend Engineer", company="Flip",
         headline="Design systems + React. Loves motion.", timezone="Asia/Kolkata",
         has_avatar=True,
         interests=["Frontend Engineer", "React", "Next.js", "TypeScript"],
         blurb="Currently shipping AI-first UX at Flip."),
    dict(email="rahul.g@flo.dev", name="Rahul Gupta", role="Backend Engineer", company="Zerodha",
         headline="Distributed systems @ Zerodha.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Distributed Systems", "Go", "Kafka", "Redis", "Backend Engineer"],
         blurb="Building the streaming layer for a trading platform."),
    dict(email="sneha.d@flo.dev", name="Sneha Deshpande", role="Researcher", company="Microsoft Research",
         headline="Multimodal foundation models.", timezone="Asia/Kolkata", has_avatar=False,
         interests=["Multimodal AI", "Researcher", "PyTorch", "GenAI"],
         blurb="Vision + language + audio. Recent EMNLP paper on grounded reasoning."),
    dict(email="aditya.j@flo.dev", name="Aditya Joshi", role="Founder", company="Grain",
         headline="AI voice agents for D2C support.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Founder", "Agents", "GenAI", "Prompt Engineering"],
         blurb="Series A. Hiring 2 backend engineers."),
    dict(email="pooja.m@flo.dev", name="Pooja Menon", role="ML Engineer", company="Freshworks",
         headline="Recsys + embeddings.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Vector Search", "GenAI", "MLOps", "Python"],
         blurb="Personalization for 60M+ customer records."),
    dict(email="vikram.b@flo.dev", name="Vikram Balaji", role="Backend Engineer", company="Razorpay",
         headline="Payments infra. Rust + Go.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Rust", "Go", "Distributed Systems", "Backend Engineer", "Observability"],
         blurb="Rebuilding payment orchestration in Rust."),
    dict(email="neha.t@flo.dev", name="Neha Tiwari", role="Product Manager", company="Cred",
         headline="PM. Loves 0→1.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Product Manager", "Fintech", "Developer Tools"],
         blurb="Currently thinking about AI in credit underwriting."),
    dict(email="siddharth.p@flo.dev", name="Siddharth Prakash", role="ML Engineer", company="Sarvam AI",
         headline="Working on Indic LLMs.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["GenAI", "PyTorch", "Multimodal AI", "Python"],
         blurb="Tokenizers for Indic scripts + eval sets."),
    dict(email="anushka.v@flo.dev", name="Anushka Venkat", role="Backend Engineer", company="Ola",
         headline="Realtime systems @ Ola.", timezone="Asia/Kolkata", has_avatar=False,
         interests=["Backend Engineer", "Kafka", "Redis", "Distributed Systems"],
         blurb="Sub-100ms driver dispatch. Ask me about geosharding."),
    dict(email="rohan.a@flo.dev", name="Rohan Agarwal", role="Founder", company="Vector Health",
         headline="AI for radiologists.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Founder", "Healthcare AI", "PyTorch", "GenAI"],
         blurb="MedTech. Regulatory + clinical validation is our moat."),
    dict(email="tanvi.b@flo.dev", name="Tanvi Bhat", role="Frontend Engineer", company="Freshworks",
         headline="UX for internal tools.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Frontend Engineer", "React", "TypeScript"],
         blurb="If your admin panel makes you cry, I want to help."),
    dict(email="harsh.v@flo.dev", name="Harsh Vora", role="ML Engineer", company="Airbnb",
         headline="Search ranking @ Airbnb.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Vector Search", "MLOps", "Python", "GenAI"],
         blurb="Semantic search at planet scale."),
    dict(email="mihika.p@flo.dev", name="Mihika Pillai", role="Researcher", company="IIT Bombay",
         headline="LLM+robotics.", timezone="Asia/Kolkata", has_avatar=False,
         interests=["Robotics", "Researcher", "PyTorch", "Multimodal AI"],
         blurb="Grasping tasks conditioned on natural language."),
    dict(email="varun.s@flo.dev", name="Varun Suri", role="Backend Engineer", company="Postman",
         headline="Devtools for APIs.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Developer Tools", "Backend Engineer", "TypeScript", "Docker"],
         blurb="I like tools that make bad APIs testable."),
    dict(email="ishani.k@flo.dev", name="Ishani Kapoor", role="Frontend Engineer", company="Notion",
         headline="Slash commands, blocks, and joy.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Frontend Engineer", "React", "TypeScript", "Next.js"],
         blurb="Ex-Figma. Loves editors."),
    dict(email="aakash.r@flo.dev", name="Aakash Ramesh", role="Founder", company="Ledgerly",
         headline="Fintech founder. LLMs on ledger.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Founder", "Fintech", "GenAI", "Agents"],
         blurb="Bookkeeping for SMBs — but the LLM does the work."),
    dict(email="devika.j@flo.dev", name="Devika Jain", role="ML Engineer", company="Turing",
         headline="Coding agents.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Agents", "GenAI", "Python", "Developer Tools"],
         blurb="Fine-tuning code models on real PR history."),
    dict(email="nikhil.b@flo.dev", name="Nikhil Bansal", role="Backend Engineer", company="Uber",
         headline="Streaming + Kafka + Rust.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Kafka", "Rust", "Distributed Systems", "Backend Engineer"],
         blurb="Currently reading the Aeron paper for the third time."),
    dict(email="riya.v@flo.dev", name="Riya Verma", role="Product Manager", company="Ather Energy",
         headline="Battery + software.", timezone="Asia/Kolkata", has_avatar=False,
         interests=["Product Manager", "Climate Tech", "Developer Tools"],
         blurb="Turning bikes into rolling APIs."),
    dict(email="karan.a@flo.dev", name="Karan Ahluwalia", role="ML Engineer", company="Ola Krutrim",
         headline="Pretraining engineer.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["GenAI", "PyTorch", "Distributed Systems", "MLOps"],
         blurb="Data pipelines and DPO tuning."),
    dict(email="preeti.d@flo.dev", name="Preeti Desai", role="Frontend Engineer", company="Zeta",
         headline="Design systems + accessibility.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Frontend Engineer", "React", "TypeScript"],
         blurb="Colour contrast police. Sorry (not sorry)."),
    dict(email="samar.k@flo.dev", name="Samar Khanna", role="Founder", company="Curriculum.ai",
         headline="AI for K-12 teachers.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Founder", "Education", "GenAI", "Agents"],
         blurb="Teacher-in-the-loop lesson planning."),
    dict(email="tara.m@flo.dev", name="Tara Mishra", role="Researcher", company="AI4Bharat",
         headline="Low-resource NLP.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["Researcher", "Multimodal AI", "GenAI", "AI Ethics"],
         blurb="Multi-lingual eval benchmarks for Indian languages."),
    dict(email="ayaan.j@flo.dev", name="Ayaan Jaffer", role="ML Engineer", company="Meesho",
         headline="Ranking + recommendations.", timezone="Asia/Kolkata", has_avatar=True,
         interests=["MLOps", "Vector Search", "Python", "GenAI"],
         blurb="Cold-start recs for a 100M+ user marketplace."),
]

# 8 reels distributed across the first ~8 profiles.
# Each row is (profile_idx, caption, video_url, thumbnail_url).
# Videos are Google's public GCS "gtv-videos-bucket" samples — permissive CORS,
# no auth, hosted for the last decade, so we don't have to ship binaries in git
# or run a download step during seeding.
_GCS = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample"

REEL_ROWS: list[tuple[int, str, str, str | None]] = [
    (0, "3 questions that broke my RAG eval loop this week.",
     f"{_GCS}/BigBuckBunny.mp4",         f"{_GCS}/images/BigBuckBunny.jpg"),
    (1, "How we went from prompt-chaining to a real agent graph in one sprint.",
     f"{_GCS}/ElephantsDream.mp4",       f"{_GCS}/images/ElephantsDream.jpg"),
    (2, "Turning Postgres into a working vector store — under 200 lines.",
     f"{_GCS}/ForBiggerBlazes.mp4",      f"{_GCS}/images/ForBiggerBlazes.jpg"),
    (4, "Why our AI copilot rollout stalled and what we changed.",
     f"{_GCS}/ForBiggerEscapes.mp4",     f"{_GCS}/images/ForBiggerEscapes.jpg"),
    (5, "Live: Whisper.cpp running on a Jetson Nano.",
     f"{_GCS}/ForBiggerFun.mp4",         f"{_GCS}/images/ForBiggerFun.jpg"),
    (9, "60s pitch: AI voice agent for D2C support.",
     f"{_GCS}/ForBiggerJoyrides.mp4",    f"{_GCS}/images/ForBiggerJoyrides.jpg"),
    (10, "Speedrun: production-grade embedding pipeline in FastAPI.",
     f"{_GCS}/ForBiggerMeltdowns.mp4",   f"{_GCS}/images/ForBiggerMeltdowns.jpg"),
    (13, "Sarvam-1 vs Llama-3 8B on Marathi — surprising results.",
     f"{_GCS}/Sintel.mp4",               f"{_GCS}/images/Sintel.jpg"),
]


def seed_bulk(seed: int = 42) -> dict[str, int]:
    """Idempotent. Runs the base seeder first, then layers bulk demo data on top."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Guarantee the interest catalog / event catalog / admin all exist first.
    base_seed.seed_all()

    ensure_schema()
    db = SessionLocal()
    stats: dict[str, int] = {}
    try:
        rng = random.Random(seed)
        stats["users_new"] = _seed_users(db)
        stats["interests_assigned"] = _seed_user_interests(db)
        stats["reels_new"] = _seed_reels(db, rng)
        stats["event_interactions"] = _seed_event_interactions(db, rng)
        stats["card_reactions"] = _seed_card_reactions(db, rng)
        stats["reel_interactions"] = _seed_reel_interactions(db, rng)
        stats["connections"] = _seed_connections(db, rng)
        stats["messages"] = _seed_messages(db, rng)
        stats["notifications"] = _seed_notifications(db, rng)

        try:
            emb = emb_worker.backfill_all(db)
            stats["embeddings_users"] = int(emb.get("users", 0))
            stats["embeddings_events"] = int(emb.get("events", 0))
        except Exception as exc:
            logger.warning("embeddings backfill on bulk seed failed: %s", exc)
    finally:
        db.close()

    return stats


def _seed_users(db: Session) -> int:
    """Create the 30 demo users. Skips any email that already exists."""
    added = 0
    for profile in USER_PROFILES:
        existing = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if existing:
            continue
        avatar_url = (
            f"https://i.pravatar.cc/300?u={profile['email']}"
            if profile.get("has_avatar")
            else None
        )
        user = user_service.create_user(
            db,
            UserCreate(
                email=profile["email"],
                name=profile["name"],
                role=profile.get("role"),
                company=profile.get("company"),
                headline=profile.get("headline"),
                timezone=profile.get("timezone", "Asia/Kolkata"),
                blurb=profile.get("blurb"),
                avatar_url=avatar_url,
            ),
        )
        user.password_hash = hash_password(DEMO_PASSWORD)
        added += 1
    db.commit()
    return added


def _seed_user_interests(db: Session) -> int:
    """Attach interests to every demo user (skip if they already have any)."""
    labels_to_id = {
        row.label: row.id
        for row in db.execute(select(Interest)).scalars().all()
    }
    attached = 0
    for profile in USER_PROFILES:
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        ids = [labels_to_id[lbl] for lbl in profile["interests"] if lbl in labels_to_id]
        if not ids:
            continue
        interest_service.set_user_interests(
            db, user.id, ids, blurb=profile.get("blurb")
        )
        attached += 1
    return attached


def _seed_reels(db: Session, rng: random.Random) -> int:
    """Create/repair 8 seed reels distributed across a subset of demo users.

    We point `video_url` at Google's public gtv-videos-bucket samples so the
    frontend can actually play them. `storage_key` is left None so the API's
    `refresh_signed_urls` doesn't overwrite our direct URL with a signed local
    blob URL.

    Idempotent — if the reel already exists for (user, caption) we still repair
    its video_url/thumbnail_url in case a previous run stored a broken
    placeholder blob.
    """
    added_or_repaired = 0
    for profile_idx, caption, video_url, thumb_url in REEL_ROWS:
        profile = USER_PROFILES[profile_idx]
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        existing = db.execute(
            select(Reel).where(Reel.user_id == user.id, Reel.caption == caption)
        ).scalar_one_or_none()
        if existing:
            # Repair any old placeholder rows in place.
            needs_fix = (
                existing.video_url != video_url
                or existing.thumbnail_url != thumb_url
                or existing.storage_key is not None
            )
            if needs_fix:
                existing.video_url = video_url
                existing.thumbnail_url = thumb_url
                existing.storage_key = None
                existing.thumbnail_key = None
                existing.status = "ready"
                added_or_repaired += 1
            continue
        reel = Reel(
            user_id=user.id,
            caption=caption,
            video_url=video_url,
            thumbnail_url=thumb_url,
            storage_key=None,
            status="ready",
            duration_seconds=round(rng.uniform(6.5, 10.0), 2),
        )
        db.add(reel)
        added_or_repaired += 1
    db.commit()
    return added_or_repaired


def _seed_event_interactions(db: Session, rng: random.Random) -> int:
    """Each demo user likes/saves/attends 3-6 events. Skips if user already has any."""
    events = db.execute(select(Event.id).order_by(Event.id)).scalars().all()
    if not events:
        return 0
    types = ["like", "save", "add_to_my_day", "mark_attended", "rsvp"]
    weights = [0.45, 0.20, 0.15, 0.10, 0.10]
    added = 0
    for profile in USER_PROFILES:
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        already = db.execute(
            select(func.count(EventInteraction.id)).where(EventInteraction.user_id == user.id)
        ).scalar() or 0
        if already:
            continue
        picked = rng.sample(list(events), k=min(len(events), rng.randint(3, 6)))
        for event_id in picked:
            interaction_type = rng.choices(types, weights=weights, k=1)[0]
            db.add(EventInteraction(user_id=user.id, event_id=event_id, type=interaction_type))
            added += 1
    db.commit()
    return added


def _seed_card_reactions(db: Session, rng: random.Random) -> int:
    """Add prompt-card reactions so /events/discover shows like counts + already_liked flags."""
    events = db.execute(select(Event.id).order_by(Event.id).limit(15)).scalars().all()
    if not events:
        return 0
    prompt_types = ["cover", "speaker", "topic", "when_where", "vibe", "who_is_going"]
    added = 0
    for profile in USER_PROFILES:
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        for event_id in rng.sample(list(events), k=min(len(events), rng.randint(2, 4))):
            prompt = rng.choice(prompt_types)
            exists = db.execute(
                select(EventCardReaction.id).where(
                    EventCardReaction.user_id == user.id,
                    EventCardReaction.event_id == event_id,
                    EventCardReaction.prompt_type == prompt,
                    EventCardReaction.prompt_ref_id.is_(None),
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(
                EventCardReaction(
                    user_id=user.id,
                    event_id=event_id,
                    prompt_type=prompt,
                    prompt_ref_id=None,
                    reaction=rng.choices(["like", "pass"], weights=[0.75, 0.25], k=1)[0],
                )
            )
            added += 1
    db.commit()
    return added


def _seed_reel_interactions(db: Session, rng: random.Random) -> int:
    """Everyone views + occasionally likes/saves each reel — makes the feed feel real."""
    reels = db.execute(select(Reel.id, Reel.user_id).order_by(Reel.id)).all()
    if not reels:
        return 0
    added = 0
    for profile in USER_PROFILES:
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        for reel_id, author_id in reels:
            if author_id == user.id:
                continue
            already = db.execute(
                select(func.count(ReelInteraction.id)).where(
                    ReelInteraction.user_id == user.id,
                    ReelInteraction.reel_id == reel_id,
                )
            ).scalar() or 0
            if already:
                continue
            db.add(ReelInteraction(
                user_id=user.id, reel_id=reel_id, type="view",
                watch_ms=rng.randint(1500, 9500),
            ))
            added += 1
            if rng.random() < 0.35:
                db.add(ReelInteraction(user_id=user.id, reel_id=reel_id, type="like", watch_ms=None))
                added += 1
            if rng.random() < 0.15:
                db.add(ReelInteraction(user_id=user.id, reel_id=reel_id, type="save", watch_ms=None))
                added += 1
    db.commit()
    return added


def _seed_connections(db: Session, rng: random.Random) -> int:
    """Wire up a small network: ~50 connection edges across the demo users, mostly accepted.

    Includes alice/bob/carol (the pre-existing demo users from base_seed) so that
    whichever account you log in as has a populated Flonnect + Threads experience.
    """
    demo_emails = [p["email"] for p in USER_PROFILES] + [
        "alice@flo.dev", "bob@flo.dev", "carol@flo.dev",
    ]
    users = list(db.execute(
        select(User).where(User.email.in_(demo_emails))
    ).scalars().all())
    if len(users) < 5:
        return 0
    # Seed our local dedupe set with what's already in the DB so re-runs don't
    # try to insert a pair that already exists (the unique constraint is on the
    # ordered pair (requester_id, receiver_id), but connections are logically
    # undirected — dedupe on the unordered pair).
    seen_pairs: set[frozenset[int]] = set()
    user_ids = {u.id for u in users}
    existing = db.execute(
        select(Connection.requester_id, Connection.receiver_id).where(
            Connection.requester_id.in_(user_ids) | Connection.receiver_id.in_(user_ids)
        )
    ).all()
    for req_id, recv_id in existing:
        seen_pairs.add(frozenset({req_id, recv_id}))

    def _count_for(uid: int) -> int:
        return sum(1 for p in seen_pairs if uid in p)

    added = 0
    priority_emails = ["alice@flo.dev", "bob@flo.dev", "carol@flo.dev"]
    priority_users = [u for u in users if u.email in priority_emails]
    others = [u for u in users if u.email not in priority_emails]
    # Step 1: guarantee each priority user has >=5 connections.
    for pu in priority_users:
        need = max(0, 5 - _count_for(pu.id))
        pool = list(others)
        rng.shuffle(pool)
        for other in pool:
            if need == 0:
                break
            pair = frozenset({pu.id, other.id})
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            db.add(Connection(
                requester_id=other.id, receiver_id=pu.id,
                status=rng.choices(["accepted", "accepted", "pending"], k=1)[0],
            ))
            added += 1
            need -= 1

    # Step 2: top up to target_total edges among the whole demo cohort.
    target_total = min(80, len(users) * 3)
    max_attempts = target_total * 8
    attempts = 0
    while len(seen_pairs) < target_total and attempts < max_attempts:
        attempts += 1
        a, b = rng.sample(users, 2)
        pair = frozenset({a.id, b.id})
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        status = rng.choices(
            ["accepted", "accepted", "accepted", "pending", "declined"],
            k=1,
        )[0]
        db.add(Connection(requester_id=a.id, receiver_id=b.id, status=status))
        added += 1
    db.commit()
    return added


def _seed_messages(db: Session, rng: random.Random) -> int:
    """Create threads for accepted connections + drop 1-4 messages per thread."""
    demo_emails = [p["email"] for p in USER_PROFILES] + [
        "alice@flo.dev", "bob@flo.dev", "carol@flo.dev",
    ]
    demo_ids = {u.id for u in db.execute(
        select(User).where(User.email.in_(demo_emails))
    ).scalars().all()}
    if not demo_ids:
        return 0
    accepted = db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            Connection.requester_id.in_(demo_ids),
            Connection.receiver_id.in_(demo_ids),
        )
    ).scalars().all()
    added = 0
    sample_lines = [
        "hey! saw we both care about {topic}. what talks are you eyeing?",
        "if you're around at lunch, keen to chat — I'm at the {topic} track.",
        "nice — I'm here mostly for {topic}. what brought you?",
        "yep saving it. lemme know if you want to hit that {topic} panel together.",
        "quick one — have you seen anything good in {topic} today?",
        "definitely. ping me when you're free after the {topic} session.",
    ]
    topic_pool = ["RAG", "agents", "safety", "MLOps", "startups", "eval", "search"]
    for conn in accepted:
        thread = db.execute(
            select(ChatThread).where(ChatThread.connection_id == conn.id)
        ).scalar_one_or_none()
        if not thread:
            title_a = db.get(User, conn.requester_id)
            title_b = db.get(User, conn.receiver_id)
            thread = ChatThread(
                connection_id=conn.id,
                title=f"{title_a.name if title_a else 'A'} · {title_b.name if title_b else 'B'}",
            )
            db.add(thread)
            db.flush()
            db.add_all([
                ChatThreadParticipant(thread_id=thread.id, user_id=conn.requester_id),
                ChatThreadParticipant(thread_id=thread.id, user_id=conn.receiver_id),
            ])
            db.flush()
        already = db.execute(
            select(func.count(Message.id)).where(Message.thread_id == thread.id)
        ).scalar() or 0
        if already:
            continue
        n_msgs = rng.randint(2, 5)
        turn = 0
        base_time = datetime.utcnow() - timedelta(hours=rng.randint(1, 48))
        for i in range(n_msgs):
            sender = conn.requester_id if turn % 2 == 0 else conn.receiver_id
            topic = rng.choice(topic_pool)
            body = rng.choice(sample_lines).format(topic=topic)
            m = Message(
                thread_id=thread.id,
                sender_id=sender,
                body=body,
                kind="text",
            )
            m.created_at = base_time + timedelta(minutes=15 * i)
            db.add(m)
            turn += 1
            added += 1
    db.commit()
    return added


def _seed_notifications(db: Session, rng: random.Random) -> int:
    """One welcome notification per new user + a handful of "someone connected with you"."""
    added = 0
    for profile in USER_PROFILES:
        user = db.execute(
            select(User).where(User.email == profile["email"])
        ).scalar_one_or_none()
        if not user:
            continue
        already = db.execute(
            select(func.count(Notification.id)).where(Notification.user_id == user.id)
        ).scalar() or 0
        if already:
            continue
        db.add(Notification(
            user_id=user.id,
            type="welcome",
            title="Welcome to Flo",
            body=f"Hey {user.name.split()[0]} — pick 3 sessions to build your Day 1.",
            deep_link="/events/discover",
        ))
        added += 1
        if rng.random() < 0.6:
            db.add(Notification(
                user_id=user.id,
                type="recommendation",
                title="Someone you should meet",
                body="Based on your interests, we found 3 attendees you'd probably enjoy.",
                deep_link="/network/recommendations",
            ))
            added += 1
    db.commit()
    return added


def main() -> None:
    stats = seed_bulk()
    logger.info("bulk seed complete: %s", stats)
    print("bulk seed complete:", stats)


if __name__ == "__main__":
    main()
