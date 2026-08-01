from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.infra.config import get_settings
from app.infra.db import ensure_interaction_uniqueness, readyz_check, refresh_ai_views
from app.infra.scheduler import register_job, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def _register_beats() -> None:
    """Wire APScheduler jobs. Guarded by soft-import of apscheduler in scheduler.py."""
    from app.workers.beats import (
        beat_event_starting_soon,
        beat_nightly_matches,
        beat_pulse_snapshot,
    )

    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except Exception:  # pragma: no cover
        return

    register_job(beat_pulse_snapshot, trigger=IntervalTrigger(seconds=5), id="pulse", replace_existing=True)
    register_job(
        beat_event_starting_soon, trigger=IntervalTrigger(seconds=60), id="event_soon", replace_existing=True
    )
    register_job(
        beat_nightly_matches, trigger=CronTrigger(hour=3, minute=0), id="nightly_matches", replace_existing=True
    )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    logger.info("Flo backend starting up")
    # Keep AI read-only views in sync with the current schema so a hot-reloaded
    # backend picks up any widening (e.g. ai_public_events_full) without needing
    # a fresh migration or db reset.
    try:
        refresh_ai_views()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("refresh_ai_views failed at startup: %s", exc)
    try:
        ensure_interaction_uniqueness()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("ensure_interaction_uniqueness failed at startup: %s", exc)
    _register_beats()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Flo backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Flo Companion Backend",
        version="0.1.0",
        description="FastAPI + SQLite + sqlite-vec backend for the Flo event companion.",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    def readyz() -> dict:
        db_ok = readyz_check()
        return {"status": "ok" if db_ok else "degraded", "db": db_ok}

    _register_routers(app)
    _register_frontend(app, settings.FRONTEND_WEB_DIR)
    return app


def _register_frontend(app: FastAPI, frontend_dir_setting: str) -> None:
    """Serve the built Flutter web bundle from `frontend_dir_setting`, if it exists.

    Mounted at "/" AFTER every API router so Starlette's ordered matcher resolves
    `/healthz`, `/users`, `/docs`, `/openapi.json`, etc. first and only falls through
    to the static mount for unknown paths. `html=True` makes StaticFiles serve
    `index.html` for the bare "/" request.
    """
    if not frontend_dir_setting:
        return
    frontend_dir = Path(frontend_dir_setting)
    index_file = frontend_dir / "index.html"
    if not index_file.is_file():
        logger.warning("FRONTEND_WEB_DIR=%s is set but has no index.html; skipping.", frontend_dir)
        return

    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info("Serving Flutter web bundle from %s", frontend_dir)


def _register_routers(app: FastAPI) -> None:
    from app.api import (
        admin,
        ai,
        auth,
        chat,
        events,
        ingest,
        interests,
        media,
        missions,
        notifications,
        pulse,
        recommendations,
        reels,
        speakers,
        users,
    )

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(interests.router)
    app.include_router(speakers.router)
    app.include_router(events.router)
    app.include_router(ingest.router)
    app.include_router(reels.router)
    app.include_router(media.router)
    app.include_router(recommendations.router)
    app.include_router(chat.router)
    app.include_router(notifications.router)
    app.include_router(ai.router)
    app.include_router(missions.router)
    app.include_router(pulse.router)
    app.include_router(admin.router)


app = create_app()
