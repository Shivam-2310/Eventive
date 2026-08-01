"""User-scoped question handlers for Ask Flo.

These fire once the :mod:`app.domain.ai.intent` classifier tags a message as
``personal_query``. Everything here is deterministic, ORM-backed, and returns
a ``dict`` shaped like:

    {
      "ok": True,
      "prose": "You have saved 3 events: ...",
      "data": {...},       # optional structured payload (for the frontend)
      "citations": [...],  # optional list of {citation, title, url}
    }

We deliberately do **not** go through NL2SQL for these because:

* the questions are a small, well-known set — SQL is overkill;
* we need cross-table joins with pretty names (events + speakers + tracks)
  that the current NL2SQL views don't expose;
* the responses render as human paragraphs, not row dumps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain import matching_service
from app.infra.timefmt import format_when
from app.models.event import Event, EventSpeaker, Speaker
from app.models.interaction import EventInteraction
from app.models.interest import Interest, UserInterest
from app.models.mission import Mission, UserMissionProgress
from app.models.networking import Connection
from app.models.notification import Notification
from app.models.user import User

# ---- helpers ---------------------------------------------------------------


def _event_line(ev: Event, speakers: list[str] | None = None) -> str:
    when = format_when(ev.start_time, ev.timezone)
    where = ev.location or ""
    if ev.room:
        where = f"{where} / {ev.room}" if where else ev.room
    tail = f" — {when}"
    if where:
        tail += f" · {where}"
    if speakers:
        tail += f" · with {', '.join(speakers)}"
    return f"[event:{ev.id}] {ev.title}{tail}"


def _event_citation(ev: Event) -> dict[str, Any]:
    return {"citation": f"event:{ev.id}", "title": ev.title, "url": f"/events/{ev.id}"}


def _speakers_for(db: Session, event_id: int) -> list[str]:
    rows = db.execute(
        select(Speaker.name)
        .join(EventSpeaker, EventSpeaker.speaker_id == Speaker.id)
        .where(EventSpeaker.event_id == event_id)
    ).all()
    return [r[0] for r in rows]


def _get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def _interactions(
    db: Session, user_id: int, types: list[str]
) -> list[tuple[EventInteraction, Event]]:
    rows = (
        db.execute(
            select(EventInteraction, Event)
            .join(Event, Event.id == EventInteraction.event_id)
            .where(
                EventInteraction.user_id == user_id,
                EventInteraction.type.in_(types),
            )
            .order_by(Event.start_time.asc().nulls_last())
        )
        .all()
    )
    return [(row[0], row[1]) for row in rows]


def _dedup_events(pairs: list[tuple[EventInteraction, Event]]) -> list[Event]:
    seen: set[int] = set()
    out: list[Event] = []
    for _, ev in pairs:
        if ev.id in seen:
            continue
        seen.add(ev.id)
        out.append(ev)
    return out


def _bulleted_events(events: list[Event], db: Session, limit: int = 10) -> str:
    if not events:
        return ""
    lines = []
    for ev in events[:limit]:
        speakers = _speakers_for(db, ev.id)
        lines.append("• " + _event_line(ev, speakers))
    if len(events) > limit:
        lines.append(f"• …and {len(events) - limit} more.")
    return "\n".join(lines)


# ---- handlers --------------------------------------------------------------


def _handle_saved_or_liked(
    db: Session, user_id: int, types: list[str], label: str
) -> dict[str, Any]:
    pairs = _interactions(db, user_id, types)
    events = _dedup_events(pairs)
    if not events:
        return {"ok": True, "prose": f"You haven't {label} any events yet.", "data": []}
    prose = f"You've {label} {len(events)} event{'s' if len(events) != 1 else ''}:\n"
    prose += _bulleted_events(events, db)
    return {
        "ok": True,
        "prose": prose,
        "data": [{"event_id": e.id, "title": e.title} for e in events],
        "citations": [_event_citation(e) for e in events[:8]],
    }


def my_saved_events(db: Session, user_id: int) -> dict[str, Any]:
    # Match the Phase 2 "Saved" bucket exactly — Profile → Saved tab is
    # backed by `save` alone. Users get separate answers for their My Day
    # and Calendar lists via `my_agenda` / `my_calendar_events`.
    return _handle_saved_or_liked(db, user_id, ["save"], "saved")


def my_liked_events(db: Session, user_id: int) -> dict[str, Any]:
    return _handle_saved_or_liked(db, user_id, ["like"], "liked")


def my_attended_events(db: Session, user_id: int) -> dict[str, Any]:
    return _handle_saved_or_liked(db, user_id, ["mark_attended"], "marked as attended")


def my_rsvps(db: Session, user_id: int) -> dict[str, Any]:
    return _handle_saved_or_liked(db, user_id, ["rsvp"], "RSVPed to")


def my_calendar_events(db: Session, user_id: int) -> dict[str, Any]:
    return _handle_saved_or_liked(db, user_id, ["add_to_calendar"], "added to your calendar")


def my_agenda(db: Session, user_id: int) -> dict[str, Any]:
    # "My Day" specifically maps to `add_to_my_day`. When it's empty we fall
    # back to the union view so users still see something useful.
    day_pairs = _interactions(db, user_id, ["add_to_my_day"])
    if day_pairs:
        events = _dedup_events(day_pairs)
        prose = f"You have {len(events)} session{'s' if len(events) != 1 else ''} on My Day:\n"
        prose += _bulleted_events(events, db)
        return {
            "ok": True,
            "prose": prose,
            "data": [{"event_id": e.id, "title": e.title} for e in events],
            "citations": [_event_citation(e) for e in events[:8]],
        }
    pairs = _interactions(
        db, user_id, ["save", "add_to_my_day", "add_to_calendar", "rsvp", "mark_attended"]
    )
    events = _dedup_events(pairs)
    if not events:
        return {
            "ok": True,
            "prose": (
                "Your agenda is empty — like or RSVP to a few events on the discover "
                "feed and they'll show up here."
            ),
            "data": [],
        }
    now = datetime.utcnow()
    upcoming = [e for e in events if e.start_time and e.start_time >= now]
    past = [e for e in events if e.start_time and e.start_time < now]
    parts: list[str] = [
        f"You have {len(events)} event{'s' if len(events) != 1 else ''} on your agenda."
    ]
    if upcoming:
        parts.append("\nComing up:")
        parts.append(_bulleted_events(upcoming, db))
    if past:
        parts.append("\nAlready wrapped:")
        parts.append(_bulleted_events(past, db, limit=5))
    return {
        "ok": True,
        "prose": "\n".join(parts),
        "data": [{"event_id": e.id, "title": e.title} for e in events],
        "citations": [_event_citation(e) for e in events[:8]],
    }


def my_next_event(db: Session, user_id: int) -> dict[str, Any]:
    pairs = _interactions(
        db, user_id, ["save", "add_to_my_day", "add_to_calendar", "rsvp", "mark_attended"]
    )
    events = _dedup_events(pairs)
    now = datetime.utcnow()
    upcoming = [e for e in events if e.start_time and e.start_time >= now]
    if not upcoming:
        return {
            "ok": True,
            "prose": "Nothing on your agenda coming up — try liking a few events on the discover feed.",
            "data": None,
        }
    upcoming.sort(key=lambda e: e.start_time or datetime.max)
    ev = upcoming[0]
    speakers = _speakers_for(db, ev.id)
    prose = "Your next event is:\n" + _event_line(ev, speakers)
    if ev.abstract:
        prose += f"\n\n{ev.abstract}"
    return {
        "ok": True,
        "prose": prose,
        "data": {"event_id": ev.id, "title": ev.title, "start_time": str(ev.start_time)},
        "citations": [_event_citation(ev)],
    }


def my_interests(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(Interest)
        .join(UserInterest, UserInterest.interest_id == Interest.id)
        .where(UserInterest.user_id == user_id)
        .order_by(UserInterest.weight.desc())
    ).scalars().all()
    if not rows:
        return {
            "ok": True,
            "prose": "You haven't set any interests yet. Pick a few from onboarding so I can tailor recommendations.",
            "data": [],
        }
    labels = ", ".join(i.label for i in rows)
    prose = f"You follow {len(rows)} interest{'s' if len(rows) != 1 else ''}: {labels}."
    return {
        "ok": True,
        "prose": prose,
        "data": [{"id": i.id, "label": i.label, "category": i.category} for i in rows],
    }


def my_connections(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(Connection).where(
            and_(
                Connection.status == "accepted",
                or_(Connection.requester_id == user_id, Connection.receiver_id == user_id),
            )
        )
    ).scalars().all()
    if not rows:
        return {
            "ok": True,
            "prose": "You don't have any accepted connections yet. Try 'who should I meet?' for suggestions.",
            "data": [],
        }
    others: list[User] = []
    for c in rows:
        other_id = c.receiver_id if c.requester_id == user_id else c.requester_id
        u = db.get(User, other_id)
        if u:
            others.append(u)
    lines = [
        f"• [user:{u.id}] {u.name}"
        + (f" — {u.headline}" if u.headline else "")
        + (f" · {u.company}" if u.company else "")
        for u in others
    ]
    prose = (
        f"You're connected with {len(others)} "
        f"{'person' if len(others) == 1 else 'people'}:\n" + "\n".join(lines)
    )
    return {
        "ok": True,
        "prose": prose,
        "data": [{"user_id": u.id, "name": u.name, "headline": u.headline} for u in others],
    }


def my_pending_requests(db: Session, user_id: int) -> dict[str, Any]:
    incoming = db.execute(
        select(Connection).where(
            Connection.receiver_id == user_id, Connection.status == "pending"
        )
    ).scalars().all()
    outgoing = db.execute(
        select(Connection).where(
            Connection.requester_id == user_id, Connection.status == "pending"
        )
    ).scalars().all()
    parts: list[str] = []
    if incoming:
        names = []
        for c in incoming:
            u = db.get(User, c.requester_id)
            if u:
                names.append(f"[user:{u.id}] {u.name}")
        parts.append(
            f"{len(incoming)} incoming request{'s' if len(incoming) != 1 else ''}: "
            + ", ".join(names)
        )
    if outgoing:
        names = []
        for c in outgoing:
            u = db.get(User, c.receiver_id)
            if u:
                names.append(f"[user:{u.id}] {u.name}")
        parts.append(
            f"{len(outgoing)} outgoing request{'s' if len(outgoing) != 1 else ''}: "
            + ", ".join(names)
        )
    if not parts:
        return {
            "ok": True,
            "prose": "No pending connection requests. Inbox is clean!",
            "data": {"incoming": 0, "outgoing": 0},
        }
    return {
        "ok": True,
        "prose": "\n".join(parts),
        "data": {"incoming": len(incoming), "outgoing": len(outgoing)},
    }


def recommend_people(db: Session, user_id: int) -> dict[str, Any]:
    picks = matching_service.recommend_people(db, user_id, k=5)
    if not picks:
        return {
            "ok": True,
            "prose": "No matches to suggest right now — try adding more interests to your profile.",
            "data": [],
        }
    lines = []
    for p in picks:
        why = p["reasons"][0] if p.get("reasons") else "Great match."
        line = f"• [user:{p['other_user_id']}] {p['name']}"
        if p.get("headline"):
            line += f" — {p['headline']}"
        line += f"\n   {why}"
        lines.append(line)
    prose = "Here are people you might want to meet:\n" + "\n".join(lines)
    return {
        "ok": True,
        "prose": prose,
        "data": picks,
    }


def recommend_events(db: Session, user_id: int) -> dict[str, Any]:
    picks = matching_service.recommend_events(db, user_id, k=5)
    if not picks:
        return {
            "ok": True,
            "prose": "Nothing to recommend yet — pick a few interests during onboarding to help me tune this.",
            "data": [],
        }
    lines = []
    citations = []
    for p in picks:
        ev = db.get(Event, p["event_id"])
        if not ev:
            continue
        speakers = _speakers_for(db, ev.id)
        line = "• " + _event_line(ev, speakers)
        if p.get("reason"):
            line += f"\n   {p['reason']}"
        lines.append(line)
        citations.append(_event_citation(ev))
    prose = "Events I think you'd love:\n" + "\n".join(lines)
    return {"ok": True, "prose": prose, "data": picks, "citations": citations}


def my_notifications(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(10)
    ).scalars().all()
    unread = sum(1 for n in rows if n.read_at is None)
    if not rows:
        return {
            "ok": True,
            "prose": "Your inbox is empty. All caught up!",
            "data": [],
        }
    lines = [
        f"• {'●' if n.read_at is None else '○'} {n.title}"
        + (f" — {n.body}" if n.body else "")
        for n in rows
    ]
    prose = (
        f"You have {len(rows)} recent notification{'s' if len(rows) != 1 else ''} "
        f"({unread} unread):\n" + "\n".join(lines)
    )
    return {
        "ok": True,
        "prose": prose,
        "data": [
            {"id": n.id, "title": n.title, "body": n.body, "read": n.read_at is not None}
            for n in rows
        ],
    }


def my_missions(db: Session, user_id: int) -> dict[str, Any]:
    missions = db.execute(select(Mission).where(Mission.active.is_(True))).scalars().all()
    if not missions:
        return {"ok": True, "prose": "No missions available right now.", "data": []}
    progress_by_mid = {
        p.mission_id: p
        for p in db.execute(
            select(UserMissionProgress).where(UserMissionProgress.user_id == user_id)
        ).scalars().all()
    }
    lines = []
    total_points = 0
    for m in missions:
        p = progress_by_mid.get(m.id)
        status = (
            f"✓ done ({p.points_awarded} pts)"
            if p and p.completed_at
            else ("in progress" if p else "not started")
        )
        if p and p.completed_at:
            total_points += p.points_awarded or 0
        lines.append(f"• {m.title} — {status}")
    prose = (
        f"Missions ({total_points} pts earned):\n" + "\n".join(lines)
    )
    return {"ok": True, "prose": prose, "data": {"total_points": total_points}}


def my_profile(db: Session, user_id: int) -> dict[str, Any]:
    u = _get_user(db, user_id)
    if not u:
        return {"ok": False, "prose": "I couldn't find your profile.", "data": None}
    parts = [f"You're {u.name} ({u.email})"]
    if u.headline:
        parts.append(u.headline)
    if u.company or u.role:
        bits = [x for x in (u.role, u.company) if x]
        parts.append(" at ".join(bits))
    if u.blurb:
        parts.append(u.blurb)
    prose = ". ".join(p.strip().rstrip(".") for p in parts if p) + "."
    interests_res = my_interests(db, user_id)
    if interests_res["data"]:
        prose += "\n\n" + interests_res["prose"]
    return {"ok": True, "prose": prose, "data": {"user_id": u.id, "email": u.email, "name": u.name}}


def my_wrapped(db: Session, user_id: int) -> dict[str, Any]:
    # cheap counters
    total = {}
    for kind in ("like", "save", "rsvp", "mark_attended"):
        n = (
            db.execute(
                select(EventInteraction.id).where(
                    EventInteraction.user_id == user_id, EventInteraction.type == kind
                )
            )
            .scalars()
            .all()
        )
        total[kind] = len(n)
    conns = len(
        db.execute(
            select(Connection).where(
                Connection.status == "accepted",
                or_(Connection.requester_id == user_id, Connection.receiver_id == user_id),
            )
        ).scalars().all()
    )
    prose = (
        f"Your Flo Wrapped so far:\n"
        f"• Liked events: {total['like']}\n"
        f"• Saved events: {total['save']}\n"
        f"• RSVPs: {total['rsvp']}\n"
        f"• Attended: {total['mark_attended']}\n"
        f"• Accepted connections: {conns}"
    )
    return {"ok": True, "prose": prose, "data": {**total, "connections": conns}}


# ---- dispatcher ------------------------------------------------------------


HANDLERS: dict[str, Any] = {
    "my_saved_events": my_saved_events,
    "my_liked_events": my_liked_events,
    "my_attended_events": my_attended_events,
    "my_rsvps": my_rsvps,
    "my_calendar_events": my_calendar_events,
    "my_agenda": my_agenda,
    "my_next_event": my_next_event,
    "my_interests": my_interests,
    "my_connections": my_connections,
    "my_pending_requests": my_pending_requests,
    "recommend_people": recommend_people,
    "recommend_events": recommend_events,
    "my_notifications": my_notifications,
    "my_missions": my_missions,
    "my_profile": my_profile,
    "my_wrapped": my_wrapped,
}


def handle(db: Session, user_id: int, subkind: str) -> dict[str, Any]:
    fn = HANDLERS.get(subkind or "")
    if not fn:
        return {
            "ok": False,
            "prose": "I didn't quite catch that — try 'my saved events' or 'who should I meet?'",
            "data": None,
        }
    try:
        return fn(db, user_id)
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "prose": f"Something went wrong: {exc}", "data": None}
