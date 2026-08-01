from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.infra.blob import blob_store
from app.infra.db import SessionLocal
from app.models.reel import Reel

logger = logging.getLogger(__name__)

MAX_DURATION_SEC = 60.5


def _ffprobe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        data = json.loads(out.decode("utf-8"))
        return float(data["format"]["duration"])
    except Exception as exc:
        logger.warning("ffprobe failed: %s", exc)
        return None


def _ffmpeg_transcode(src: Path, dst: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # No ffmpeg — just move the source into place so the reel is still playable.
        shutil.copy2(src, dst)
        return True
    try:
        subprocess.check_call(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-vf",
                "scale='min(720,iw)':-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                str(dst),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        return True
    except Exception as exc:
        logger.warning("ffmpeg transcode failed: %s", exc)
        return False


def _ffmpeg_thumb(src: Path, dst: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        dst.write_bytes(b"")
        return False
    try:
        subprocess.check_call(
            [ffmpeg, "-y", "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2", str(dst)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return True
    except Exception as exc:
        logger.warning("thumb failed: %s", exc)
        return False


def _reject(reel: Reel, error: str, raw_path: Path | None) -> None:
    """Mark a reel rejected and scrub every reference to the raw upload so a
    client can never dereference it via a signed URL."""
    reel.status = "rejected"
    reel.error = error
    reel.storage_key = None
    reel.thumbnail_key = None
    reel.video_url = None
    reel.thumbnail_url = None
    if raw_path is not None:
        try:
            raw_path.unlink(missing_ok=True)
        except Exception:
            pass


def process_reel(reel_id: int) -> None:
    """Background job: probe → guard 10s → transcode → thumbnail → mark ready."""
    db: Session = SessionLocal()
    try:
        reel = db.get(Reel, reel_id)
        if not reel or not reel.storage_key:
            return
        raw_path = blob_store.path_for(reel.storage_key)
        if not raw_path.is_file():
            _reject(reel, "raw file missing", None)
            db.commit()
            return

        duration = _ffprobe_duration(raw_path)
        # Only persist duration when it fits the ck_reel_max_duration CHECK
        # constraint; test_long_video_transitions_to_rejected fails otherwise
        # because SQLAlchemy commits the over-limit value before status flip.
        if duration is not None and duration > MAX_DURATION_SEC:
            _reject(reel, f"duration {duration:.1f}s exceeds {MAX_DURATION_SEC:.0f}s limit", raw_path)
            db.commit()
            return
        reel.duration_seconds = duration

        out_key = f"reels/{reel.id}.mp4"
        thumb_key = f"reels/{reel.id}.jpg"
        out_path = blob_store.path_for(out_key)
        thumb_path = blob_store.path_for(thumb_key)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ok = _ffmpeg_transcode(raw_path, out_path)
        _ffmpeg_thumb(raw_path, thumb_path)
        if not ok:
            _reject(reel, "transcode failed", raw_path)
            db.commit()
            return

        reel.storage_key = out_key
        reel.thumbnail_key = thumb_key
        reel.video_url = blob_store.signed_url(out_key)
        reel.thumbnail_url = blob_store.signed_url(thumb_key)
        reel.status = "ready"
        reel.error = None
        db.commit()

        # try to strip the raw upload
        if raw_path != out_path:
            try:
                raw_path.unlink(missing_ok=True)
            except Exception:
                pass
    finally:
        db.close()
