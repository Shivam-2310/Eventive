"""Reel service: create → processing, feed → ready only, ownership guard."""
from __future__ import annotations

import pytest

from app.domain import reel_service, user_service
from app.models.reel import Reel
from app.schemas.user import UserCreate


def _mk_user(db, email: str) -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name="U"))


def test_create_reel_starts_in_processing(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "reel-owner@flo.dev")
    reel = reel_service.create_reel(
        db_session,
        user_id=u.id,
        filename="clip.mp4",
        content=b"\x00\x00\x00\x00fake-mp4",
        caption="Hello",
    )
    assert reel.status == "processing"
    assert reel.storage_key and reel.storage_key.startswith("reels/raw_")
    assert reel.caption == "Hello"


def test_create_reel_normalizes_bad_suffix(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "n@flo.dev")
    reel = reel_service.create_reel(db_session, u.id, filename="clip.exe", content=b"x")
    assert reel.storage_key.endswith(".mp4")


def test_list_feed_returns_only_ready(db_session) -> None:  # noqa: ANN001
    """Feed hides processing / rejected reels regardless of when they were created."""
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "feed@flo.dev")
    # Ready
    ready = Reel(user_id=u.id, status="ready", storage_key="reels/ready.mp4")
    processing = Reel(user_id=u.id, status="processing", storage_key="reels/p.mp4")
    rejected = Reel(user_id=u.id, status="rejected", storage_key="reels/r.mp4")
    db_session.add_all([ready, processing, rejected])
    db_session.commit()

    items = reel_service.list_feed(db_session, user_id=u.id, limit=10)
    ids = [i["reel"].id for i in items]
    assert ready.id in ids
    assert processing.id not in ids
    assert rejected.id not in ids


def test_delete_own_reel_removes_row(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "own@flo.dev")
    r = Reel(user_id=u.id, status="ready", storage_key="reels/own.mp4")
    db_session.add(r)
    db_session.commit()

    assert reel_service.delete_own_reel(db_session, u.id, r.id) is True
    assert reel_service.get_reel(db_session, r.id) is None


def test_delete_reel_by_non_owner_returns_false(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    a = _mk_user(db_session, "a@flo.dev")
    b = _mk_user(db_session, "b@flo.dev")
    r = Reel(user_id=a.id, status="ready", storage_key="reels/a.mp4")
    db_session.add(r)
    db_session.commit()
    assert reel_service.delete_own_reel(db_session, b.id, r.id) is False
    # row still present.
    assert reel_service.get_reel(db_session, r.id) is not None


def test_admin_delete_reel(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "adm@flo.dev")
    r = Reel(user_id=u.id, status="ready", storage_key="reels/adm.mp4")
    db_session.add(r)
    db_session.commit()
    assert reel_service.admin_delete_reel(db_session, r.id) is True
    assert reel_service.get_reel(db_session, r.id) is None
    assert reel_service.admin_delete_reel(db_session, r.id) is False


def test_record_interaction_valid_and_invalid(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    u = _mk_user(db_session, "int@flo.dev")
    r = Reel(user_id=u.id, status="ready", storage_key="reels/i.mp4")
    db_session.add(r)
    db_session.commit()
    row = reel_service.record_interaction(db_session, u.id, r.id, "like", watch_ms=1234)
    assert row.type == "like"
    assert row.watch_ms == 1234
    with pytest.raises(ValueError):
        reel_service.record_interaction(db_session, u.id, r.id, "hug", watch_ms=None)


def test_refresh_signed_urls_populates_video_and_thumbnail(db_session) -> None:  # noqa: ANN001, ARG001
    r = Reel(user_id=1, status="ready", storage_key="reels/x.mp4", thumbnail_key="reels/x.jpg")
    reel_service.refresh_signed_urls(r)
    assert r.video_url and r.video_url.startswith("/media/blob?k=reels/x.mp4")
    assert r.thumbnail_url and r.thumbnail_url.startswith("/media/blob?k=reels/x.jpg")
