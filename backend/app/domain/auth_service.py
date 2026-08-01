"""Auth service — bcrypt + JWT + server-side refresh-token revocation.

Design constraints:

- `POST /users` (Phase 1) is intentionally left in place so existing tooling and
  the earlier smoke test paths keep working; new UI clients should call
  `POST /auth/register` instead which additionally issues token pairs.
- Every existing REST endpoint that takes `user_id` as a query/path parameter
  is left untouched — this module adds *additive* auth on top so JWT-aware
  clients can adopt gradually. `get_current_user` is available as a FastAPI
  dependency for endpoints that want to enforce authentication.
"""

from __future__ import annotations

from datetime import datetime

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import user_service
from app.infra.config import get_settings
from app.infra.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_jti,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair
from app.schemas.user import UserCreate, UserRead


class AuthError(Exception):
    """Raised when auth fails; the API layer turns this into a 401."""


def _issue_pair(db: Session, user: User, *, user_agent: str | None = None) -> TokenPair:
    settings = get_settings()
    access_token, access_exp = create_access_token(user.id, is_admin=user.is_admin)
    refresh_token, jti, refresh_exp = create_refresh_token(user.id)
    row = RefreshToken(
        user_id=user.id,
        jti_hash=hash_jti(jti),
        expires_at=refresh_exp.replace(tzinfo=None) if refresh_exp.tzinfo else refresh_exp,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    db.commit()
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TTL_MIN * 60,
        user=UserRead.model_validate(user),
    )


def register(db: Session, payload: RegisterRequest, *, user_agent: str | None = None) -> TokenPair:
    if user_service.get_by_email(db, payload.email):
        raise AuthError("email already registered")
    user_payload = UserCreate(
        email=payload.email,
        name=payload.name,
        headline=payload.headline,
        company=payload.company,
        role=payload.role,
        timezone=payload.timezone,
        blurb=payload.blurb,
    )
    user = user_service.create_user(db, user_payload)
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return _issue_pair(db, user, user_agent=user_agent)


def login(db: Session, payload: LoginRequest, *, user_agent: str | None = None) -> TokenPair:
    user = user_service.get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthError("invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()
    return _issue_pair(db, user, user_agent=user_agent)


def refresh(db: Session, refresh_token: str, *, user_agent: str | None = None) -> TokenPair:
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("refresh token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("invalid refresh token") from exc

    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        raise AuthError("invalid refresh token")

    row = db.execute(
        select(RefreshToken).where(RefreshToken.jti_hash == hash_jti(jti))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise AuthError("refresh token revoked")
    if row.expires_at < datetime.utcnow():
        raise AuthError("refresh token expired")

    user = db.get(User, int(sub))
    if not user:
        raise AuthError("user no longer exists")

    row.revoked_at = datetime.utcnow()
    row.last_used_at = datetime.utcnow()
    db.commit()

    return _issue_pair(db, user, user_agent=user_agent)


def logout(db: Session, refresh_token: str | None) -> None:
    """Best-effort revocation; never raise on unknown/expired tokens."""
    if not refresh_token:
        return
    try:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    if not jti:
        return
    row = db.execute(
        select(RefreshToken).where(RefreshToken.jti_hash == hash_jti(jti))
    ).scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()


def logout_all(db: Session, user_id: int) -> int:
    """Revoke every active refresh token for a user. Returns count revoked."""
    now = datetime.utcnow()
    rows = db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).scalars().all()
    for row in rows:
        row.revoked_at = now
    db.commit()
    return len(rows)


def user_from_access_token(db: Session, token: str) -> User | None:
    try:
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    return db.get(User, int(sub))


def _access_token_from_request(request) -> str | None:  # noqa: ANN001
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header:
        # WebSocket upgrades can't send headers → accept ?access_token=...
        try:
            return request.query_params.get("access_token")
        except Exception:
            return None
    scheme, _, credentials = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return None
    return credentials.strip()


def _resolve_user_from_request(request, db: Session) -> User | None:  # noqa: ANN001
    token = _access_token_from_request(request)
    if not token:
        return None
    return user_from_access_token(db, token)
