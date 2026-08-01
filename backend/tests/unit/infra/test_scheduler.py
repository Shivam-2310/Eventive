"""Soft-imported APScheduler wrapper — must degrade gracefully if the dep is missing."""
from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_scheduler_module() -> None:
    """Restore module-level singletons between tests since we mutate them."""
    from app.infra import scheduler

    scheduler._scheduler = None
    scheduler._jobs = []
    yield
    scheduler._scheduler = None
    scheduler._jobs = []


def test_register_job_queues_without_starting() -> None:
    from app.infra import scheduler

    def _noop() -> None:
        return None

    scheduler.register_job(_noop, id="noop")
    assert len(scheduler._jobs) == 1
    assert scheduler._jobs[0][0] is _noop
    assert scheduler._jobs[0][1] == {"id": "noop"}


def test_start_scheduler_no_op_when_apscheduler_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If `apscheduler` fails to import, `start_scheduler` must return silently."""
    from app.infra import scheduler

    # Force the soft-import to fail.
    monkeypatch.setitem(sys.modules, "apscheduler", None)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.asyncio", None)

    scheduler.start_scheduler()
    assert scheduler._scheduler is None


def test_stop_scheduler_is_safe_when_never_started() -> None:
    """`stop_scheduler` is a no-op if `_scheduler is None` — safe to call unconditionally."""
    from app.infra import scheduler

    assert scheduler._scheduler is None
    scheduler.stop_scheduler()
    assert scheduler._scheduler is None


def test_start_scheduler_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second call while a scheduler is already active is a no-op."""
    from app.infra import scheduler

    class _StubScheduler:
        def add_job(self, *args: object, **kwargs: object) -> None:
            return None

        def start(self) -> None:
            return None

        def shutdown(self, wait: bool = False) -> None:  # noqa: ARG002
            return None

    scheduler._scheduler = _StubScheduler()
    # Should return early without touching apscheduler at all.
    scheduler.start_scheduler()
    assert isinstance(scheduler._scheduler, _StubScheduler)
