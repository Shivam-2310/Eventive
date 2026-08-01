"""LLMProvider selection based on `LLM_PROVIDER` env + fallback to stub."""
from __future__ import annotations

import pytest


def test_stub_selected_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.ai import llm_provider as _llm
    from app.domain.ai.stub_provider import StubProvider
    from app.infra.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "stub")
    get_settings.cache_clear()
    _llm.reset_provider()
    p = _llm.get_provider()
    assert isinstance(p, StubProvider)
    assert p.name == "stub"


def test_gemini_fallback_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_PROVIDER=gemini` without `GEMINI_API_KEY` → stub."""
    from app.domain.ai import llm_provider as _llm
    from app.domain.ai.stub_provider import StubProvider
    from app.infra.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    _llm.reset_provider()
    p = _llm.get_provider()
    assert isinstance(p, StubProvider)


def test_gemini_selected_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_PROVIDER=gemini` + `GEMINI_API_KEY` → GeminiProvider.

    The provider's internal client falls back to stub when the SDK can't
    initialize, but the returned type is still GeminiProvider (name=='gemini').
    """
    from app.domain.ai import llm_provider as _llm
    from app.domain.ai.gemini_provider import GeminiProvider
    from app.infra.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-tests")
    get_settings.cache_clear()
    _llm.reset_provider()
    p = _llm.get_provider()
    # If the sdk failed to init (e.g. invalid key), the constructor still returns
    # a GeminiProvider; embed_batch etc. use the internal `_fallback` StubProvider.
    assert isinstance(p, GeminiProvider)
    assert p.name == "gemini"


def test_get_provider_is_cached() -> None:
    """Second call returns the exact same instance until `reset_provider()` is called."""
    from app.domain.ai import llm_provider as _llm

    _llm.reset_provider()
    a = _llm.get_provider()
    b = _llm.get_provider()
    assert a is b
    _llm.reset_provider()
    c = _llm.get_provider()
    assert c is not a
