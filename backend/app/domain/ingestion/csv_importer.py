from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain import event_service
from app.models.event import Speaker


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None


def import_events_csv(db: Session, content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    added, updated, failed = 0, 0, 0
    errors: list[str] = []
    for i, row in enumerate(reader, start=1):
        try:
            payload = {
                "external_id": (row.get("external_id") or row.get("id") or "").strip() or None,
                "title": (row.get("title") or "").strip(),
                "description": row.get("description") or None,
                "abstract": row.get("abstract") or None,
                "track": row.get("track") or None,
                "start_time": _parse_dt(row.get("start_time")),
                "end_time": _parse_dt(row.get("end_time")),
                "timezone": row.get("timezone") or None,
                "location": row.get("location") or None,
                "room": row.get("room") or None,
                "capacity": int(row["capacity"]) if row.get("capacity") else None,
                "status": (row.get("status") or "scheduled").strip(),
                "cover_image_url": row.get("cover_image_url") or None,
            }
            if not payload["title"]:
                raise ValueError("missing title")
            _, created = event_service.upsert_event_by_external_id(db, payload)
            if created:
                added += 1
            else:
                updated += 1
        except Exception as exc:
            failed += 1
            errors.append(f"row {i}: {exc}")
    return {"added": added, "updated": updated, "failed": failed, "errors": errors[:20]}


def import_speakers_csv(db: Session, content: bytes) -> dict[str, Any]:
    from sqlalchemy import select

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    added, updated, failed = 0, 0, 0
    errors: list[str] = []
    for i, row in enumerate(reader, start=1):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                raise ValueError("missing name")
            existing = db.execute(select(Speaker).where(Speaker.name == name)).scalar_one_or_none()
            social = row.get("social_links")
            if social:
                try:
                    social = json.dumps(json.loads(social))
                except Exception:
                    social = json.dumps({"raw": social})
            if existing:
                if row.get("bio"):
                    existing.bio = row["bio"]
                if row.get("company"):
                    existing.company = row["company"]
                if row.get("title"):
                    existing.title = row["title"]
                if row.get("headshot_url"):
                    existing.headshot_url = row["headshot_url"]
                if social:
                    existing.social_links = social
                updated += 1
            else:
                db.add(
                    Speaker(
                        name=name,
                        bio=row.get("bio") or None,
                        company=row.get("company") or None,
                        title=row.get("title") or None,
                        headshot_url=row.get("headshot_url") or None,
                        social_links=social,
                    )
                )
                added += 1
        except Exception as exc:
            failed += 1
            errors.append(f"row {i}: {exc}")
    db.commit()
    return {"added": added, "updated": updated, "failed": failed, "errors": errors[:20]}
