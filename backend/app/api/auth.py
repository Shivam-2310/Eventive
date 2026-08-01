from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.domain import auth_service
from app.infra.db import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    try:
        return auth_service.register(db, payload, user_agent=_ua(request))
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    try:
        return auth_service.login(db, payload, user_agent=_ua(request))
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    try:
        return auth_service.refresh(db, payload.refresh_token, user_agent=_ua(request))
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    auth_service.logout(db, payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_200_OK)
def logout_all(
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
) -> dict:
    revoked = auth_service.logout_all(db, user.id)
    return {"revoked": revoked}


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(require_current_user)) -> UserRead:
    return UserRead.model_validate(user)
