"""APScheduler wiring (Phase 12).

Left as a soft-import stub so the app starts without the dep during earlier
phases. `start_scheduler()` becomes a no-op if `apscheduler` is not installed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_scheduler = None
_jobs: list[tuple[Callable, dict]] = []


def register_job(func: Callable, **kwargs) -> None:
    """Queue a job to be registered when the scheduler starts."""
    _jobs.append((func, kwargs))


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception:  # pragma: no cover
        logger.info("apscheduler not installed — scheduler disabled")
        return

    _scheduler = AsyncIOScheduler()
    for func, kw in _jobs:
        _scheduler.add_job(func, **kw)
    _scheduler.start()
    logger.info("APScheduler started with %s jobs", len(_jobs))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:  # pragma: no cover
        pass
    _scheduler = None
