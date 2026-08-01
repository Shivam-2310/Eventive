from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any, Protocol, runtime_checkable

# Dimension of every stored embedding across the app. sqlite-vec tables are
# typed by dimension, so this must match Alembic revision 004_local_embeddings
# and the model loaded by LocalEmbedProvider (bge-small-en-v1.5 → 384).
EMBED_DIM = 384


@runtime_checkable
class EmbedProvider(Protocol):
    """Embedding-only interface. Used by workers/embeddings.py and everything
    that hits sqlite-vec (matching_service, RAG, reel ranking)."""

    name: str

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]: ...


@runtime_checkable
class ChatProvider(Protocol):
    """Chat/completion-only interface. Used by FloBot, NL2SQL, and the LLM
    reason decorator in matching_service."""

    name: str

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    async def chat_stream(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]: ...

    def chat_with_tools(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]: ...

    def generate_short_text(self, prompt: str, max_words: int = 30) -> str: ...


@runtime_checkable
class LLMProvider(EmbedProvider, ChatProvider, Protocol):
    """Combined interface, retained for the StubProvider which trivially
    satisfies both halves."""


_chat_provider: ChatProvider | None = None
_embed_provider: EmbedProvider | None = None


def get_provider() -> ChatProvider:
    """Return the configured chat provider (Gemini if configured, else stub).

    Kept named `get_provider()` for back-compat with the many call sites that
    predate the embed/chat split.
    """
    global _chat_provider
    if _chat_provider is not None:
        return _chat_provider
    from app.infra.config import get_settings

    settings = get_settings()
    kind = (settings.LLM_PROVIDER or "stub").lower()
    if kind == "gemini" and settings.GEMINI_API_KEY:
        try:
            from app.domain.ai.gemini_provider import GeminiProvider

            _chat_provider = GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_CHAT_MODEL)
            return _chat_provider
        except Exception:
            pass
    from app.domain.ai.stub_provider import StubProvider

    _chat_provider = StubProvider()
    return _chat_provider


def get_embedder() -> EmbedProvider:
    """Return the configured embedding provider.

    Defaults to the local ONNX embedder (network-free, no quotas). Falls back
    to StubProvider only when the fastembed import blows up (e.g. missing
    system libs in a stripped-down test container) so we never crash the app
    on startup just because the ML deps couldn't load.
    """
    global _embed_provider
    if _embed_provider is not None:
        return _embed_provider
    from app.infra.config import get_settings

    settings = get_settings()
    kind = (settings.EMBED_PROVIDER or "local").lower()
    if kind == "local":
        try:
            from app.domain.ai.local_embed_provider import LocalEmbedProvider

            _embed_provider = LocalEmbedProvider(settings.EMBED_MODEL_NAME, EMBED_DIM)
            return _embed_provider
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "LocalEmbedProvider failed to initialise (%s); falling back to StubProvider.",
                exc,
            )
    from app.domain.ai.stub_provider import StubProvider

    _embed_provider = StubProvider()
    return _embed_provider


def reset_provider() -> None:
    global _chat_provider, _embed_provider
    _chat_provider = None
    _embed_provider = None
