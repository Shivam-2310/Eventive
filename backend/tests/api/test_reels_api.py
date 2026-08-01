"""Reels REST: upload → processing, feed, interactions, delete owner-check."""
from __future__ import annotations

import io

import pytest

from app.models.reel import Reel


def _mk_user(client, email: str) -> int:  # noqa: ANN001
    return client.post("/users", json={"email": email, "name": "U"}).json()["id"]


@pytest.fixture(autouse=True)
def _mock_transcode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Background transcode is mocked so upload tests never touch ffmpeg."""
    from app.workers import transcode

    monkeypatch.setattr(transcode, "process_reel", lambda _rid: None)
    # For safety also patch the module referenced by the reels router.
    from app.api import reels as reels_router

    monkeypatch.setattr(reels_router, "process_reel", lambda _rid: None)


def test_upload_reel_starts_in_processing(client) -> None:  # noqa: ANN001
    uid = _mk_user(client, "up@x.com")
    body = b"\x00\x00\x00\x00fake-mp4"
    r = client.post(
        f"/reels?user_id={uid}",
        data={"caption": "hi"},
        files={"file": ("clip.mp4", io.BytesIO(body), "video/mp4")},
    )
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "processing"
    assert r.json()["reel_id"]


def test_empty_file_rejected(client) -> None:  # noqa: ANN001
    uid = _mk_user(client, "e@x.com")
    r = client.post(
        f"/reels?user_id={uid}",
        files={"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
    )
    assert r.status_code == 400


def test_get_reel_missing(client) -> None:  # noqa: ANN001
    assert client.get("/reels/999999").status_code == 404


def test_feed_returns_ready_reels_only(client, db_session) -> None:  # noqa: ANN001
    uid = _mk_user(client, "feed@x.com")
    r = Reel(user_id=uid, status="ready", storage_key="reels/ready.mp4")
    r2 = Reel(user_id=uid, status="processing", storage_key="reels/proc.mp4")
    db_session.add_all([r, r2])
    db_session.commit()

    body = client.get(f"/reels/feed?user_id={uid}").json()
    ids = [item["reel"]["id"] for item in body]
    assert r.id in ids
    assert r2.id not in ids


def test_reel_interaction_records(client, db_session) -> None:  # noqa: ANN001
    uid = _mk_user(client, "int@x.com")
    r = Reel(user_id=uid, status="ready", storage_key="reels/x.mp4")
    db_session.add(r)
    db_session.commit()

    r_id = r.id
    resp = client.post(
        f"/reels/{r_id}/interactions?user_id={uid}",
        json={"type": "like", "watch_ms": 500},
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "like"


def test_reel_interaction_invalid_type_400(client, db_session) -> None:  # noqa: ANN001
    uid = _mk_user(client, "invint@x.com")
    r = Reel(user_id=uid, status="ready", storage_key="reels/x.mp4")
    db_session.add(r)
    db_session.commit()
    resp = client.post(
        f"/reels/{r.id}/interactions?user_id={uid}",
        json={"type": "hug"},
    )
    assert resp.status_code == 400


def test_owner_can_delete_reel(client, db_session) -> None:  # noqa: ANN001
    uid = _mk_user(client, "own@x.com")
    r = Reel(user_id=uid, status="ready", storage_key="reels/o.mp4")
    db_session.add(r)
    db_session.commit()

    resp = client.delete(f"/reels/{r.id}?user_id={uid}")
    assert resp.status_code == 204
    assert client.get(f"/reels/{r.id}").status_code == 404


def test_non_owner_delete_returns_403(client, db_session) -> None:  # noqa: ANN001
    owner = _mk_user(client, "o@x.com")
    thief = _mk_user(client, "t@x.com")
    r = Reel(user_id=owner, status="ready", storage_key="reels/o.mp4")
    db_session.add(r)
    db_session.commit()

    resp = client.delete(f"/reels/{r.id}?user_id={thief}")
    assert resp.status_code == 403
