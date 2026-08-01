from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.domain import chat_service, event_service


def like_event(db: Session, user_id: int, event_id: int) -> dict[str, Any]:
    row = event_service.record_interaction(db, user_id, event_id, "like")
    return {"ok": True, "interaction_id": row.id, "event_id": event_id, "type": "like"}


def rsvp_event(db: Session, user_id: int, event_id: int) -> dict[str, Any]:
    row = event_service.record_interaction(db, user_id, event_id, "rsvp")
    return {"ok": True, "interaction_id": row.id, "event_id": event_id, "type": "rsvp"}


def open_match(db: Session, user_id: int, other_user_id: int) -> dict[str, Any]:
    conn = chat_service.create_connection(db, user_id, other_user_id, hook_interest_id=None)
    return {"ok": True, "connection_id": conn.id, "status": conn.status}


def send_message_draft(user_id: int, other_user_id: int, body: str) -> dict[str, Any]:
    # Never actually sends — returns a draft for the user to approve.
    return {"ok": True, "draft": body, "to_user_id": other_user_id, "from_user_id": user_id}


def parse_and_execute(db: Session, user_id: int, user_msg: str) -> dict[str, Any] | None:
    """Extremely small parser for demo actions the stub router can invoke.

    Supported:
      - "like event <id>"
      - "rsvp event <id>"
      - "open match with user <id>"
    """
    text = user_msg.strip().lower()
    m = re.search(r"like\s+event\s+(\d+)", text)
    if m:
        return like_event(db, user_id, int(m.group(1)))
    m = re.search(r"rsvp\s+(?:to\s+)?event\s+(\d+)", text)
    if m:
        return rsvp_event(db, user_id, int(m.group(1)))
    m = re.search(r"open\s+match\s+with\s+user\s+(\d+)", text)
    if m:
        return open_match(db, user_id, int(m.group(1)))
    return None
