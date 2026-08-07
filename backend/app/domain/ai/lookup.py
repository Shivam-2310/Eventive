"""Deterministic single-record lookups used by Ask Eventive.

Kept separate from :mod:`app.domain.ai.personal` because these are lookups
about the public catalog (any event / any speaker), not about the current
user's records.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.timefmt import format_time, format_when
from app.models.event import Event, EventInterest, EventSpeaker, Speaker
from app.models.interest import Interest


def event_by_id(db: Session, event_id: int) -> dict[str, Any]:
    ev = db.get(Event, event_id)
    if not ev:
        return {
            "ok": False,
            "prose": f"I couldn't find event #{event_id}.",
            "data": None,
        }
    speakers = db.execute(
        select(Speaker)
        .join(EventSpeaker, EventSpeaker.speaker_id == Speaker.id)
        .where(EventSpeaker.event_id == event_id)
    ).scalars().all()
    interests = db.execute(
        select(Interest)
        .join(EventInterest, EventInterest.interest_id == Interest.id)
        .where(EventInterest.event_id == event_id)
    ).scalars().all()
    when = format_when(ev.start_time, ev.timezone)
    if ev.end_time:
        when += " – " + format_time(ev.end_time, ev.timezone)
    where = ev.location or ""
    if ev.room:
        where = f"{where} / {ev.room}" if where else ev.room
    lines: list[str] = [
        f"[event:{ev.id}] {ev.title}",
        f"Track: {ev.track or '—'}    When: {when}    Where: {where or '—'}",
    ]
    if ev.capacity:
        lines.append(f"Capacity: {ev.capacity}    Status: {ev.status}")
    if speakers:
        s_parts = [
            f"{s.name}"
            + (f" ({s.title})" if s.title else "")
            + (f", {s.company}" if s.company else "")
            for s in speakers
        ]
        lines.append("Speakers: " + " · ".join(s_parts))
    if interests:
        lines.append("Tags: " + ", ".join(i.label for i in interests))
    body = ev.abstract or ev.description
    if body:
        lines.append("")
        lines.append(body)
    citations = [{"citation": f"event:{ev.id}", "title": ev.title, "url": f"/events/{ev.id}"}]
    for s in speakers:
        citations.append(
            {"citation": f"speaker:{s.id}", "title": s.name, "url": f"/speakers/{s.id}"}
        )
    return {
        "ok": True,
        "prose": "\n".join(lines),
        "data": {"event_id": ev.id, "title": ev.title, "track": ev.track},
        "citations": citations,
    }


def speaker_by_name(db: Session, name: str) -> dict[str, Any]:
    q = (name or "").strip().strip("?").strip()
    if not q:
        return {"ok": False, "prose": "Who did you want to look up?", "data": None}
    # Full match first, then prefix, then contains.
    row = db.execute(
        select(Speaker).where(func.lower(Speaker.name) == q.lower()).limit(1)
    ).scalars().first()
    if not row:
        row = db.execute(
            select(Speaker)
            .where(func.lower(Speaker.name).like(f"{q.lower()}%"))
            .limit(1)
        ).scalars().first()
    if not row:
        row = db.execute(
            select(Speaker)
            .where(func.lower(Speaker.name).like(f"%{q.lower()}%"))
            .limit(1)
        ).scalars().first()
    if not row:
        return {
            "ok": False,
            "prose": f"I couldn't find a speaker matching '{q}'.",
            "data": None,
        }
    # events they're speaking on
    events = db.execute(
        select(Event)
        .join(EventSpeaker, EventSpeaker.event_id == Event.id)
        .where(EventSpeaker.speaker_id == row.id)
        .order_by(Event.start_time.asc().nulls_last())
    ).scalars().all()
    lines: list[str] = [f"[speaker:{row.id}] {row.name}"]
    tail_parts = [x for x in (row.title, row.company) if x]
    if tail_parts:
        lines.append(", ".join(tail_parts))
    if row.bio:
        lines.append("")
        lines.append(row.bio)
    if events:
        lines.append("")
        lines.append(f"Speaking on {len(events)} session{'s' if len(events) != 1 else ''}:")
        for ev in events[:6]:
            lines.append(f"• [event:{ev.id}] {ev.title} — {format_when(ev.start_time, ev.timezone)}")
    citations = [{"citation": f"speaker:{row.id}", "title": row.name, "url": f"/speakers/{row.id}"}]
    for ev in events[:5]:
        citations.append({"citation": f"event:{ev.id}", "title": ev.title, "url": f"/events/{ev.id}"})
    return {
        "ok": True,
        "prose": "\n".join(lines),
        "data": {"speaker_id": row.id, "name": row.name},
        "citations": citations,
    }
