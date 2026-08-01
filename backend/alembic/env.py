from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

import sqlite_vec
from alembic import context
from sqlalchemy import engine_from_config, event, pool

# Make the `app` package importable when Alembic is invoked from `backend/`.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infra.config import get_settings  # noqa: E402
from app.infra.db import Base  # noqa: E402
from app import models  # noqa: F401,E402  (register models on Base.metadata)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

settings = get_settings()
_db_url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def _install_sqlite_vec(dbapi_conn) -> None:  # noqa: ANN001
    try:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
    except Exception:
        pass


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        _install_sqlite_vec(dbapi_conn)
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA foreign_keys=ON")
        finally:
            cur.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
