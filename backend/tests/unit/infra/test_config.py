"""Settings load + env override coverage (cross-cutting infra)."""
from __future__ import annotations

import pytest


def test_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    """When only the isolation env is set, sensible defaults are still present."""
    from app.infra.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.LLM_PROVIDER == "stub"
    assert s.ADMIN_EMAIL == "admin@flo.dev"
    assert s.PORT == 8000
    assert s.MEDIA_URL_TTL_SECONDS == 600
    # DATABASE_URL / DATA_DIR are overridden by _isolated_env for hermetic tests.
    assert s.DATABASE_URL.startswith("sqlite:///")
    assert s.DATA_DIR


def test_env_overrides_are_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars trump defaults; each `get_settings.cache_clear()` re-reads them."""
    from app.infra.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("MEDIA_URL_TTL_SECONDS", "42")
    get_settings.cache_clear()
    s = get_settings()
    assert s.LLM_PROVIDER == "gemini"
    assert s.MEDIA_URL_TTL_SECONDS == 42
    assert s.cors_origins_list == ["https://a.example", "https://b.example"]


def test_cors_origins_wildcard_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infra.config import get_settings

    monkeypatch.setenv("CORS_ORIGINS", "*")
    get_settings.cache_clear()
    assert get_settings().cors_origins_list == ["*"]

    monkeypatch.setenv("CORS_ORIGINS", "")
    get_settings.cache_clear()
    assert get_settings().cors_origins_list == ["*"]


def test_settings_are_cached() -> None:
    """`get_settings` is `lru_cache`d — two calls return the same object."""
    from app.infra.config import get_settings

    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
