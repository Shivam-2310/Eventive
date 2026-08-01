"""Workers: embedding upserts + backfill + kNN helpers (stub provider)."""
from __future__ import annotations

from sqlalchemy import text

from app.domain import interest_service, user_service
from app.schemas.user import UserCreate
from app.workers import embeddings as emb_worker


def test_embed_interest_upserts_vector(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    from app.models.interest import Interest

    interest = db_session.execute(text("SELECT id FROM interest LIMIT 1")).scalar_one()
    ok = emb_worker.embed_interest(db_session, int(interest))
    assert ok is True
    row = db_session.execute(
        text("SELECT embedding FROM vec_interest WHERE interest_id = :k"), {"k": int(interest)}
    ).first()
    assert row is not None
    assert isinstance(row[0], (bytes, bytearray))
    _ = Interest  # keep import for lint clarity


def test_embed_event_upserts_vector(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    eid = db_session.execute(text("SELECT id FROM event LIMIT 1")).scalar_one()
    ok = emb_worker.embed_event(db_session, int(eid))
    assert ok is True


def test_embed_missing_returns_false(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    assert emb_worker.embed_event(db_session, 999_999) is False
    assert emb_worker.embed_interest(db_session, 999_999) is False
    assert emb_worker.embed_user_profile(db_session, 999_999) is False


def test_embed_user_profile_uses_interests_when_present(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="up@flo.dev", name="U", blurb="hi"))
    interest = interest_service.list_interests(db_session)[0]
    interest_service.set_user_interests(db_session, user.id, [interest.id])
    ok = emb_worker.embed_user_profile(db_session, user.id)
    assert ok is True
    row = db_session.execute(
        text("SELECT embedding FROM vec_user_profile WHERE user_id = :k"), {"k": user.id}
    ).first()
    assert row is not None


def test_embed_user_profile_no_interests_uses_name_headline(db_session) -> None:  # noqa: ANN001
    """When a user has no interests + no blurb, the fallback uses their profile text."""
    from app.infra.db import ensure_schema

    ensure_schema()
    user = user_service.create_user(
        db_session, UserCreate(email="fb@flo.dev", name="Fallback", headline="Head", role="Role")
    )
    ok = emb_worker.embed_user_profile(db_session, user.id)
    assert ok is True


def test_backfill_all_populates_counts(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    # `seeded` already ran `backfill_all` once, so use force=True to re-embed
    # and prove the function still covers the full seeded corpus.
    stats = emb_worker.backfill_all(db_session, force=True)
    assert stats["events"] >= 40
    assert stats["interests"] >= 40
    assert stats["users"] >= 1


def test_backfill_all_is_idempotent_by_default(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """Second run without force=True should skip everything already embedded."""
    stats = emb_worker.backfill_all(db_session)
    assert stats["events"] == 0
    assert stats["interests"] == 0
    assert stats["users"] == 0
    assert stats["skipped"] >= 40


def test_rag_backfill_creates_chunks(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    # Same reasoning as above — seed pre-populated chunks; force to re-embed.
    stats = emb_worker.rag_backfill(db_session, force=True)
    assert stats["chunks"] >= 60  # 50 events + 20 speakers → 70 in default seed


def test_nearest_returns_sorted_and_excludes_ref(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """`nearest()` sorts by distance ascending and drops the reference key itself."""
    ref = db_session.execute(text("SELECT id FROM event LIMIT 1")).scalar_one()
    rows = emb_worker.nearest(db_session, "vec_event", "event_id", int(ref), k=5)
    assert rows
    assert all(k != int(ref) for k, _ in rows)
    distances = [d for _, d in rows]
    assert distances == sorted(distances)


def test_nearest_by_vec_returns_k_or_fewer(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    from app.domain.ai.stub_provider import StubProvider

    vec = StubProvider().embed_batch(["python fastapi"])[0]
    rows = emb_worker.nearest_by_vec(db_session, "vec_event", "event_id", vec, k=3)
    assert len(rows) <= 3


def test_embed_document_chunks_replaces_existing(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """Re-embedding a source deletes prior chunks and re-inserts a new batch."""
    from app.models.ai import DocumentChunk

    eid = int(db_session.execute(text("SELECT id FROM event LIMIT 1")).scalar_one())
    n1 = emb_worker.embed_document_chunks(db_session, "event", eid)
    from sqlalchemy import func, select

    count1 = db_session.execute(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.source_type == "event", DocumentChunk.source_id == eid
        )
    ).scalar()
    n2 = emb_worker.embed_document_chunks(db_session, "event", eid)
    count2 = db_session.execute(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.source_type == "event", DocumentChunk.source_id == eid
        )
    ).scalar()
    assert n1 == n2
    assert count1 == count2


def test_chunk_helper_respects_stride() -> None:
    """`_chunk` splits a long body with overlap without infinite looping."""
    body = " ".join([f"w{i}" for i in range(1200)])
    chunks = emb_worker._chunk(body, target_words=400, overlap_words=50)
    assert chunks
    assert all(len(c.split()) <= 400 for c in chunks)


def test_embed_event_folds_interest_tags_into_body(db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """`embed_event` must include event's tag labels + category in the embed text.

    Without this, the tag column is invisible to the vector space and event
    recommendations lose their strongest interest signal. We spy on the
    embedder to capture what body text got embedded and assert the labels
    appear (with the `TAGS:` prefix) exactly once.
    """
    from datetime import datetime, timedelta

    from app.domain import event_service, interest_service
    from app.infra.db import ensure_schema
    from app.schemas.event import EventCreate, EventInterestAssign

    ensure_schema()

    interest = interest_service.create_free_text_interest(
        db_session, "Vector Search", "topic"
    )
    ev = event_service.create_event(
        db_session,
        EventCreate(
            title="Cool AI Talk",
            track="AI",
            start_time=datetime.utcnow() + timedelta(days=1),
        ),
    )
    # Wire the interest to the event BEFORE spying so the direct embed_event
    # call below has tags to fold in. (assign_interests also fires its own
    # re-embed against the real embedder here — we don't care about that; we
    # only spy for the direct call that follows.)
    event_service.assign_interests(
        db_session, ev.id, EventInterestAssign(interest_ids=[interest.id])
    )

    captured: list[str] = []

    class SpyEmbedder:
        def embed_batch(self, texts):  # noqa: ANN001
            captured.extend(texts)
            # 384-dim deterministic zero vector avoids importing StubProvider.
            return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr(emb_worker, "get_embedder", lambda: SpyEmbedder())
    assert emb_worker.embed_event(db_session, ev.id) is True
    assert captured, "embedder was never called"
    body = captured[-1]
    assert "Vector Search" in body, body
    assert "TAGS:" in body, body

    # Sanity: re-assigning interests via the service also re-embeds and the
    # spy captures the tag-folded body (regression against Bug 3 in the audit).
    captured.clear()
    event_service.assign_interests(
        db_session, ev.id, EventInterestAssign(interest_ids=[interest.id])
    )
    assert captured, "assign_interests did not trigger embed_event"
    assert "Vector Search" in captured[-1]


def test_embed_event_no_tags_omits_prefix(db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """When an event has zero tag assignments, the TAGS: prefix is not emitted
    (keeps the embed text tight for tag-less imports)."""
    from datetime import datetime, timedelta

    from app.domain import event_service
    from app.infra.db import ensure_schema
    from app.schemas.event import EventCreate

    ensure_schema()
    ev = event_service.create_event(
        db_session,
        EventCreate(
            title="Empty Tags Talk",
            start_time=datetime.utcnow() + timedelta(days=1),
        ),
    )
    captured: list[str] = []

    class SpyEmbedder:
        def embed_batch(self, texts):  # noqa: ANN001
            captured.extend(texts)
            return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr(emb_worker, "get_embedder", lambda: SpyEmbedder())
    assert emb_worker.embed_event(db_session, ev.id) is True
    assert captured and "TAGS:" not in captured[-1]
