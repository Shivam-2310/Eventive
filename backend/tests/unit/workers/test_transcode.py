"""Transcode worker: ffprobe/ffmpeg mocked; verify 60s guard + status flow."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.reel import Reel


def _seed_reel(db_session, storage_key: str = "reels/raw.mp4") -> Reel:  # noqa: ANN001
    from app.domain import user_service
    from app.infra.blob import blob_store
    from app.infra.db import ensure_schema
    from app.schemas.user import UserCreate

    ensure_schema()
    u = user_service.create_user(db_session, UserCreate(email="reel-owner@flo.dev", name="U"))
    # write a real file at the raw storage key so process_reel doesn't reject on missing file.
    blob_store.save_bytes(b"\x00\x00\x00fake", storage_key)
    r = Reel(user_id=u.id, status="processing", storage_key=storage_key)
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


def test_process_reel_marks_ready_when_short(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    reel = _seed_reel(db_session, "reels/short.mp4")
    from app.workers import transcode

    # Write bytes into the destination path so the transcoded outputs exist on disk.
    def _fake_transcode(_src, dst):  # noqa: ANN001
        dst.write_bytes(b"trans")
        return True

    def _fake_thumb(_src, dst):  # noqa: ANN001
        dst.write_bytes(b"thumb")
        return True

    monkeypatch.setattr(transcode, "_ffprobe_duration", lambda _p: 5.0)
    monkeypatch.setattr(transcode, "_ffmpeg_transcode", _fake_transcode)
    monkeypatch.setattr(transcode, "_ffmpeg_thumb", _fake_thumb)

    transcode.process_reel(reel.id)
    db_session.expire_all()
    updated = db_session.get(Reel, reel.id)
    assert updated is not None
    assert updated.status == "ready"
    assert updated.duration_seconds == 5.0
    assert updated.storage_key == f"reels/{reel.id}.mp4"
    assert updated.thumbnail_key == f"reels/{reel.id}.jpg"
    assert updated.video_url and updated.video_url.startswith("/media/blob?")


def test_process_reel_rejects_over_max_duration(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    """Any duration above `transcode.MAX_DURATION_SEC` (currently 60.5s) is rejected."""
    reel = _seed_reel(db_session, "reels/long.mp4")
    from app.workers import transcode

    over_limit = transcode.MAX_DURATION_SEC + 10.0
    monkeypatch.setattr(transcode, "_ffprobe_duration", lambda _p: over_limit)
    monkeypatch.setattr(transcode, "_ffmpeg_transcode", lambda _s, _d: True)
    monkeypatch.setattr(transcode, "_ffmpeg_thumb", lambda _s, _d: True)

    transcode.process_reel(reel.id)
    db_session.expire_all()
    updated = db_session.get(Reel, reel.id)
    assert updated is not None
    assert updated.status == "rejected"
    assert "exceeds" in (updated.error or "")


def test_process_reel_accepts_15_seconds_after_bump(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    """Regression: with the 60s bump, mid-length (~15s) reels must go through."""
    reel = _seed_reel(db_session, "reels/mid.mp4")
    from app.workers import transcode

    def _fake_transcode(_src, dst):  # noqa: ANN001
        dst.write_bytes(b"trans")
        return True

    def _fake_thumb(_src, dst):  # noqa: ANN001
        dst.write_bytes(b"thumb")
        return True

    monkeypatch.setattr(transcode, "_ffprobe_duration", lambda _p: 15.0)
    monkeypatch.setattr(transcode, "_ffmpeg_transcode", _fake_transcode)
    monkeypatch.setattr(transcode, "_ffmpeg_thumb", _fake_thumb)

    transcode.process_reel(reel.id)
    db_session.expire_all()
    updated = db_session.get(Reel, reel.id)
    assert updated is not None
    assert updated.status == "ready"
    assert updated.duration_seconds == 15.0


def test_process_reel_rejects_on_ffmpeg_failure(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    reel = _seed_reel(db_session, "reels/fail.mp4")
    from app.workers import transcode

    monkeypatch.setattr(transcode, "_ffprobe_duration", lambda _p: 5.0)
    monkeypatch.setattr(transcode, "_ffmpeg_transcode", lambda _s, _d: False)
    monkeypatch.setattr(transcode, "_ffmpeg_thumb", lambda _s, _d: False)

    transcode.process_reel(reel.id)
    db_session.expire_all()
    updated = db_session.get(Reel, reel.id)
    assert updated is not None
    assert updated.status == "rejected"
    assert updated.error == "transcode failed"


def test_process_reel_missing_raw_file(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    """Simulate a stray Reel row with no on-disk raw upload — must be flagged."""
    from app.domain import user_service
    from app.infra.db import ensure_schema
    from app.schemas.user import UserCreate
    from app.workers import transcode

    ensure_schema()
    u = user_service.create_user(db_session, UserCreate(email="missing@flo.dev", name="U"))
    reel = Reel(user_id=u.id, status="processing", storage_key="reels/does-not-exist.mp4")
    db_session.add(reel)
    db_session.commit()

    # Nothing else to mock — file simply isn't there.
    transcode.process_reel(reel.id)
    db_session.expire_all()
    updated = db_session.get(Reel, reel.id)
    assert updated is not None
    assert updated.status == "rejected"
    assert updated.error == "raw file missing"


def test_ffprobe_duration_uses_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`_ffprobe_duration` shells out to ffprobe — verify the mocked call path."""
    from app.workers import transcode

    monkeypatch.setattr(transcode.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    fake_output = json.dumps({"format": {"duration": "7.5"}}).encode()

    def _check_output(cmd, *_a, **_kw):  # noqa: ANN001, ARG001
        return fake_output

    monkeypatch.setattr(transcode.subprocess, "check_output", _check_output)
    dur = transcode._ffprobe_duration(tmp_path / "x.mp4")
    assert dur == 7.5


def test_ffprobe_duration_none_when_no_ffprobe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.workers import transcode

    monkeypatch.setattr(transcode.shutil, "which", lambda _name: None)
    assert transcode._ffprobe_duration(tmp_path / "x.mp4") is None


def test_ffmpeg_transcode_falls_back_to_copy_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No ffmpeg installed → just copy the source over so the reel is still playable."""
    from app.workers import transcode

    src = tmp_path / "in.mp4"
    dst = tmp_path / "out.mp4"
    src.write_bytes(b"payload")
    monkeypatch.setattr(transcode.shutil, "which", lambda _name: None)
    assert transcode._ffmpeg_transcode(src, dst) is True
    assert dst.read_bytes() == b"payload"


def test_ffmpeg_transcode_returns_false_on_subprocess_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.workers import transcode

    src = tmp_path / "in.mp4"
    src.write_bytes(b"payload")
    monkeypatch.setattr(transcode.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    def _bad(*_a, **_kw):  # noqa: ANN001, ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(transcode.subprocess, "check_call", _bad)
    assert transcode._ffmpeg_transcode(src, tmp_path / "out.mp4") is False
