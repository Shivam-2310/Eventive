from __future__ import annotations

import json
import logging
import math
import struct

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.ai.llm_provider import EMBED_DIM, get_embedder
from app.models.ai import DocumentChunk
from app.models.event import Event, Speaker
from app.models.interest import Interest, UserInterest
from app.models.reel import Reel
from app.models.user import User

logger = logging.getLogger(__name__)


VEC_TABLES = {
    "vec_user_profile": "user_id",
    "vec_event": "event_id",
    "vec_interest": "interest_id",
    "vec_document": "chunk_id",
}


def _to_blob(vec: list[float]) -> bytes:
    if len(vec) != EMBED_DIM:
        raise ValueError(f"vec must be {EMBED_DIM} floats, got {len(vec)}")
    return struct.pack(f"<{EMBED_DIM}f", *vec)


def _upsert_vec(db: Session, table: str, key_col: str, key_val: int, vec: list[float]) -> None:
    db.execute(text(f"DELETE FROM {table} WHERE {key_col} = :k"), {"k": key_val})
    db.execute(
        text(f"INSERT INTO {table}({key_col}, embedding) VALUES (:k, :v)"),
        {"k": key_val, "v": _to_blob(vec)},
    )
    db.commit()


def embed_interest(db: Session, interest_id: int) -> bool:
    i = db.get(Interest, interest_id)
    if not i:
        return False
    text_ = f"{i.category}: {i.label}"
    vec = get_embedder().embed_batch([text_])[0]
    _upsert_vec(db, "vec_interest", "interest_id", interest_id, vec)
    return True


def embed_event(db: Session, event_id: int) -> bool:
    ev = db.get(Event, event_id)
    if not ev:
        return False
    speaker_bios = db.execute(
        text(
            "SELECT s.name, COALESCE(s.title, ''), COALESCE(s.bio, '') "
            "FROM speaker s JOIN event_speaker es ON es.speaker_id = s.id "
            "WHERE es.event_id = :eid"
        ),
        {"eid": event_id},
    ).all()
    speakers_str = " | ".join(f"{n}: {t} — {b[:200]}" for n, t, b in speaker_bios)
    # Fold the event's own interest tags into the embed body so cosine matching
    # against a user profile embedding (which is built from `category: label`
    # strings) has a strong direct signal. Without this the tag column was
    # invisible to the vector space — matches only worked when the abstract
    # happened to mention the tag label.
    tag_labels = db.execute(
        text(
            "SELECT i.category || ': ' || i.label "
            "FROM interest i JOIN event_interest ei ON ei.interest_id = i.id "
            "WHERE ei.event_id = :eid"
        ),
        {"eid": event_id},
    ).scalars().all()
    tags_str = "TAGS: " + ", ".join(tag_labels) if tag_labels else ""
    body = " ".join(
        x
        for x in (ev.title, ev.track or "", tags_str, ev.abstract or "", ev.description or "", speakers_str)
        if x
    )
    vec = get_embedder().embed_batch([body])[0]
    _upsert_vec(db, "vec_event", "event_id", event_id, vec)
    return True


def embed_user_profile(db: Session, user_id: int) -> bool:
    u = db.get(User, user_id)
    if not u:
        return False
    # weighted average of interest embeddings + blurb
    stmt = (
        select(UserInterest, Interest)
        .join(Interest, Interest.id == UserInterest.interest_id)
        .where(UserInterest.user_id == user_id)
    )
    interest_texts: list[tuple[str, float]] = []
    for ui, i in db.execute(stmt).all():
        interest_texts.append((f"{i.category}: {i.label}", float(ui.weight or 1.0)))
    blurb = (u.blurb or "").strip()

    provider = get_embedder()
    vecs: list[tuple[list[float], float]] = []
    if interest_texts:
        embs = provider.embed_batch([t for t, _ in interest_texts])
        for (_, w), e in zip(interest_texts, embs, strict=True):
            vecs.append((e, w))
    if blurb:
        vecs.append((provider.embed_batch([blurb])[0], 2.0))
    if not vecs:
        # fall back to name+headline+role
        seed = " ".join(x for x in (u.name, u.headline or "", u.role or "") if x) or f"user:{u.id}"
        vecs.append((provider.embed_batch([seed])[0], 1.0))

    acc = [0.0] * EMBED_DIM
    total_w = 0.0
    for v, w in vecs:
        for j in range(EMBED_DIM):
            acc[j] += v[j] * w
        total_w += w
    if total_w == 0:
        total_w = 1.0
    avg = [x / total_w for x in acc]
    norm = math.sqrt(sum(x * x for x in avg)) or 1.0
    avg = [x / norm for x in avg]
    _upsert_vec(db, "vec_user_profile", "user_id", user_id, avg)
    return True


def embed_document_chunks(db: Session, source_type: str, source_id: int) -> int:
    """Chunk + embed source content. Called on event/speaker/reel-transcript upsert."""
    # remove existing chunks + vecs
    old_ids = [
        r[0]
        for r in db.execute(
            select(DocumentChunk.id).where(
                DocumentChunk.source_type == source_type, DocumentChunk.source_id == source_id
            )
        ).all()
    ]
    for cid in old_ids:
        db.execute(text("DELETE FROM vec_document WHERE chunk_id = :k"), {"k": cid})
    db.execute(
        text("DELETE FROM document_chunk WHERE source_type = :t AND source_id = :s"),
        {"t": source_type, "s": source_id},
    )
    db.commit()

    text_body = _source_text(db, source_type, source_id)
    if not text_body:
        return 0
    chunks = _chunk(text_body)
    provider = get_embedder()
    embs = provider.embed_batch(chunks)
    n = 0
    for i, (chunk, emb) in enumerate(zip(chunks, embs, strict=True)):
        meta = {"source_type": source_type, "source_id": source_id, "index": i}
        row = DocumentChunk(
            source_type=source_type,
            source_id=source_id,
            chunk_index=i,
            chunk_text=chunk,
            chunk_metadata=json.dumps(meta),
        )
        db.add(row)
        db.flush()
        _upsert_vec(db, "vec_document", "chunk_id", row.id, emb)
        n += 1
    db.commit()
    return n


def _source_text(db: Session, source_type: str, source_id: int) -> str:
    if source_type == "event":
        ev = db.get(Event, source_id)
        if not ev:
            return ""
        speaker_names = db.execute(
            text("SELECT s.name FROM speaker s JOIN event_speaker es ON es.speaker_id = s.id WHERE es.event_id = :e"),
            {"e": source_id},
        ).scalars().all()
        return "\n".join(
            [
                f"EVENT: {ev.title}",
                f"TRACK: {ev.track or ''}",
                f"WHEN: {ev.start_time} — {ev.end_time}",
                f"WHERE: {ev.location or ''} {ev.room or ''}",
                f"SPEAKERS: {', '.join(speaker_names)}",
                f"ABSTRACT: {ev.abstract or ''}",
                f"DESCRIPTION: {ev.description or ''}",
            ]
        )
    if source_type == "speaker":
        s = db.get(Speaker, source_id)
        if not s:
            return ""
        return "\n".join([f"SPEAKER: {s.name}", f"TITLE: {s.title or ''}", f"COMPANY: {s.company or ''}", f"BIO: {s.bio or ''}"])
    if source_type == "reel_transcript":
        r = db.get(Reel, source_id)
        if not r or not r.transcript:
            return ""
        return f"REEL by user {r.user_id}\nCAPTION: {r.caption or ''}\nTRANSCRIPT: {r.transcript}"
    return ""


def _chunk(body: str, target_words: int = 400, overlap_words: int = 50) -> list[str]:
    words = body.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, target_words - overlap_words)
    for i in range(0, len(words), step):
        piece = words[i : i + target_words]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if i + target_words >= len(words):
            break
    return chunks


# --- kNN helpers ---------------------------------------------------------


def nearest(db: Session, table: str, key_col: str, ref_key: int, k: int = 10) -> list[tuple[int, float]]:
    q_row = db.execute(text(f"SELECT embedding FROM {table} WHERE {key_col} = :k"), {"k": ref_key}).first()
    if not q_row:
        return []
    q_blob = q_row[0]
    rows = db.execute(
        text(f"SELECT {key_col}, distance FROM {table} WHERE embedding MATCH :v AND k = :k ORDER BY distance"),
        {"v": q_blob, "k": k + 1},
    ).all()
    out = [(int(kid), float(d)) for kid, d in rows if int(kid) != int(ref_key)]
    return out[:k]


def nearest_by_vec(
    db: Session, table: str, key_col: str, vec: list[float], k: int = 10
) -> list[tuple[int, float]]:
    rows = db.execute(
        text(f"SELECT {key_col}, distance FROM {table} WHERE embedding MATCH :v AND k = :k ORDER BY distance"),
        {"v": _to_blob(vec), "k": k},
    ).all()
    return [(int(kid), float(d)) for kid, d in rows]


def _has_vec(db: Session, table: str, key_col: str, key_val: int) -> bool:
    row = db.execute(
        text(f"SELECT 1 FROM {table} WHERE {key_col} = :k LIMIT 1"),
        {"k": key_val},
    ).first()
    return row is not None


def _has_chunks(db: Session, source_type: str, source_id: int) -> bool:
    row = db.execute(
        select(DocumentChunk.id)
        .where(
            DocumentChunk.source_type == source_type,
            DocumentChunk.source_id == source_id,
        )
        .limit(1)
    ).first()
    return row is not None


def backfill_all(db: Session, *, force: bool = False) -> dict[str, int]:
    """Populate vec_* tables for interests/events/users.

    Idempotent by default: rows that already have a stored vector are skipped,
    so restarts don't re-hit the LLM (which matters for free-tier Gemini
    quotas — see the 429 we hit before adding this guard). Pass ``force=True``
    to rebuild every row, e.g. after tweaking the embedding text.
    """
    stats = {"users": 0, "events": 0, "interests": 0, "skipped": 0}
    for i in db.execute(select(Interest.id)).scalars().all():
        if not force and _has_vec(db, "vec_interest", "interest_id", i):
            stats["skipped"] += 1
            continue
        if embed_interest(db, i):
            stats["interests"] += 1
    for e in db.execute(select(Event.id)).scalars().all():
        if not force and _has_vec(db, "vec_event", "event_id", e):
            stats["skipped"] += 1
            continue
        if embed_event(db, e):
            stats["events"] += 1
    for u in db.execute(select(User.id)).scalars().all():
        if not force and _has_vec(db, "vec_user_profile", "user_id", u):
            stats["skipped"] += 1
            continue
        if embed_user_profile(db, u):
            stats["users"] += 1
    return stats


def rag_backfill(db: Session, *, force: bool = False) -> dict[str, int]:
    """Chunk + embed events/speakers/reel-transcripts into document_chunk +
    vec_document. Idempotent by default; sources that already have chunks
    are skipped. Pass ``force=True`` to rebuild."""
    stats = {"chunks": 0, "skipped": 0}
    for e in db.execute(select(Event.id)).scalars().all():
        if not force and _has_chunks(db, "event", e):
            stats["skipped"] += 1
            continue
        stats["chunks"] += embed_document_chunks(db, "event", e)
    for s in db.execute(select(Speaker.id)).scalars().all():
        if not force and _has_chunks(db, "speaker", s):
            stats["skipped"] += 1
            continue
        stats["chunks"] += embed_document_chunks(db, "speaker", s)
    for r in db.execute(select(Reel.id).where(Reel.transcript.isnot(None))).scalars().all():
        if not force and _has_chunks(db, "reel_transcript", r):
            stats["skipped"] += 1
            continue
        stats["chunks"] += embed_document_chunks(db, "reel_transcript", r)
    return stats
