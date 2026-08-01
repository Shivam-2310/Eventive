"""LocalBlobStore: filesystem round-trip + HMAC-signed URL guard."""
from __future__ import annotations

import time
from pathlib import Path

import pytest


def test_save_and_read_bytes_round_trip(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    key = store.save_bytes(b"hello world", "reels/x.mp4")
    assert key == "reels/x.mp4"
    assert store.exists(key)
    assert store.read_bytes(key) == b"hello world"
    # underlying file lives inside DATA_DIR/reels
    assert (tmp_data_dir / "reels" / "x.mp4").is_file()


def test_signed_url_verify_ok(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    store.save_bytes(b"payload", "reels/y.mp4")
    url = store.signed_url("reels/y.mp4", ttl_seconds=60)
    # url looks like /media/blob?k=<key>&t=<epoch>&s=<sig>
    assert url.startswith("/media/blob?k=reels/y.mp4&t=")
    # parse t + s
    query = url.split("?", 1)[1]
    parts = dict(kv.split("=", 1) for kv in query.split("&"))
    assert store.verify(parts["k"], int(parts["t"]), parts["s"]) is True


def test_signed_url_expired_rejected(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    key = "reels/expired.mp4"
    # sign with a past expiry
    past = int(time.time()) - 5
    sig = store._sign(key, past)  # type: ignore[attr-defined]
    assert store.verify(key, past, sig) is False


def test_signed_url_tampered_signature_rejected(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    store.save_bytes(b"x", "reels/z.mp4")
    url = store.signed_url("reels/z.mp4", ttl_seconds=60)
    parts = dict(kv.split("=", 1) for kv in url.split("?", 1)[1].split("&"))
    bad_sig = "AAAA" + parts["s"][4:]
    assert store.verify(parts["k"], int(parts["t"]), bad_sig) is False


def test_path_traversal_rejected(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    with pytest.raises(ValueError):
        store.path_for("../etc/passwd")


def test_delete_removes_file(tmp_data_dir: Path) -> None:
    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    store.save_bytes(b"bye", "reels/del.mp4")
    assert store.exists("reels/del.mp4")
    store.delete("reels/del.mp4")
    assert not store.exists("reels/del.mp4")


def test_save_stream_writes_all_chunks(tmp_data_dir: Path) -> None:
    import io

    from app.infra.blob import LocalBlobStore

    store = LocalBlobStore(root=tmp_data_dir)
    src = io.BytesIO(b"stream-body")
    store.save_stream(src, "reels/s.mp4")
    assert store.read_bytes("reels/s.mp4") == b"stream-body"
