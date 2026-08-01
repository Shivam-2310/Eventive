from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path

from app.infra.config import get_settings


class LocalBlobStore:
    """Local filesystem blob store with HMAC-signed URLs.

    Keys are relative paths like `reels/<uuid>.mp4`. Files are stored under
    `${DATA_DIR}/<key>`. `signed_url(key)` produces `/media/blob?k=<key>&t=<expiry>&s=<sig>`
    which the `/media` router validates on read.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.DATA_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        # Prevent directory traversal.
        key = key.replace("\\", "/").lstrip("/")
        if ".." in key.split("/"):
            raise ValueError("invalid key")
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError("path escapes root")
        return p

    def save_bytes(self, data: bytes, key: str) -> str:
        p = self.path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def save_stream(self, src, key: str) -> str:  # noqa: ANN001
        p = self.path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                f.write(chunk)
        return key

    def exists(self, key: str) -> bool:
        try:
            return self.path_for(key).is_file()
        except ValueError:
            return False

    def read_bytes(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self.path_for(key).unlink(missing_ok=True)
        except ValueError:
            pass

    def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        settings = get_settings()
        ttl = ttl_seconds or settings.MEDIA_URL_TTL_SECONDS
        expires_at = int(time.time()) + int(ttl)
        sig = self._sign(key, expires_at)
        return f"/media/blob?k={key}&t={expires_at}&s={sig}"

    def verify(self, key: str, expires_at: int, sig: str) -> bool:
        if expires_at < int(time.time()):
            return False
        expected = self._sign(key, expires_at)
        return hmac.compare_digest(expected, sig)

    def _sign(self, key: str, expires_at: int) -> str:
        secret = get_settings().MEDIA_SIGNING_SECRET.encode()
        mac = hmac.new(secret, f"{key}|{expires_at}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")


blob_store = LocalBlobStore()
