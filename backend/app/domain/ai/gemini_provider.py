from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.domain.ai.stub_provider import StubProvider

logger = logging.getLogger(__name__)

# Uses the current `google-genai` SDK (successor to the EOL `google-generativeai`).
# Talks to Gemini API v1 by default, so all live model names work.
#
# This adapter is CHAT-ONLY. Embeddings are handled by the local ONNX-based
# LocalEmbedProvider (see `local_embed_provider.py`) — no Gemini quota is
# consumed for vector search anywhere in the app. If a Gemini chat model is
# unavailable (bad key, quota exhausted, model retired), we walk a fallback
# chain and, on total failure, latch to the deterministic stub so a broken
# cloud credential can't crash or spam a running dev session.

_CHAT_FALLBACK_CHAIN: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-1.5-flash-latest",
)


def _strip_prefix(name: str) -> str:
    """`google-genai` accepts either `models/xxx` or bare `xxx`; keep it bare."""
    n = (name or "").strip()
    return n[len("models/"):] if n.startswith("models/") else n


class GeminiProvider:
    """Google Gemini chat adapter. Falls back to stub if the SDK / API is
    unavailable. Does NOT do embeddings — use `get_embedder()` for that."""

    name = "gemini"

    def __init__(self, api_key: str, chat_model: str) -> None:
        self._api_key = api_key
        self._chat_model_name = _strip_prefix(chat_model)
        self._fallback = StubProvider()
        self._client = None
        self._chat_broken = False
        self._chat_model_resolved: str | None = None
        try:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=api_key)
        except Exception as exc:
            logger.warning(
                "google-genai SDK unavailable, falling back to stub: %s", exc
            )

    def _list_available_models(self) -> list[str]:
        """Best-effort catalog dump for the current API key."""
        if not self._client:
            return []
        try:
            models = self._client.models.list()
            names: list[str] = []
            for m in models:
                n = getattr(m, "name", "") or ""
                if n:
                    names.append(_strip_prefix(n))
            return names
        except Exception as exc:
            logger.info("Gemini models.list() also failed: %s", exc)
            return []

    def _resolve_chat_model(self, probe_prompt: str = "hi") -> tuple[str | None, list[tuple[str, str]]]:
        if self._chat_model_resolved is not None:
            return self._chat_model_resolved, []
        if not self._client:
            return None, []
        candidates = [self._chat_model_name, *(m for m in _CHAT_FALLBACK_CHAIN
                                               if m != self._chat_model_name)]
        # Also probe whatever models the key actually advertises. This catches
        # cases where a key only has access to preview / private models.
        catalog = [
            n for n in self._list_available_models()
            if "flash" in n.lower() or "pro" in n.lower()
        ]
        for extra in catalog:
            if extra not in candidates:
                candidates.append(extra)

        failures: list[tuple[str, str]] = []
        for candidate in candidates:
            name = _strip_prefix(candidate)
            if not name:
                continue
            try:
                self._client.models.generate_content(model=name, contents=probe_prompt)
                logger.info("Gemini chat model resolved to %s", name)
                self._chat_model_resolved = name
                return name, failures
            except Exception as exc:
                failures.append((name, str(exc).splitlines()[0]))
                continue
        return None, failures

    def _ensure_chat_ready(self) -> bool:
        if self._chat_broken or not self._client:
            return False
        if self._chat_model_resolved is not None:
            return True
        model, failures = self._resolve_chat_model()
        if model is None:
            details = "; ".join(f"{n}: {err}" for n, err in failures) or "no candidates"
            available = self._list_available_models()
            available_str = ", ".join(available) if available else "<none returned>"
            logger.warning(
                "Gemini chat unavailable, permanently using stub for this process.\n"
                "  Per-model failures: %s\n"
                "  Models the API key CAN access: %s",
                details,
                available_str,
            )
            self._chat_broken = True
            return False
        return True

    @staticmethod
    def _join_messages(messages: list[dict[str, str]]) -> str:
        return "\n".join(
            f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages
        )

    def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
        if not self._ensure_chat_ready():
            return self._fallback.chat(messages)
        try:
            res = self._client.models.generate_content(
                model=self._chat_model_resolved,
                contents=self._join_messages(messages),
            )
            return getattr(res, "text", "") or self._fallback.chat(messages)
        except Exception as exc:
            logger.warning(
                "Gemini chat failed (%s); permanently falling back to stub for this process.",
                exc,
            )
            self._chat_broken = True
            return self._fallback.chat(messages)

    async def chat_stream(self, messages: list[dict[str, str]], **_: Any) -> AsyncIterator[str]:
        if not self._ensure_chat_ready():
            async for chunk in self._fallback.chat_stream(messages):
                yield chunk
            return
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._chat_model_resolved,
                contents=self._join_messages(messages),
            )
            async for chunk in stream:
                text = getattr(chunk, "text", "")
                if text:
                    yield text
        except Exception as exc:
            logger.warning(
                "Gemini stream failed (%s); permanently falling back to stub for this process.",
                exc,
            )
            self._chat_broken = True
            async for chunk in self._fallback.chat_stream(messages):
                yield chunk

    def chat_with_tools(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], **_: Any
    ) -> dict[str, Any]:
        return self._fallback.chat_with_tools(messages, tools)

    def generate_short_text(self, prompt: str, max_words: int = 30) -> str:
        text = self.chat([{"role": "user", "content": prompt}])
        words = text.strip().split()[:max_words]
        return " ".join(words) if words else self._fallback.generate_short_text(prompt, max_words)
