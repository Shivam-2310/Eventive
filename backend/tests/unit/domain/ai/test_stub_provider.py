"""StubProvider: deterministic EMBED_DIM embeddings + templated chat."""
from __future__ import annotations

import asyncio


def test_embed_batch_deterministic_and_unit_norm(stub_provider) -> None:  # noqa: ANN001
    from app.domain.ai.llm_provider import EMBED_DIM

    vecs = stub_provider.embed_batch(["hello world", "hello world", "different"])
    assert all(len(v) == EMBED_DIM for v in vecs)
    # Identical inputs → identical outputs.
    assert vecs[0] == vecs[1]
    assert vecs[0] != vecs[2]
    # Normalized to unit length (within float epsilon).
    norm_sq = sum(x * x for x in vecs[0])
    assert abs(norm_sq - 1.0) < 1e-6


def test_embed_batch_case_insensitive(stub_provider) -> None:  # noqa: ANN001
    """The stub lowercases + strips before hashing, so 'X' and 'x' collide."""
    a, b = stub_provider.embed_batch(["Hello", "hello"])
    assert a == b


def test_chat_echoes_last_user_message(stub_provider) -> None:  # noqa: ANN001
    out = stub_provider.chat([
        {"role": "system", "content": "s"},
        {"role": "user", "content": "how are you"},
    ])
    assert "how are you" in out
    assert out.startswith("[stub-llm] echo:")


def test_chat_stream_yields_tokens(stub_provider) -> None:  # noqa: ANN001
    async def _collect() -> list[str]:
        out: list[str] = []
        async for chunk in stub_provider.chat_stream([{"role": "user", "content": "hi"}]):
            out.append(chunk)
        return out

    chunks = asyncio.run(_collect())
    assert chunks
    assert "".join(chunks).strip().startswith("[stub-llm]")


def test_chat_with_tools_classifies_intent(stub_provider) -> None:  # noqa: ANN001
    """Keyword-based tiny classifier — hardcoded branches for the demo."""
    q1 = stub_provider.chat_with_tools([{"role": "user", "content": "how many events today"}], [])
    q2 = stub_provider.chat_with_tools([{"role": "user", "content": "like event 3"}], [])
    q3 = stub_provider.chat_with_tools([{"role": "user", "content": "tell me about AI safety"}], [])
    assert q1["intent"] == "structured_query"
    assert q2["intent"] == "action"
    assert q3["intent"] == "semantic_search"


def test_generate_short_text_is_prompt_derived(stub_provider) -> None:  # noqa: ANN001
    a = stub_provider.generate_short_text("Talk about AI safety and eval")
    b = stub_provider.generate_short_text("Talk about AI safety and eval")
    c = stub_provider.generate_short_text("Something else")
    assert a == b
    assert a != c
    assert a.startswith("A live session — ")
