"""FastAPI dependencies. Kept in the api layer so it can freely reference `Depends`."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.domain import auth_service
from app.infra.db import get_db
from app.models.user import User


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Return the authenticated user if a valid Bearer token is present, else None."""
    return auth_service._resolve_user_from_request(request, db)


def require_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = auth_service._resolve_user_from_request(request, db)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_current_user(request, db)
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
