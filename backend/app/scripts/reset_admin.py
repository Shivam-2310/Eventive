"""CLI: reset admin password from ADMIN_EMAIL + ADMIN_INITIAL_PASSWORD env vars."""
from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.domain import user_service
from app.infra.config import get_settings
from app.infra.db import SessionLocal
from app.infra.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.email == settings.ADMIN_EMAIL)).scalar_one_or_none()
        if not admin:
            admin = user_service.create_user(
                db,
                UserCreate(email=settings.ADMIN_EMAIL, name="Flo Admin", is_admin=True),
            )
        admin.is_admin = True
        admin.password_hash = hash_password(settings.ADMIN_INITIAL_PASSWORD)
        db.commit()
        logger.info("admin reset for %s", settings.ADMIN_EMAIL)
        print("ok")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
