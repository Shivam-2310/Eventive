"""Shared fixtures for the Eventive backend test suite.

Every test starts from a fresh SQLite file under ``tmp_path``, a fresh
``DATA_DIR`` and ``LLM_PROVIDER=stub`` so nothing ever hits Gemini or leaks
state between tests. The ``_isolated_env`` fixture is ``autouse=True`` and
runs before every test; it also clears the cached ``Settings`` singleton and
disposes the module-level SQLAlchemy engine via the ``reset_engine_for_tests``
hook in :mod:`app.infra.db`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Rewire the whole app to a throwaway SQLite file + DATA_DIR per test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_url = f"sqlite:///{(data_dir / 'eventive.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    # Ensure the LangChain Ask Eventive agent (app/domain/ai/agent.py) stays
    # unavailable in tests so the deterministic router runs. Otherwise a
    # locally-set GROQ_API_KEY / GEMINI_API_KEY would silently swap the router
    # onto a network path.
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    # Force the stub embedder in tests: keeps them offline, deterministic, and
    # side-steps the ~50 MB fastembed model download that would otherwise fire
    # the first time any test hits `embed_batch`.
    monkeypatch.setenv("EMBED_PROVIDER", "stub")
    monkeypatch.setenv("SEED_DEMO_FIXTURES", "true")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@eventive.dev")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "admin")
    monkeypatch.setenv("MEDIA_SIGNING_SECRET", "test-media-secret")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    # Invalidate cached settings + rebuild engine bound to the new DATABASE_URL.
    from app.domain.ai import agent as _agent
    from app.domain.ai import llm_provider as _llm
    from app.infra import config as _cfg
    from app.infra import db as _db

    _cfg.get_settings.cache_clear()
    _db.reset_engine_for_tests()
    _llm.reset_provider()
    _agent.reset_llm()

    yield data_dir


@pytest.fixture
def tmp_data_dir(_isolated_env: Path) -> Path:
    """Alias for the isolated DATA_DIR (already created)."""
    return _isolated_env


@pytest.fixture
def db_session():
    """Yield a fresh SQLAlchemy session with the full schema created."""
    from app.infra.db import SessionLocal, ensure_schema

    ensure_schema()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):  # noqa: ANN001, ARG001
    """FastAPI TestClient bound to the app; ensures schema is created first.

    We intentionally instantiate ``TestClient(app)`` without the context-manager
    form so FastAPI's lifespan (which would spin up APScheduler in-process) is
    skipped — the E2E smoke test uses the same shortcut.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def seeded(db_session) -> dict:  # noqa: ANN001, ARG001
    """Run the full seed pipeline and return the stats dict."""
    from app.scripts.seed import seed_all

    return seed_all()


@pytest.fixture
def stub_provider():
    """Return a fresh StubProvider instance for direct-call tests."""
    from app.domain.ai.stub_provider import StubProvider

    return StubProvider()
