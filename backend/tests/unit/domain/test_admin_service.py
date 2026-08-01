"""Admin service: log_admin_action writes rows; seed logs `seed_run` itself."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.domain import admin_service
from app.models.admin import AdminAuditLog


def test_log_admin_action_writes_row(db_session) -> None:  # noqa: ANN001
    from app.domain import user_service
    from app.infra.db import ensure_schema

    ensure_schema()
    from app.schemas.user import UserCreate

    actor = user_service.create_user(
        db_session, UserCreate(email="actor@flo.dev", name="Actor", is_admin=True)
    )
    row = admin_service.log_admin_action(
        db_session,
        actor_user_id=actor.id,
        action="test_action",
        target_type="event",
        target_id=42,
        payload={"foo": "bar"},
    )
    assert row.id
    saved = db_session.execute(select(AdminAuditLog).where(AdminAuditLog.id == row.id)).scalar_one()
    assert saved.actor_user_id == actor.id
    assert saved.action == "test_action"
    assert saved.target_type == "event"
    assert saved.target_id == "42"
    assert json.loads(saved.payload) == {"foo": "bar"}


def test_log_admin_action_serializes_none_payload(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    row = admin_service.log_admin_action(db_session, None, "noop")
    assert row.payload is None
    assert row.target_id is None


def test_seed_writes_seed_run_row(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Seed itself logs a `seed_run` admin action with the resulting stats."""
    rows = db_session.execute(
        select(AdminAuditLog).where(AdminAuditLog.action == "seed_run")
    ).scalars().all()
    assert rows, "expected at least one seed_run audit row"
    stats = json.loads(rows[-1].payload) if rows[-1].payload else {}
    assert "stats" in stats
    assert stats["stats"]["admin"] >= 0


def test_list_audit_logs_orders_desc(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    admin_service.log_admin_action(db_session, None, "first")
    admin_service.log_admin_action(db_session, None, "second")
    rows = admin_service.list_audit_logs(db_session, limit=10)
    assert rows[0].action == "second"
