"""Password hashing (Phase 14: bcrypt with SHA-256 pre-hash for length safety).

Legacy `sha256$` hashes from the pre-Phase-14 era must still verify (backward
compat) but every new hash is bcrypt ($2b$).
"""
from __future__ import annotations

from app.infra.security import hash_password, needs_rehash, verify_password


def test_hash_and_verify_round_trip() -> None:
    h = hash_password("swordfish")
    assert h.startswith("$2b$")
    assert verify_password("swordfish", h) is True


def test_wrong_password_rejected() -> None:
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong", h) is False


def test_verify_handles_none_and_malformed() -> None:
    assert verify_password("x", None) is False
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-valid-hash") is False
    assert verify_password("x", "bcrypt$foo$bar") is False


def test_two_hashes_of_same_password_differ() -> None:
    """Random salt means back-to-back hashes should not be identical."""
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a) is True
    assert verify_password("same", b) is True


def test_password_longer_than_72_bytes_still_verifies() -> None:
    """bcrypt truncates at 72 bytes; the SHA-256 pre-hash step must sidestep that."""
    long_pw = "x" * 200
    h = hash_password(long_pw)
    assert verify_password(long_pw, h) is True
    # A different long password with the same first 72 chars must NOT collide.
    assert verify_password("x" * 199 + "y", h) is False


def test_legacy_sha256_hash_still_verifies_and_needs_rehash() -> None:
    """Users hashed under the pre-Phase-14 `sha256$SALT$DIGEST` scheme must still log in."""
    import hashlib
    import secrets

    salt = secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:legacy-pw".encode()).hexdigest()
    legacy = f"sha256${salt}${digest}"

    assert verify_password("legacy-pw", legacy) is True
    assert verify_password("nope", legacy) is False
    assert needs_rehash(legacy) is True
    assert needs_rehash(hash_password("fresh")) is False
