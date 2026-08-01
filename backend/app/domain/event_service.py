from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.models.event import Event, EventInterest, EventSpeaker, Speaker
from app.models.interaction import EventCardReaction, EventInteraction
from app.models.interest import Interest
from app.models.networking import Connection
from app.schemas.event import (
    EventCard,
    EventCardPrompt,
    EventCreate,
    EventInterestAssign,
    EventReaction,
    EventUpdate,
    SpeakerCreate,
    SpeakerUpdate,
)

logger = logging.getLogger(__name__)


def _reembed_event(db: Session, event_id: int) -> None:
    """Best-effort refresh of the event's sqlite-vec row.

    Kept private + best-effort so a mis-configured embedder never breaks the
    calling business op (assign_speaker / assign_interests / upsert). The
    Alembic-created ``vec_event`` row is idempotently upserted by embed_event.
    """
    try:
        from app.workers import embeddings as _emb_worker

        _emb_worker.embed_event(db, event_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("embed_event(%s) after mutation failed: %s", event_id, exc)

VALID_PROMPT_TYPES = {"cover", "speaker", "topic", "when_where", "vibe", "who_is_going"}
VALID_INTERACTION_TYPES = {
    "like",
    "save",
    "add_to_my_day",
    "mark_attended",
    "add_to_calendar",
    "rsvp",
}


# --- Speakers ------------------------------------------------------------


def _speaker_row_to_dict(s: Speaker) -> dict[str, Any]:
    social = None
    if s.social_links:
        try:
            social = json.loads(s.social_links)
        except Exception:
            social = None
    return {
        "id": s.id,
        "name": s.name,
        "bio": s.bio,
        "headshot_url": s.headshot_url,
        "company": s.company,
        "title": s.title,
        "social_links": social,
    }


def create_speaker(db: Session, payload: SpeakerCreate) -> Speaker:
    data = payload.model_dump()
    social = data.pop("social_links", None)
    s = Speaker(**data, social_links=json.dumps(social) if social is not None else None)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_speaker(db: Session, speaker_id: int, payload: SpeakerUpdate) -> Speaker | None:
    s = db.get(Speaker, speaker_id)
    if not s:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "social_links" in data:
        val = data.pop("social_links")
        s.social_links = json.dumps(val) if val is not None else None
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


def get_speaker(db: Session, speaker_id: int) -> Speaker | None:
    return db.get(Speaker, speaker_id)


def list_speakers(db: Session, limit: int = 100) -> list[Speaker]:
    return list(db.execute(select(Speaker).order_by(Speaker.id).limit(limit)).scalars().all())


def delete_speaker(db: Session, speaker_id: int) -> bool:
    s = db.get(Speaker, speaker_id)
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True


# --- Events --------------------------------------------------------------


def create_event(db: Session, payload: EventCreate) -> Event:
    ev = Event(**payload.model_dump())
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def upsert_event_by_external_id(db: Session, payload: dict[str, Any]) -> tuple[Event, bool]:
    """Returns (event, created). `created=False` means it was updated."""
    ext = payload.get("external_id")
    existing = None
    if ext:
        existing = db.execute(select(Event).where(Event.external_id == ext)).scalar_one_or_none()
    if existing:
        for k, v in payload.items():
            if v is not None and hasattr(existing, k):
                setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing, False
    ev = Event(**{k: v for k, v in payload.items() if hasattr(Event, k)})
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev, True


def get_event(db: Session, event_id: int) -> Event | None:
    return db.get(Event, event_id)


def update_event(db: Session, event_id: int, payload: EventUpdate) -> Event | None:
    ev = db.get(Event, event_id)
    if not ev:
        return None
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ev, k, v)
    db.commit()
    db.refresh(ev)
    return ev


def delete_event(db: Session, event_id: int) -> bool:
    ev = db.get(Event, event_id)
    if not ev:
        return False
    db.delete(ev)
    db.commit()
    return True


def list_events(
    db: Session,
    status: str | None = None,
    track: str | None = None,
    day: date | None = None,
    speaker_id: int | None = None,
    interest_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Event]:
    stmt = select(Event)
    if status:
        stmt = stmt.where(Event.status == status)
    if track:
        stmt = stmt.where(Event.track == track)
    if day:
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        stmt = stmt.where(and_(Event.start_time >= start, Event.start_time < end))
    if speaker_id:
        stmt = stmt.join(EventSpeaker, EventSpeaker.event_id == Event.id).where(EventSpeaker.speaker_id == speaker_id)
    if interest_id:
        stmt = stmt.join(EventInterest, EventInterest.event_id == Event.id).where(
            EventInterest.interest_id == interest_id
        )
    stmt = stmt.order_by(Event.start_time.nulls_last(), Event.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().unique().all())


def assign_speaker(db: Session, event_id: int, speaker_id: int, role: str = "panelist") -> EventSpeaker:
    existing = db.execute(
        select(EventSpeaker).where(EventSpeaker.event_id == event_id, EventSpeaker.speaker_id == speaker_id)
    ).scalar_one_or_none()
    if existing:
        existing.role = role
        db.commit()
        _reembed_event(db, event_id)
        return existing
    es = EventSpeaker(event_id=event_id, speaker_id=speaker_id, role=role)
    db.add(es)
    db.commit()
    db.refresh(es)
    _reembed_event(db, event_id)
    return es


def assign_interests(db: Session, event_id: int, payload: EventInterestAssign) -> int:
    db.execute(delete(EventInterest).where(EventInterest.event_id == event_id))
    added = 0
    for iid in payload.interest_ids:
        if db.get(Interest, iid):
            db.add(EventInterest(event_id=event_id, interest_id=iid))
            added += 1
    db.commit()
    _reembed_event(db, event_id)
    return added


def event_speakers(db: Session, event_id: int) -> list[Speaker]:
    stmt = (
        select(Speaker)
        .join(EventSpeaker, EventSpeaker.speaker_id == Speaker.id)
        .where(EventSpeaker.event_id == event_id)
    )
    return list(db.execute(stmt).scalars().all())


def event_interests(db: Session, event_id: int) -> list[Interest]:
    stmt = (
        select(Interest)
        .join(EventInterest, EventInterest.interest_id == Interest.id)
        .where(EventInterest.event_id == event_id)
    )
    return list(db.execute(stmt).scalars().all())


def hydrate_event(db: Session, ev: Event) -> dict[str, Any]:
    speakers = [_speaker_row_to_dict(s) for s in event_speakers(db, ev.id)]
    interests = [{"id": i.id, "label": i.label, "category": i.category} for i in event_interests(db, ev.id)]
    from app.schemas.event import EventRead

    read = EventRead.model_validate(ev).model_dump()
    read["speakers"] = speakers
    read["interests"] = interests
    return read


# --- Discover cards ------------------------------------------------------


def discover_cards(db: Session, user_id: int, cursor: int | None, limit: int) -> tuple[list[EventCard], int | None]:
    stmt = select(Event).where(Event.status.in_(["scheduled", "live", "delayed"])).order_by(
        Event.start_time.nulls_last(), Event.id
    )
    if cursor:
        stmt = stmt.where(Event.id > cursor)
    stmt = stmt.limit(limit)
    events = list(db.execute(stmt).scalars().all())

    liked_pairs, connected_ids = _card_context(db, user_id)
    cards = [_build_event_card(db, ev, liked_pairs, connected_ids) for ev in events]
    next_cursor = events[-1].id if events else None
    return cards, next_cursor


def for_you_cards(db: Session, user_id: int, limit: int) -> list[EventCard]:
    """Interest-first discovery deck.

    Delegates ordering to `matching_service.recommend_events` (which already
    excludes finished/canceled/liked events and applies the interests-first
    scoring) then hydrates each hit with the same rich prompt structure the
    swipe deck expects. Keeps the frontend on one card model.
    """
    from app.domain import matching_service

    recs = matching_service.recommend_events(db, user_id, k=max(limit, 1))
    if not recs:
        return []
    liked_pairs, connected_ids = _card_context(db, user_id)
    # Preserve the exact ranking order returned by the recommender.
    cards: list[EventCard] = []
    for rec in recs[:limit]:
        ev = db.get(Event, int(rec["event_id"]))
        if ev is None:
            continue
        cards.append(_build_event_card(db, ev, liked_pairs, connected_ids))
    return cards


def _card_context(
    db: Session, user_id: int
) -> tuple[set[tuple[int, str, int | None]], set[int]]:
    """Fetch the reaction-lookup set + connected-user set used by every card build."""
    liked_pairs = set(
        db.execute(
            select(
                EventCardReaction.event_id,
                EventCardReaction.prompt_type,
                EventCardReaction.prompt_ref_id,
            ).where(
                EventCardReaction.user_id == user_id,
                EventCardReaction.reaction == "like",
            )
        ).all()
    )
    connected_ids = _connected_user_ids(db, user_id)
    return liked_pairs, connected_ids


def _build_event_card(
    db: Session,
    ev: Event,
    liked_pairs: set[tuple[int, str, int | None]],
    connected_ids: set[int],
) -> EventCard:
    """Build the 5–6 prompt swipe card for a single event.

    Extracted from ``discover_cards`` so the chronological deck and the
    interest-first "For You" deck (`for_you_cards`) render identically —
    same prompts, same speaker liking flag, same hydration payload.
    """
    speakers = event_speakers(db, ev.id)
    prompts: list[EventCardPrompt] = []
    prompts.append(
        EventCardPrompt(
            prompt_type="cover",
            label=ev.title,
            body=ev.cover_image_url or "",
            already_liked=(ev.id, "cover", None) in liked_pairs,
        )
    )
    if speakers:
        s = speakers[0]
        prompts.append(
            EventCardPrompt(
                prompt_type="speaker",
                prompt_ref_id=s.id,
                label=s.name,
                body=(s.title or "") + (f" · {s.company}" if s.company else ""),
                already_liked=(ev.id, "speaker", s.id) in liked_pairs,
            )
        )
    prompts.append(
        EventCardPrompt(
            prompt_type="topic",
            label="Topic",
            body=(ev.abstract or ev.description or "")[:300],
            already_liked=(ev.id, "topic", None) in liked_pairs,
        )
    )
    from app.infra.timefmt import format_day_time
    when = format_day_time(ev.start_time, ev.timezone)
    prompts.append(
        EventCardPrompt(
            prompt_type="when_where",
            label=when,
            body=" · ".join(x for x in (ev.location, ev.room) if x),
            already_liked=(ev.id, "when_where", None) in liked_pairs,
        )
    )
    prompts.append(
        EventCardPrompt(
            prompt_type="vibe",
            label="Vibe",
            body=ev.vibe_text or _fallback_vibe(ev),
            already_liked=(ev.id, "vibe", None) in liked_pairs,
        )
    )
    going = _who_is_going(db, ev.id, connected_ids)
    prompts.append(
        EventCardPrompt(
            prompt_type="who_is_going",
            label="Who's going",
            body=", ".join(going) if going else "",
            already_liked=(ev.id, "who_is_going", None) in liked_pairs,
        )
    )

    already_liked_speaker = any(
        pt == "speaker" for eid, pt, _ in liked_pairs if eid == ev.id
    )
    hydrated = hydrate_event(db, ev)
    from app.schemas.event import EventRead

    return EventCard(
        event=EventRead.model_validate(hydrated),
        prompts=prompts,
        already_liked_speaker=already_liked_speaker,
    )


def _fallback_vibe(ev: Event) -> str:
    track = f" ({ev.track})" if ev.track else ""
    return f"An engaging session on {ev.title}{track}."


def _connected_user_ids(db: Session, user_id: int) -> set[int]:
    stmt = select(Connection).where(
        ((Connection.requester_id == user_id) | (Connection.receiver_id == user_id))
        & (Connection.status == "accepted")
    )
    ids: set[int] = set()
    for c in db.execute(stmt).scalars().all():
        ids.add(c.receiver_id if c.requester_id == user_id else c.requester_id)
    return ids


def _who_is_going(db: Session, event_id: int, connected_ids: set[int], k: int = 3) -> list[str]:
    if not connected_ids:
        return []
    stmt = (
        select(EventInteraction.user_id)
        .where(EventInteraction.event_id == event_id, EventInteraction.type.in_(["rsvp", "save", "mark_attended"]))
        .distinct()
    )
    going = [uid for uid in db.execute(stmt).scalars().all() if uid in connected_ids][:k]
    if not going:
        return []
    from app.models.user import User as UserM

    names = db.execute(select(UserM.name).where(UserM.id.in_(going))).scalars().all()
    return list(names)


# --- Reactions & interactions --------------------------------------------


def react_to_prompt(db: Session, user_id: int, event_id: int, payload: EventReaction) -> EventCardReaction:
    if payload.prompt_type not in VALID_PROMPT_TYPES:
        raise ValueError(f"invalid prompt_type: {payload.prompt_type}")
    row = db.execute(
        select(EventCardReaction).where(
            EventCardReaction.user_id == user_id,
            EventCardReaction.event_id == event_id,
            EventCardReaction.prompt_type == payload.prompt_type,
            EventCardReaction.prompt_ref_id == payload.prompt_ref_id,
        )
    ).scalar_one_or_none()
    if row:
        row.reaction = payload.reaction
        row.comment_text = payload.comment_text
    else:
        row = EventCardReaction(
            user_id=user_id,
            event_id=event_id,
            prompt_type=payload.prompt_type,
            prompt_ref_id=payload.prompt_ref_id,
            reaction=payload.reaction,
            comment_text=payload.comment_text,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def record_interaction(db: Session, user_id: int, event_id: int, type_: str) -> EventInteraction:
    """Idempotent upsert: (user_id, event_id, type) is unique so repeated
    button taps return the existing row instead of stacking duplicates.
    """
    if type_ not in VALID_INTERACTION_TYPES:
        raise ValueError(f"invalid interaction type: {type_}")
    existing = db.execute(
        select(EventInteraction).where(
            EventInteraction.user_id == user_id,
            EventInteraction.event_id == event_id,
            EventInteraction.type == type_,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = EventInteraction(user_id=user_id, event_id=event_id, type=type_)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_interaction(db: Session, user_id: int, event_id: int, type_: str) -> bool:
    """Deletes the (user, event, type) interaction row, if it exists.

    Returns True when a row was actually removed. Safe to call on an
    already-cleared state — callers can use this to implement toggles.
    """
    if type_ not in VALID_INTERACTION_TYPES:
        raise ValueError(f"invalid interaction type: {type_}")
    row = db.execute(
        select(EventInteraction).where(
            EventInteraction.user_id == user_id,
            EventInteraction.event_id == event_id,
            EventInteraction.type == type_,
        )
    ).scalar_one_or_none()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def user_interaction_map(db: Session, user_id: int) -> dict[int, list[str]]:
    """Return `{event_id: [interaction_type, ...]}` for the given user.

    Used by the client to hydrate the "active" state of every chip in the
    Event Details bottom sheet and to render the Profile activity sections
    without having to fetch each event individually.
    """
    rows = db.execute(
        select(EventInteraction.event_id, EventInteraction.type).where(EventInteraction.user_id == user_id)
    ).all()
    out: dict[int, list[str]] = {}
    for event_id, type_ in rows:
        out.setdefault(int(event_id), []).append(str(type_))
    return out


def user_events_by_interaction(db: Session, user_id: int) -> dict[str, list[dict[str, Any]]]:
    """Group the user's interactions into buckets of hydrated events.

    Keys are the six canonical interaction types plus the pseudo-bucket
    ``upcoming_rsvp`` (RSVPs whose event has not yet started). Every value
    is a list of ``EventRead`` dicts, ordered by soonest start time first.
    """
    stmt = (
        select(EventInteraction.type, Event)
        .join(Event, Event.id == EventInteraction.event_id)
        .where(EventInteraction.user_id == user_id)
        .order_by(Event.start_time.nulls_last(), Event.id)
    )
    buckets: dict[str, list[dict[str, Any]]] = {t: [] for t in VALID_INTERACTION_TYPES}
    buckets["upcoming_rsvp"] = []
    now = datetime.utcnow()
    seen: dict[str, set[int]] = {}
    for type_, ev in db.execute(stmt).all():
        if ev is None:
            continue
        bucket_seen = seen.setdefault(type_, set())
        if ev.id in bucket_seen:
            continue
        bucket_seen.add(ev.id)
        hydrated = hydrate_event(db, ev)
        buckets[type_].append(hydrated)
        if type_ == "rsvp" and ev.start_time and ev.start_time >= now:
            buckets["upcoming_rsvp"].append(hydrated)
    return buckets
