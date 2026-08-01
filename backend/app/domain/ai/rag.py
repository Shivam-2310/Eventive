from __future__ import annotations

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.ai.llm_provider import get_embedder
from app.models.ai import DocumentChunk


def _mmr(candidates: list[tuple[int, float]], k: int, diversity: float = 0.6) -> list[tuple[int, float]]:
    """Very light MMR: prefer closer items but penalize duplicate source_id."""
    picked: list[tuple[int, float]] = []
    seen_sources: dict[int, int] = {}
    for cid, dist in candidates:
        # cid encodes the chunk id; source penalty applied downstream by caller
        source = seen_sources.get(cid, 0)
        penalty = diversity * source
        score = -dist - penalty
        picked.append((cid, score))
        seen_sources[cid] = seen_sources.get(cid, 0) + 1
    picked.sort(key=lambda x: x[1], reverse=True)
    return picked[:k]


def retrieve(db: Session, query: str, top_k: int = 8) -> list[dict]:
    if not query.strip():
        return []
    qvec = get_embedder().embed_batch([query])[0]
    import struct as _struct

    blob = _struct.pack(f"<{len(qvec)}f", *qvec)
    rows = db.execute(
        text(
            "SELECT chunk_id, distance FROM vec_document "
            "WHERE embedding MATCH :v AND k = :k ORDER BY distance"
        ),
        {"v": blob, "k": max(top_k * 3, 16)},
    ).all()
    # Dedup by (source_type, source_id) preferring closest
    picked: list[dict] = []
    seen: dict[tuple[str, int], int] = {}
    for cid, dist in rows:
        chunk = db.get(DocumentChunk, int(cid))
        if not chunk:
            continue
        key = (chunk.source_type, chunk.source_id)
        seen[key] = seen.get(key, 0) + 1
        # allow up to 2 chunks per source, penalize repeats
        if seen[key] > 2:
            continue
        score = -(float(dist) + 0.1 * (seen[key] - 1))
        picked.append(
            {
                "chunk_id": chunk.id,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "text": chunk.chunk_text,
                "distance": float(dist),
                "score": score,
            }
        )
    picked.sort(key=lambda x: x["score"], reverse=True)
    return picked[:top_k]


def cosine_boost(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
