from __future__ import annotations

import asyncio
import hashlib
import struct
from collections.abc import AsyncIterator, Iterable
from typing import Any

from app.domain.ai.llm_provider import EMBED_DIM


class StubProvider:
    """Deterministic zero-network provider. Same input → same output.

    Embeddings are SHA-256 seeded floats in [-1, 1]. Chat responses are
    templated. Good enough for demo mode + tests, and never needs an API key.
    """

    name = "stub"

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> list[float]:
        text = (text or "").strip().lower()
        seed = hashlib.sha256(text.encode()).digest()
        vec: list[float] = []
        i = 0
        while len(vec) < EMBED_DIM:
            block = hashlib.sha256(seed + i.to_bytes(4, "little")).digest()
            for j in range(0, len(block), 4):
                if len(vec) >= EMBED_DIM:
                    break
                (u,) = struct.unpack("<I", block[j : j + 4])
                vec.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
            i += 1
        # normalize
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
        user_msg = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        return f"[stub-llm] echo: {user_msg[:200]}"

    async def chat_stream(self, messages: list[dict[str, str]], **_: Any) -> AsyncIterator[str]:
        full = self.chat(messages)
        for word in full.split(" "):
            yield word + " "
            await asyncio.sleep(0.01)

    def chat_with_tools(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], **_: Any
    ) -> dict[str, Any]:
        user_msg = next((m.get("content", "").lower() for m in reversed(messages) if m.get("role") == "user"), "")
        # tiny keyword classifier — good enough for demo
        if any(k in user_msg for k in ("how many", "count", "list", "which events", "when does", "starts after")):
            return {"intent": "structured_query", "text": "", "tool": None}
        if any(k in user_msg for k in ("like ", "rsvp", "save event", "open match", "message ")):
            return {"intent": "action", "text": "", "tool": None}
        return {"intent": "semantic_search", "text": "", "tool": None}

    def generate_short_text(self, prompt: str, max_words: int = 30) -> str:
        # produce a stable, prompt-derived blurb
        seed = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        words = prompt.strip().split()[:max_words]
        return "A live session — " + " ".join(words[:max_words]) + f" (#{seed})"
