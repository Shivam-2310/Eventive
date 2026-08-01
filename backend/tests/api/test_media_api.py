"""Media signed-URL endpoint: HMAC token verification + FileResponse."""
from __future__ import annotations

import time


def test_signed_url_delivers_file(client) -> None:  # noqa: ANN001
    from app.infra.blob import blob_store

    blob_store.save_bytes(b"hello", "reels/m.mp4")
    url = blob_store.signed_url("reels/m.mp4", ttl_seconds=60)
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.content == b"hello"


def test_expired_signature_403(client) -> None:  # noqa: ANN001
    from app.infra.blob import blob_store

    key = "reels/expired.mp4"
    blob_store.save_bytes(b"x", key)
    past = int(time.time()) - 10
    sig = blob_store._sign(key, past)
    resp = client.get(f"/media/blob?k={key}&t={past}&s={sig}")
    assert resp.status_code == 403


def test_tampered_signature_403(client) -> None:  # noqa: ANN001
    from app.infra.blob import blob_store

    key = "reels/tamper.mp4"
    blob_store.save_bytes(b"x", key)
    url = blob_store.signed_url(key, ttl_seconds=60)
    parts = dict(kv.split("=", 1) for kv in url.split("?", 1)[1].split("&"))
    bad = "AAAA" + parts["s"][4:]
    resp = client.get(f"/media/blob?k={parts['k']}&t={parts['t']}&s={bad}")
    assert resp.status_code == 403


def test_missing_file_404(client) -> None:  # noqa: ANN001
    from app.infra.blob import blob_store

    key = "reels/nope.mp4"
    # produce a valid signature but do not create the file
    url = blob_store.signed_url(key, ttl_seconds=60)
    resp = client.get(url)
    assert resp.status_code == 404
