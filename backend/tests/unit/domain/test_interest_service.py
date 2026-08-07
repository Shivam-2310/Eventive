"""Interest service: taxonomy load, filter, free-text, user↔interest linking."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.domain import interest_service, user_service
from app.models.interest import Interest, UserInterest
from app.schemas.user import UserCreate


def _make_user(db, email: str = "u@eventive.dev") -> object:  # noqa: ANN001
    return user_service.create_user(db, UserCreate(email=email, name="U"))


def test_seed_loads_44_interests(seeded: dict, db_session) -> None:  # noqa: ANN001
    total = db_session.execute(select(func.count(Interest.id))).scalar()
    assert total == 44
    assert seeded["interests"] == 44


def test_list_interests_filters_by_category(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    topics = interest_service.list_interests(db_session, category="topic")
    assert topics, "expected at least one topic interest"
    assert all(i.category == "topic" for i in topics)


def test_create_free_text_interest_marks_not_predefined(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    row = interest_service.create_free_text_interest(db_session, "My Custom Interest", "topic")
    assert row.is_predefined is False
    assert row.slug == "my-custom-interest"

    # Second call is idempotent: same slug → same row (no new insert).
    again = interest_service.create_free_text_interest(db_session, "My Custom Interest", "topic")
    assert again.id == row.id


def test_set_user_interests_replaces_and_writes_blurb(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _make_user(db_session, email="ui-test@eventive.dev")
    interests = interest_service.list_interests(db_session, category="topic")[:3]
    interest_ids = [i.id for i in interests]

    rows = interest_service.set_user_interests(db_session, user.id, interest_ids, blurb="hi there")
    assert len(rows) == 3
    db_session.refresh(user)
    assert user.blurb == "hi there"

    # Reassigning with a subset replaces, does not duplicate.
    rows2 = interest_service.set_user_interests(db_session, user.id, interest_ids[:1])
    assert len(rows2) == 1
    remaining = db_session.execute(
        select(UserInterest).where(UserInterest.user_id == user.id)
    ).scalars().all()
    assert len(remaining) == 1


def test_set_user_interests_ignores_unknown_interest_ids(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _make_user(db_session, email="ignore-unknown@eventive.dev")
    real_id = interest_service.list_interests(db_session)[0].id
    rows = interest_service.set_user_interests(db_session, user.id, [real_id, 999_999])
    assert len(rows) == 1


def test_set_user_interests_default_weight_is_one(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _make_user(db_session, email="weight@eventive.dev")
    real_id = interest_service.list_interests(db_session)[0].id
    interest_service.set_user_interests(db_session, user.id, [real_id])
    ui = db_session.execute(
        select(UserInterest).where(UserInterest.user_id == user.id)
    ).scalar_one()
    assert ui.weight == 1.0
    assert ui.source == "self"


def test_set_user_interests_missing_user_raises() -> None:
    """`set_user_interests` guards against a non-existent user."""
    from app.infra.db import SessionLocal, ensure_schema

    ensure_schema()
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            interest_service.set_user_interests(db, 999_999, [])
    finally:
        db.close()


def test_get_user_interests_returns_pairs(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    user = _make_user(db_session, email="pairs@eventive.dev")
    real_ids = [i.id for i in interest_service.list_interests(db_session)[:2]]
    interest_service.set_user_interests(db_session, user.id, real_ids)
    pairs = interest_service.get_user_interests(db_session, user.id)
    assert len(pairs) == 2
    for ui, interest in pairs:
        assert ui.user_id == user.id
        assert ui.interest_id == interest.id


def test_upsert_predefined_skips_duplicates(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    items = [
        {"label": "TestOne", "category": "topic"},
        {"label": "TestTwo", "category": "topic"},
    ]
    n = interest_service.upsert_predefined(db_session, items)
    assert n == 2
    n2 = interest_service.upsert_predefined(db_session, items)
    assert n2 == 0


def test_set_user_interests_refreshes_vec_row(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Regression: `set_user_interests` MUST synchronously refresh
    `vec_user_profile` so recommendations pick up the new interests without a
    manual `/ai/embed/user/{id}` call.

    Sets one interest → assert vec row exists. Then re-sets to a different
    interest → assert the vec blob CHANGES (stub embedder is deterministic).
    """
    from sqlalchemy import text as sql_text

    user = _make_user(db_session, email="reembed@eventive.dev")
    interests = interest_service.list_interests(db_session, category="topic")
    assert len(interests) >= 2

    interest_service.set_user_interests(db_session, user.id, [interests[0].id])
    row1 = db_session.execute(
        sql_text("SELECT embedding FROM vec_user_profile WHERE user_id = :k"),
        {"k": user.id},
    ).first()
    assert row1 is not None, "set_user_interests did not populate vec_user_profile"
    blob1 = bytes(row1[0])

    interest_service.set_user_interests(db_session, user.id, [interests[1].id])
    row2 = db_session.execute(
        sql_text("SELECT embedding FROM vec_user_profile WHERE user_id = :k"),
        {"k": user.id},
    ).first()
    assert row2 is not None
    blob2 = bytes(row2[0])
    assert blob1 != blob2, "vec_user_profile did not change after interest swap"


def test_set_user_interests_reembed_failure_is_swallowed(seeded: dict, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """A broken embedder must NOT bubble out and fail the interest save.

    We stub `embed_user_profile` to raise, then confirm `set_user_interests`
    still returns cleanly and the UserInterest rows are persisted.
    """
    from app.workers import embeddings as emb_worker

    def _boom(*_a, **_kw):
        raise RuntimeError("embedder down")

    monkeypatch.setattr(emb_worker, "embed_user_profile", _boom)

    user = _make_user(db_session, email="reembed-swallow@eventive.dev")
    real_id = interest_service.list_interests(db_session)[0].id
    rows = interest_service.set_user_interests(db_session, user.id, [real_id])
    assert len(rows) == 1
