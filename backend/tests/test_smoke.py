"""End-to-end smoke test that exercises every phase's happy path in-process."""
from __future__ import annotations

import io
import os
import tempfile

os.environ.setdefault("LLM_PROVIDER", "stub")


def _setup_temp_db() -> None:
    """Point the whole app at a throwaway sqlite file before importing anything."""
    tmp = tempfile.mkdtemp(prefix="flo_test_")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/flo.db"
    os.environ["DATA_DIR"] = tmp
    os.environ["SEED_DEMO_FIXTURES"] = "true"


_setup_temp_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.infra.config import get_settings  # noqa: E402
from app.infra.db import ensure_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.scripts.seed import seed_all  # noqa: E402


def test_full_happy_path() -> None:
    # Refresh settings cache (env vars changed).
    get_settings.cache_clear()  # type: ignore[attr-defined]
    ensure_schema()
    seed_stats = seed_all()
    assert seed_stats["interests"] > 30
    assert seed_stats["events"] >= 40

    client = TestClient(app)

    # Phase 0
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200

    # Phase 1
    r = client.post("/users", json={"email": "dan@x.com", "name": "Dan"})
    assert r.status_code == 201, r.text
    dan = r.json()

    # Phase 2
    all_interests = client.get("/interests").json()
    assert len(all_interests) >= 40
    topic_ids = [i["id"] for i in all_interests if i["category"] == "topic"][:3]
    r = client.put(f"/users/{dan['id']}/interests", json={"interest_ids": topic_ids, "blurb": "hi"})
    assert r.status_code == 200
    assert len(client.get(f"/users/{dan['id']}/interests").json()) == 3

    # Phase 3
    events = client.get("/events").json()
    assert len(events) >= 40
    first_event_id = events[0]["id"]
    detail = client.get(f"/events/{first_event_id}").json()
    assert detail["id"] == first_event_id

    # Phase 4 — ingest events CSV (upsert path)
    csv_bytes = b"external_id,title,track,start_time,end_time,timezone,status\n"
    csv_bytes += b"probe-1,Probe Session,AI,2026-07-11T09:00:00,2026-07-11T10:00:00,UTC,scheduled\n"
    r = client.post(
        "/ingest/events",
        files={"file": ("probe.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    for _ in range(20):
        job = client.get(f"/ingest/jobs/{job_id}").json()
        if job["status"] in {"success", "failed"}:
            break
    assert job["status"] == "success", job

    # Phase 6
    disc = client.get(f"/events/discover?user_id={dan['id']}&limit=3").json()
    assert len(disc["cards"]) >= 1
    ev = disc["cards"][0]["event"]
    r = client.post(
        f"/events/{ev['id']}/react?user_id={dan['id']}",
        json={"prompt_type": "topic", "reaction": "like"},
    )
    assert r.status_code == 200
    r = client.post(
        f"/events/{ev['id']}/interactions?user_id={dan['id']}",
        json={"type": "like"},
    )
    assert r.status_code == 200

    # Phase 7 — seed already ran backfill_all internally, so force a re-embed
    # to prove the endpoint still covers the full seeded corpus.
    r = client.post("/ai/embed/backfill-all?force=true")
    assert r.status_code == 200
    stats = r.json()
    assert stats["users"] >= 1 and stats["events"] >= 40 and stats["interests"] >= 40

    r = client.get(f"/ai/embed/nearest/user/{dan['id']}?k=3").json()
    assert isinstance(r, list)

    # Phase 8
    r = client.get(f"/recommendations/events/{dan['id']}?limit=3").json()
    assert isinstance(r, list)

    # Phase 9 — accept an existing seeded connection (alice + bob = ids 2, 3)
    r = client.post("/connections?requester_id=2", json={"receiver_id": dan["id"]})
    assert r.status_code == 201
    conn = r.json()
    r = client.patch(f"/connections/{conn['id']}?user_id={dan['id']}", json={"status": "accepted"})
    assert r.status_code == 200
    threads = client.get(f"/threads?user_id={dan['id']}").json()
    assert len(threads) >= 1
    thread_id = threads[0]["id"]
    r = client.post(
        f"/threads/{thread_id}/messages?user_id={dan['id']}",
        json={"body": "hey"},
    )
    assert r.status_code == 201
    r = client.post(
        f"/threads/{thread_id}/attend-together?user_id={dan['id']}",
        json={"event_id": ev["id"]},
    )
    assert r.status_code == 200
    invite_id = r.json()["id"]
    r = client.post(f"/threads/{thread_id}/attend-together/{invite_id}/accept?user_id=2")
    assert r.status_code == 200

    # Phase 10
    r = client.get(f"/notifications?user_id={dan['id']}").json()
    assert isinstance(r, list)

    # Phase 11 — RAG backfill + Ask Flo (SSE not required; endpoint returns 200 stream)
    r = client.post("/ai/rag/backfill?force=true")
    assert r.status_code == 200
    with client.stream("POST", f"/ai/chat?user_id={dan['id']}", json={"message": "any AI safety talks today?"}) as s:
        text = "".join(chunk for chunk in s.iter_text())
    assert "event:" in text or "chunk" in text or "intent" in text

    # Phase 12
    missions = client.get("/missions").json()
    assert len(missions) >= 1
    r = client.get(f"/missions/me?user_id={dan['id']}").json()
    assert isinstance(r, list)

    # Phase 13
    pulse = client.get("/admin/pulse/snapshot").json()
    assert "likes_today" in pulse
    wrap = client.get(f"/users/{dan['id']}/wrapped").json()
    assert "sessions_attended" in wrap
