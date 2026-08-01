"""AI REST: suggestions, chat SSE, embed nearest, RAG backfill, voice stub."""
from __future__ import annotations

import json


def _mk_user(client, email: str) -> int:  # noqa: ANN001
    return client.post("/users", json={"email": email, "name": "U"}).json()["id"]


def test_suggestions_returns_starter_chips(seeded, client) -> None:  # noqa: ANN001, ARG001
    """`/ai/suggestions` returns >=4 starter chips covering the intent surface
    (personal_query, structured_query, semantic_search, action). We assert on
    the intent kinds present rather than an exact count so the chip catalog
    can grow without breaking the smoke test."""
    uid = _mk_user(client, "sug@x.com")
    r = client.get(f"/ai/suggestions?user_id={uid}")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 4
    intents = {row.get("intent") for row in body}
    # At least a couple of the intent kinds must be represented.
    assert intents.intersection({"personal_query", "structured_query", "semantic_search", "action", "event_lookup"})


def test_ai_chat_sse_stream_completes(seeded, client) -> None:  # noqa: ANN001, ARG001
    uid = _mk_user(client, "chat@x.com")
    with client.stream(
        "POST",
        f"/ai/chat?user_id={uid}",
        json={"message": "any AI safety talks today?"},
    ) as s:
        assert s.status_code == 200
        # Collect all SSE lines — expect at least one `event: intent` line and a `event: done`.
        text_all: list[str] = []
        for line in s.iter_lines():
            text_all.append(line)
    joined = "\n".join(text_all)
    assert "event: intent" in joined
    assert "event: done" in joined


def test_ai_chat_sse_streams_chunks(seeded, client) -> None:  # noqa: ANN001, ARG001
    """The stub provider yields token-sized chunks in the semantic branch."""
    uid = _mk_user(client, "stream@x.com")
    with client.stream(
        "POST",
        f"/ai/chat?user_id={uid}",
        json={"message": "any RAG demos?"},
    ) as s:
        events: list[dict] = []
        current: dict = {}
        for line in s.iter_lines():
            if line.startswith("event: "):
                current["event"] = line[len("event: "):]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[len("data: "):])
            elif line == "" and current:
                events.append(current)
                current = {}
    kinds = {e["event"] for e in events}
    assert "intent" in kinds
    assert "done" in kinds


def test_embed_backfill_all(seeded, client) -> None:  # noqa: ANN001, ARG001
    # `seeded` already ran the pipeline; force=true reproves full coverage.
    r = client.post("/ai/embed/backfill-all?force=true")
    assert r.status_code == 200
    stats = r.json()
    assert stats["events"] >= 40
    assert stats["interests"] >= 40
    assert stats["users"] >= 1


def test_embed_backfill_all_default_is_idempotent(seeded, client) -> None:  # noqa: ANN001, ARG001
    """Without force, the second call must be a cheap no-op."""
    r = client.post("/ai/embed/backfill-all")
    assert r.status_code == 200
    stats = r.json()
    assert stats["events"] == 0
    assert stats["skipped"] >= 40


def test_embed_nearest_user_and_event(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/ai/embed/nearest/user/2?k=3")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/ai/embed/nearest/event/1?k=3")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_embed_single_endpoints(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/ai/embed/user/2")
    assert r.status_code == 200 and r.json()["ok"] is True

    events = client.get("/events?limit=1").json()
    eid = events[0]["id"]
    r = client.post(f"/ai/embed/event/{eid}")
    assert r.status_code == 200

    interests = client.get("/interests").json()
    iid = interests[0]["id"]
    r = client.post(f"/ai/embed/interest/{iid}")
    assert r.status_code == 200


def test_embed_missing_returns_404(client) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    assert client.post("/ai/embed/user/999999").status_code == 404
    assert client.post("/ai/embed/event/999999").status_code == 404
    assert client.post("/ai/embed/interest/999999").status_code == 404


def test_rag_backfill_reports_chunks(seeded, client) -> None:  # noqa: ANN001, ARG001
    # `seeded` already populated document_chunk; force=true re-runs full pipeline.
    r = client.post("/ai/rag/backfill?force=true")
    assert r.status_code == 200
    assert r.json()["chunks"] >= 60


def test_ws_voice_returns_voice_disabled(client) -> None:  # noqa: ANN001
    """`/ws/ai/voice` is bound to the Noop adapter — must send `voice_disabled` and close."""
    with client.websocket_connect("/ai/ws/voice?user_id=1") as ws:
        raw = ws.receive_text()
        payload = json.loads(raw)
        assert payload == {"error": "voice_disabled"}
