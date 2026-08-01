"""Admin REST: audit log + admin reel deletion."""
from __future__ import annotations


def test_admin_audit_log_lists_seed_run(seeded, client) -> None:  # noqa: ANN001, ARG001
    body = client.get("/admin/audit-log").json()
    assert isinstance(body, list)
    actions = {row["action"] for row in body}
    assert "seed_run" in actions


def test_admin_delete_reel_writes_audit(client, db_session) -> None:  # noqa: ANN001
    from app.domain import user_service
    from app.models.reel import Reel
    from app.schemas.user import UserCreate

    user = user_service.create_user(db_session, UserCreate(email="ad@x.com", name="A"))
    reel = Reel(user_id=user.id, status="ready", storage_key="reels/x.mp4")
    db_session.add(reel)
    db_session.commit()
    reel_id = reel.id

    r = client.delete(f"/admin/reels/{reel_id}")
    assert r.status_code == 204

    audit = client.get("/admin/audit-log").json()
    reel_actions = [a for a in audit if a["action"] == "reel_delete"]
    assert reel_actions
    assert any(a["target_id"] == str(reel_id) for a in reel_actions)


def test_admin_delete_missing_reel_404(client) -> None:  # noqa: ANN001
    r = client.delete("/admin/reels/999999")
    assert r.status_code == 404
