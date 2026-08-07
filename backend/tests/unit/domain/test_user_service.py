"""User service unit tests (create / read / update / delete + email uniqueness)."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain import user_service
from app.schemas.user import UserCreate, UserUpdate


def _make(db, email: str = "test@eventive.dev", name: str = "Test") -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name=name))


def test_create_user_persists_row(db_session) -> None:  # noqa: ANN001
    u = _make(db_session)
    assert u.id is not None
    assert u.email == "test@eventive.dev"
    assert u.opt_in_networking is True  # default from schema


def test_get_and_get_by_email(db_session) -> None:  # noqa: ANN001
    u = _make(db_session, email="lookup@eventive.dev")
    assert user_service.get_user(db_session, u.id).id == u.id
    assert user_service.get_by_email(db_session, "lookup@eventive.dev").id == u.id
    assert user_service.get_by_email(db_session, "nope@eventive.dev") is None
    assert user_service.get_user(db_session, 999_999) is None


def test_list_users_pagination(db_session) -> None:  # noqa: ANN001
    for i in range(5):
        _make(db_session, email=f"u{i}@eventive.dev", name=f"U{i}")
    all_users = user_service.list_users(db_session)
    assert len(all_users) == 5
    page = user_service.list_users(db_session, limit=2, offset=2)
    assert len(page) == 2
    assert page[0].id == all_users[2].id


def test_update_user_partial_patch(db_session) -> None:  # noqa: ANN001
    u = _make(db_session)
    updated = user_service.update_user(
        db_session, u.id, UserUpdate(name="New Name", opt_in_networking=False)
    )
    assert updated is not None
    assert updated.name == "New Name"
    assert updated.opt_in_networking is False
    # Email unchanged.
    assert updated.email == "test@eventive.dev"


def test_update_user_returns_none_when_missing(db_session) -> None:  # noqa: ANN001
    assert user_service.update_user(db_session, 42_424, UserUpdate(name="ghost")) is None


def test_delete_user(db_session) -> None:  # noqa: ANN001
    u = _make(db_session)
    assert user_service.delete_user(db_session, u.id) is True
    assert user_service.get_user(db_session, u.id) is None
    # second delete returns False (already gone).
    assert user_service.delete_user(db_session, u.id) is False


def test_duplicate_email_raises_integrity_error(db_session) -> None:  # noqa: ANN001
    """`user` has a UNIQUE(email) constraint — repeated create must raise."""
    _make(db_session, email="dup@eventive.dev")
    with pytest.raises(IntegrityError):
        _make(db_session, email="dup@eventive.dev")


def test_touch_last_seen_sets_timestamp(db_session) -> None:  # noqa: ANN001
    u = _make(db_session)
    assert u.last_seen_at is None
    user_service.touch_last_seen(db_session, u.id)
    db_session.refresh(u)
    assert u.last_seen_at is not None


def test_seed_creates_exactly_one_admin(seeded: dict, db_session) -> None:  # noqa: ANN001
    """Seed step: fresh DB → seed creates exactly one admin with is_admin=True."""
    from sqlalchemy import func, select

    from app.models.user import User

    admin_count = db_session.execute(
        select(func.count(User.id)).where(User.is_admin.is_(True))
    ).scalar()
    assert admin_count == 1
    assert seeded["admin"] == 1


def test_create_user_synchronously_embeds_profile(db_session) -> None:  # noqa: ANN001
    """Regression: every new user MUST have a `vec_user_profile` row on
    creation so `matching_service.recommend_people` sees them immediately.
    Also fires from `/auth/register` because register → create_user."""
    from sqlalchemy import text as sql_text

    u = _make(db_session, email="autoembed@eventive.dev", name="Auto")
    row = db_session.execute(
        sql_text("SELECT embedding FROM vec_user_profile WHERE user_id = :k"),
        {"k": u.id},
    ).first()
    assert row is not None, "create_user did not populate vec_user_profile"


def test_create_user_swallows_embed_failure(db_session, monkeypatch) -> None:  # noqa: ANN001
    """If the embedder is temporarily broken, create_user must still succeed."""
    from app.workers import embeddings as emb_worker

    def _boom(*_a, **_kw):
        raise RuntimeError("embedder down")

    monkeypatch.setattr(emb_worker, "embed_user_profile", _boom)
    u = _make(db_session, email="safe@eventive.dev", name="Safe")
    assert u.id is not None
