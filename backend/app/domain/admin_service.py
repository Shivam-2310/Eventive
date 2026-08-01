from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import AdminAuditLog


def log_admin_action(
    db: Session,
    actor_user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    payload: dict | None = None,
) -> AdminAuditLog:
    row = AdminAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        payload=json.dumps(payload) if payload is not None else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_audit_logs(db: Session, limit: int = 100) -> list[AdminAuditLog]:
    return list(
        db.execute(select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(limit)).scalars().all()
    )
