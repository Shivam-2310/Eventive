from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.ws_manager import manager
from app.models.notification import Notification


def push(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    body: str | None = None,
    deep_link: str | None = None,
) -> Notification:
    row = Notification(user_id=user_id, type=type_, title=title, body=body, deep_link=deep_link)
    db.add(row)
    db.commit()
    db.refresh(row)
    payload: dict[str, Any] = {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "deep_link": row.deep_link,
        "created_at": row.created_at.isoformat(),
    }
    _fire_and_forget(manager.send_to_user(user_id, {"channel": "notification", "data": payload}))
    return row


def list_notifications(db: Session, user_id: int, unread_only: bool = False) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.id.desc())
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.execute(stmt.limit(200)).scalars().all())


def mark_read(db: Session, user_id: int, notif_id: int) -> bool:
    n = db.get(Notification, notif_id)
    if not n or n.user_id != user_id:
        return False
    if n.read_at is None:
        n.read_at = datetime.utcnow()
        db.commit()
    return True


def _fire_and_forget(coro) -> None:  # noqa: ANN001
    """Best-effort WS push. Route handlers may be sync (running in FastAPI's
    threadpool) or async (running on the main loop). We try both and swallow
    errors so business logic never fails because a WS delivery couldn't be
    scheduled — the notification row is already persisted for the next fetch.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
        return
    except RuntimeError:
        pass
    try:
        import anyio.from_thread

        async def _runner() -> None:
            await coro

        anyio.from_thread.run(_runner)
    except Exception:
        # No portal available (e.g. background task not spawned via FastAPI).
        # Skip the WS push silently.
        pass
