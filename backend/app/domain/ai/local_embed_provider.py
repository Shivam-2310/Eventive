"""Local, network-free embedding provider backed by fastembed / ONNX Runtime.

Runs on CPU with a small quantized ONNX model (default: BAAI/bge-small-en-v1.5,
384-dim, ~50 MB). First initialisation downloads the model into fastembed's
on-disk cache (`~/.cache/fastembed/` by default); subsequent starts are
instant. In the Docker image we pre-download at build time so the container
never needs network access at startup.

Why this exists:
  * Removes the Gemini free-tier quota that used to kick in on every restart.
  * Keeps a single 384-dim vector shape across every code path (see EMBED_DIM
    in llm_provider.py). sqlite-vec tables are typed by dimension, so this
    number must match Alembic revision 004_local_embeddings.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


class LocalEmbedProvider:
    """Lazy-loaded singleton wrapper around `fastembed.TextEmbedding`.

    Model instantiation costs ~1–2s (parses the ONNX graph and vocab), so we
    do it once at first `embed_batch` call and reuse the loaded model for the
    lifetime of the process. Thread-safe via a lock — SQLAlchemy sessions can
    call this from any request thread.
    """

    name = "local"

    def __init__(self, model_name: str, expected_dim: int) -> None:
        self._model_name = model_name
        self._expected_dim = expected_dim
        self._model: Any = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                # Import lazily so the import cost is only paid when the
                # embedder is actually needed (tests that use StubProvider
                # never pull ONNX into the process).
                from fastembed import TextEmbedding  # type: ignore[import-not-found]

                logger.info("Loading local embedding model %s...", self._model_name)
                self._model = TextEmbedding(model_name=self._model_name)
                logger.info("Local embedding model %s ready.", self._model_name)
        return self._model

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        # Normalize to a concrete list so we can iterate multiple times and
        # produce a stable "empty" fallback when the caller passes no input.
        items = [(t or "").strip() for t in texts]
        if not items:
            return []
        # fastembed refuses genuinely-empty strings on some model variants;
        # substitute a single space so the batch keeps a stable length.
        safe = [t if t else " " for t in items]
        model = self._ensure_model()
        raw = list(model.embed(safe))
        out: list[list[float]] = []
        for vec in raw:
            values = [float(x) for x in vec]
            if len(values) != self._expected_dim:
                # Should never happen — fastembed's model card guarantees a
                # fixed dim — but pad/truncate defensively so sqlite-vec never
                # sees a wrong-length blob.
                if len(values) > self._expected_dim:
                    values = values[: self._expected_dim]
                else:
                    values = values + [0.0] * (self._expected_dim - len(values))
            out.append(values)
        return out
