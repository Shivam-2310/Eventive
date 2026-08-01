from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import event_service
from app.models.event import Speaker


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None


def import_json_bundle(db: Session, content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except Exception as exc:
        return {"added": 0, "updated": 0, "failed": 0, "errors": [f"invalid json: {exc}"]}

    stats = {"events_added": 0, "events_updated": 0, "speakers_added": 0, "speakers_updated": 0, "failed": 0}
    errors: list[str] = []

    speakers_by_name: dict[str, Speaker] = {}
    for sp in payload.get("speakers", []):
        try:
            name = (sp.get("name") or "").strip()
            if not name:
                raise ValueError("missing name")
            existing = db.execute(select(Speaker).where(Speaker.name == name)).scalar_one_or_none()
            social = sp.get("social_links")
            if isinstance(social, (dict, list)):
                social = json.dumps(social)
            if existing:
                for k in ("bio", "company", "title", "headshot_url"):
                    if sp.get(k):
                        setattr(existing, k, sp[k])
                if social:
                    existing.social_links = social
                speakers_by_name[name] = existing
                stats["speakers_updated"] += 1
            else:
                s = Speaker(
                    name=name,
                    bio=sp.get("bio"),
                    company=sp.get("company"),
                    title=sp.get("title"),
                    headshot_url=sp.get("headshot_url"),
                    social_links=social,
                )
                db.add(s)
                db.flush()
                speakers_by_name[name] = s
                stats["speakers_added"] += 1
        except Exception as exc:
            stats["failed"] += 1
            errors.append(str(exc))
    db.commit()

    for ev in payload.get("events", []):
        try:
            row = {
                "external_id": ev.get("external_id"),
                "title": ev.get("title", ""),
                "description": ev.get("description"),
                "abstract": ev.get("abstract"),
                "track": ev.get("track"),
                "start_time": _parse_dt(ev.get("start_time")),
                "end_time": _parse_dt(ev.get("end_time")),
                "timezone": ev.get("timezone"),
                "location": ev.get("location"),
                "room": ev.get("room"),
                "capacity": ev.get("capacity"),
                "status": ev.get("status") or "scheduled",
                "cover_image_url": ev.get("cover_image_url"),
            }
            if not row["title"]:
                raise ValueError("missing title")
            ev_row, created = event_service.upsert_event_by_external_id(db, row)
            if created:
                stats["events_added"] += 1
            else:
                stats["events_updated"] += 1
            for sp_ref in ev.get("speakers", []) or []:
                if isinstance(sp_ref, dict):
                    name = sp_ref.get("name")
                    role = sp_ref.get("role", "panelist")
                else:
                    name, role = sp_ref, "panelist"
                if not name:
                    continue
                sp = speakers_by_name.get(name) or db.execute(
                    select(Speaker).where(Speaker.name == name)
                ).scalar_one_or_none()
                if not sp:
                    sp = Speaker(name=name)
                    db.add(sp)
                    db.flush()
                    speakers_by_name[name] = sp
                event_service.assign_speaker(db, ev_row.id, sp.id, role)
        except Exception as exc:
            stats["failed"] += 1
            errors.append(str(exc))

    return {**stats, "errors": errors[:20]}
