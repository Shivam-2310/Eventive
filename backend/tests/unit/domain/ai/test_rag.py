"""RAG retrieve: top-k + source diversification + cosine_boost helper."""
from __future__ import annotations

from app.domain.ai import rag


def test_retrieve_empty_query_returns_empty(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    assert rag.retrieve(db_session, "", top_k=5) == []
    assert rag.retrieve(db_session, "   ", top_k=5) == []


def test_retrieve_returns_top_k_with_seeded_chunks(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """Seed script pre-embeds 70 chunks; retrieval should return `top_k` sorted rows."""
    results = rag.retrieve(db_session, "AI safety alignment RAG", top_k=5)
    assert results
    assert len(results) <= 5
    # Each item has the canonical shape.
    for r in results:
        assert set(r.keys()) >= {"chunk_id", "source_type", "source_id", "text", "distance", "score"}
    # Results are sorted by score descending.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_deduplicates_by_source(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """No more than 2 chunks per (source_type, source_id) come back."""
    results = rag.retrieve(db_session, "AI Python FastAPI", top_k=20)
    seen: dict[tuple[str, int], int] = {}
    for r in results:
        k = (r["source_type"], r["source_id"])
        seen[k] = seen.get(k, 0) + 1
    assert all(v <= 2 for v in seen.values())


def test_cosine_boost_range() -> None:
    """Between orthogonal vectors it's 0; between identical unit vectors it's 1."""
    assert rag.cosine_boost([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert rag.cosine_boost([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert rag.cosine_boost([], []) == 0.0
    assert rag.cosine_boost([1.0], []) == 0.0
    # Anti-parallel = -1
    assert rag.cosine_boost([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_mmr_prefers_lower_distance() -> None:
    """`_mmr` picks the lowest-distance candidate first (higher score)."""
    from app.domain.ai.rag import _mmr

    picked = _mmr([(1, 0.5), (2, 0.1), (3, 0.9)], k=2)
    assert len(picked) == 2
    # candidate with distance 0.1 has the highest score.
    ids = [p[0] for p in picked]
    assert ids[0] == 2
