"""Auth primitives — bcrypt password hashing + PyJWT access/refresh tokens.

Uses the `bcrypt` package directly instead of going through `passlib`. Two
reasons for that:

1. `passlib 1.7.4` reads `bcrypt.__about__.__version__` at import to decide
   which backend to bind, and `bcrypt >= 4.0` removed that attribute — so
   `passlib` falls through to a self-test path that hashes a 400-byte string
   and immediately hits bcrypt's 72-byte limit, crashing at import time.
2. bcrypt has a hard 72-byte limit on the password. We pre-hash with SHA-256
   then base64-encode → always fits, still cryptographically fine (this is the
   pattern Django, Passlib's own `bcrypt_sha256`, and most modern stacks use).

Legacy sha256-only hashes produced by the earlier placeholder (`sha256$salt$digest`)
are still verified so the seeded admin from before Phase 14 keeps working;
`needs_rehash` flags them so the login flow upgrades them to bcrypt on the
next successful login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.infra.config import get_settings

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

_BCRYPT_ROUNDS = 12
_BCRYPT_PREFIX = "$2b$"


def _prepare(plain: str) -> bytes:
    """SHA-256 -> base64 to fit under bcrypt's 72-byte limit for arbitrary passwords."""
    if plain is None:
        raise ValueError("password must not be None")
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if not plain:
        raise ValueError("password must not be empty")
    hashed = bcrypt.hashpw(_prepare(plain), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """Verify plaintext against a stored hash.

    Accepts both new bcrypt hashes and legacy `sha256$salt$digest` hashes so
    the seeded admin (created before Phase 14) can still log in.
    """
    if not hashed or not plain:
        return False
    if hashed.startswith("sha256$"):
        try:
            _, salt, digest = hashed.split("$", 2)
        except ValueError:
            return False
        expected = hashlib.sha256(f"{salt}:{plain}".encode()).hexdigest()
        return hmac.compare_digest(expected, digest)
    if not hashed.startswith(_BCRYPT_PREFIX) and not hashed.startswith("$2a$") and not hashed.startswith("$2y$"):
        return False
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("ascii"))
    except Exception:
        return False


def needs_rehash(hashed: str | None) -> bool:
    """Return True if the stored hash should be upgraded (e.g. from legacy sha256)."""
    if not hashed:
        return False
    if hashed.startswith("sha256$"):
        return True
    # Optional: could inspect the bcrypt cost factor and upgrade if it's lower
    # than `_BCRYPT_ROUNDS`, but that's rarely worth the extra login latency.
    return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: int, *, is_admin: bool = False, extra: dict | None = None) -> tuple[str, datetime]:
    settings = get_settings()
    exp = _now() + timedelta(minutes=settings.JWT_ACCESS_TTL_MIN)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TOKEN_TYPE_ACCESS,
        "is_admin": bool(is_admin),
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token, exp


def create_refresh_token(user_id: int, *, jti: str | None = None) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = jti or uuid.uuid4().hex
    exp = _now() + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)
    payload = {
        "sub": str(user_id),
        "type": TOKEN_TYPE_REFRESH,
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token, jti, exp


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    """Decode + validate a JWT. Raises `jwt.PyJWTError` on any failure."""
    settings = get_settings()
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected token type {expected_type}, got {payload.get('type')}")
    return payload


def hash_jti(jti: str) -> str:
    """Store an opaque digest of the refresh-token jti, not the raw jti itself."""
    return hashlib.sha256(jti.encode()).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)
