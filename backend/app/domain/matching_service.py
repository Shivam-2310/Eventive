from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.ai.llm_provider import get_provider
from app.models.event import Event, EventInterest
from app.models.interaction import EventInteraction
from app.models.interest import Interest, UserInterest
from app.models.networking import Connection, Match
from app.models.user import User
from app.workers.embeddings import nearest


def _shared_interests(db: Session, a: int, b: int) -> list[Interest]:
    a_ids = {
        row for row, in db.execute(select(UserInterest.interest_id).where(UserInterest.user_id == a)).all()
    }
    b_ids = {
        row for row, in db.execute(select(UserInterest.interest_id).where(UserInterest.user_id == b)).all()
    }
    shared = list(a_ids & b_ids)
    if not shared:
        return []
    return list(db.execute(select(Interest).where(Interest.id.in_(shared))).scalars().all())


def _shared_event_count(db: Session, a: int, b: int) -> int:
    a_events = set(
        db.execute(
            select(EventInteraction.event_id).where(
                EventInteraction.user_id == a,
                EventInteraction.type.in_(["like", "save", "rsvp", "mark_attended"]),
            )
        ).scalars().all()
    )
    b_events = set(
        db.execute(
            select(EventInteraction.event_id).where(
                EventInteraction.user_id == b,
                EventInteraction.type.in_(["like", "save", "rsvp", "mark_attended"]),
            )
        ).scalars().all()
    )
    return len(a_events & b_events)


def _existing_connection(db: Session, a: int, b: int) -> Connection | None:
    return db.execute(
        select(Connection).where(
            ((Connection.requester_id == a) & (Connection.receiver_id == b))
            | ((Connection.requester_id == b) & (Connection.receiver_id == a))
        )
    ).scalar_one_or_none()


def recommend_people(db: Session, user_id: int, k: int = 20) -> list[dict[str, Any]]:
    me = db.get(User, user_id)
    if not me:
        return []

    # Interests-first candidate pool: everyone who shares ≥1 interest with me.
    # Vector kNN is used as a *fallback pool* (for users with no interests set
    # yet) and as a distance signal used only for tiebreaking within the
    # interest-sharer pool. This matches the product intent that "cards should
    # be based on interests matching first".
    my_interest_ids: set[int] = {
        int(row) for row, in db.execute(
            select(UserInterest.interest_id).where(UserInterest.user_id == user_id)
        ).all()
    }
    interest_candidates: set[int] = set()
    if my_interest_ids:
        interest_candidates = {
            int(uid) for uid, in db.execute(
                select(UserInterest.user_id).where(
                    UserInterest.interest_id.in_(my_interest_ids),
                    UserInterest.user_id != user_id,
                ).distinct()
            ).all()
        }

    # Pull a wide kNN band so (a) we have distances for the interest sharers
    # we already know about, and (b) users with no interests still get *some*
    # recommendations. `nearest()` excludes the ref key itself.
    knn_rows = nearest(db, "vec_user_profile", "user_id", user_id, k=max(k * 3, 40))
    knn_dist: dict[int, float] = {int(oid): float(d) for oid, d in knn_rows}

    candidate_ids: set[int] = interest_candidates | set(knn_dist)
    provider = get_provider()

    # Pass 1: score every candidate + build rule-based reasons. NO LLM calls here —
    # the free-tier Gemini chat quota is 20 requests/day and calling it 40x per
    # page load will blow it out immediately (and each 429 costs ~1s of latency).
    rows: list[dict[str, Any]] = []
    others_by_id: dict[int, User] = {}
    shared_by_id: dict[int, list[Interest]] = {}
    for other_id in candidate_ids:
        other = db.get(User, other_id)
        if not other or not other.opt_in_networking:
            continue
        conn = _existing_connection(db, user_id, other_id)
        if conn and conn.status in {"accepted", "blocked"}:
            continue
        shared = _shared_interests(db, user_id, other_id)
        # Neutral distance for users only reachable via interest overlap (i.e.
        # not in the top-N kNN band). 1.0 sits at the midpoint of the cosine
        # distance range so vec ranking doesn't punish nor reward them.
        dist = knn_dist.get(other_id, 1.0)
        # Interests-first ranking: shared interests dominate (weight 1.0/tag).
        # Vec similarity is a smaller tiebreaker (weight 0.3). Small bumps for
        # complementary role and same timezone keep the "worth a hello" cases
        # from disappearing when there are only weak interest overlaps.
        rule_score = 1.0 * len(shared) + 0.3 * (1.0 - dist)
        rule_score += 0.05 * _shared_event_count(db, user_id, other_id)
        if me.role and other.role and me.role.lower() != other.role.lower():
            rule_score += 0.05
        if me.timezone and other.timezone and me.timezone == other.timezone:
            rule_score += 0.03
        reasons: list[str] = []
        if shared:
            reasons.append("You share " + ", ".join(i.label for i in shared[:3]))
        if not reasons:
            reasons.append("Similar profile embedding — worth a hello.")
        others_by_id[other_id] = other
        shared_by_id[other_id] = shared
        rows.append(
            {
                "other_user_id": other_id,
                "name": other.name,
                "headline": other.headline,
                "score": round(rule_score, 4),
                "reasons": reasons,
            }
        )

    rows.sort(key=lambda x: x["score"], reverse=True)

    # Pass 2: only decorate the top-3 with an LLM-generated one-liner. Everyone
    # else uses the rule-based reason. Keeps the endpoint fast and the free
    # daily quota alive across many page loads.
    if provider.name == "gemini":
        for row in rows[:3]:
            other = others_by_id[row["other_user_id"]]
            shared = shared_by_id[row["other_user_id"]]
            try:
                llm_line = provider.generate_short_text(
                    f"In one short line, why should {me.name} meet {other.name}? "
                    f"They both care about: {', '.join(i.label for i in shared[:3]) or 'AI'}.",
                    max_words=20,
                )
                if llm_line:
                    row["reasons"] = [row["reasons"][0], llm_line][:2]
            except Exception:
                pass

    for row in rows[:k]:
        _upsert_match(db, user_id, row["other_user_id"], row["score"], row["reasons"])
    return rows[:k]


def recommend_events(db: Session, user_id: int, k: int = 10) -> list[dict[str, Any]]:
    me = db.get(User, user_id)
    if not me:
        return []
    # aggregate candidates: kNN by user profile embedding
    provider = get_provider()
    try:
        from sqlalchemy import text as sql_text

        uvec_row = db.execute(
            sql_text("SELECT embedding FROM vec_user_profile WHERE user_id = :uid"),
            {"uid": user_id},
        ).first()
        if uvec_row is None:
            rows = []
        else:
            rows = db.execute(
                sql_text(
                    "SELECT event_id, distance FROM vec_event WHERE embedding MATCH :v "
                    "AND k = :k ORDER BY distance"
                ),
                {"v": uvec_row[0], "k": max(k * 3, 20)},
            ).all()
    except Exception:
        rows = []

    liked_event_ids = {
        r for r, in db.execute(
            select(EventInteraction.event_id).where(
                EventInteraction.user_id == user_id,
                EventInteraction.type.in_(["like", "save", "rsvp"]),
            )
        ).all()
    }
    now = datetime.utcnow()

    result: list[dict[str, Any]] = []
    for eid, dist in rows:
        eid = int(eid)
        if eid in liked_event_ids:
            continue
        ev = db.get(Event, eid)
        if not ev:
            continue
        if ev.status in {"finished", "canceled"}:
            continue
        rule_score = (1.0 - float(dist))
        if ev.start_time and ev.start_time > now:
            hours = max(0.5, (ev.start_time - now).total_seconds() / 3600.0)
            rule_score += 1.0 / hours  # sooner is better
        # speaker affinity: any speaker in a user's already-liked events?
        rule_score += 0.05 * _speaker_affinity(db, user_id, eid)
        reason = _event_reason(db, provider, me, ev)
        result.append(
            {
                "event_id": eid,
                "title": ev.title,
                "track": ev.track,
                "start_time": ev.start_time,
                "score": round(rule_score, 4),
                "reason": reason,
            }
        )
    result.sort(key=lambda x: x["score"], reverse=True)
    return result[:k]


def _speaker_affinity(db: Session, user_id: int, event_id: int) -> int:
    from sqlalchemy import text as sql_text

    try:
        rows = db.execute(
            sql_text(
                "SELECT COUNT(DISTINCT es.speaker_id) FROM event_speaker es "
                "WHERE es.event_id = :eid AND es.speaker_id IN ("
                "  SELECT DISTINCT es2.speaker_id FROM event_speaker es2 "
                "  JOIN event_interaction ei ON ei.event_id = es2.event_id "
                "  WHERE ei.user_id = :uid AND ei.type IN ('like', 'save', 'rsvp', 'mark_attended')"
                ")"
            ),
            {"eid": event_id, "uid": user_id},
        ).scalar()
        return int(rows or 0)
    except Exception:
        return 0


def _event_reason(db: Session, provider, me: User, ev: Event) -> str:
    interests = db.execute(
        select(Interest)
        .join(EventInterest, EventInterest.interest_id == Interest.id)
        .where(EventInterest.event_id == ev.id)
    ).scalars().all()
    labels = [i.label for i in interests][:3]
    if provider.name == "gemini":
        try:
            return provider.generate_short_text(
                f"In one short line, why should {me.name} attend '{ev.title}'"
                + (f" (tags: {', '.join(labels)})" if labels else "")
                + "?",
                max_words=22,
            )
        except Exception:
            pass
    if labels:
        return f"Matches your interests: {', '.join(labels)}."
    return f"Popular in the {ev.track or 'AI'} track."


def _upsert_match(db: Session, a: int, b: int, score: float, reasons: list[str]) -> None:
    lo, hi = min(a, b), max(a, b)
    existing = db.execute(
        select(Match).where(Match.user_a_id == lo, Match.user_b_id == hi)
    ).scalar_one_or_none()
    if existing:
        existing.score = score
        existing.reasons = json.dumps(reasons)
    else:
        db.add(Match(user_a_id=lo, user_b_id=hi, score=score, reasons=json.dumps(reasons)))
    db.commit()
