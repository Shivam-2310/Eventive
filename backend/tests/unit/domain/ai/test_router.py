"""AI router: intent branches + composed answer + audit hooks."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.domain import user_service
from app.domain.ai import router as ai_router
from app.models.ai import AIMessage, AISession
from app.schemas.user import UserCreate


def _collect(gen) -> list[dict]:  # noqa: ANN001
    async def _run() -> list[dict]:
        out: list[dict] = []
        async for evt in gen:
            out.append(evt)
        return out

    return asyncio.run(_run())


def _force_intent(monkeypatch, intent: str) -> None:  # noqa: ANN001
    """Patch the provider's `chat_with_tools` classifier to force a branch."""
    from app.domain.ai import llm_provider as _llm

    _llm.reset_provider()
    provider = _llm.get_provider()

    def _chat_with_tools(messages, tools, **_):  # noqa: ANN001, ARG001
        return {"intent": intent, "text": "", "tool": None}

    monkeypatch.setattr(provider, "chat_with_tools", _chat_with_tools)


def test_semantic_search_branch_emits_citations(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="rt-sem@flo.dev", name="X"))
    _force_intent(monkeypatch, "semantic_search")
    events = _collect(ai_router.handle_chat_stream(db_session, user.id, "AI safety talks"))
    kinds = {e["event"] for e in events}
    assert "intent" in kinds
    assert "done" in kinds
    intent_evt = next(e for e in events if e["event"] == "intent")
    assert intent_evt["data"]["intent"] == "semantic_search"
    # some citations or chunks should have been emitted
    assert any(e["event"] in {"citation", "chunk"} for e in events)

    # Persisted user + assistant AI messages.
    session = db_session.execute(
        select(AISession).where(AISession.user_id == user.id).order_by(AISession.id.desc())
    ).scalars().first()
    assert session is not None
    msgs = db_session.execute(select(AIMessage).where(AIMessage.session_id == session.id)).scalars().all()
    roles = [m.role for m in msgs]
    assert "user" in roles and "assistant" in roles
    assistant = next(m for m in msgs if m.role == "assistant")
    assert assistant.intent == "semantic_search"


def test_structured_query_branch_uses_nl2sql(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="rt-sq@flo.dev", name="X"))
    _force_intent(monkeypatch, "structured_query")
    events = _collect(ai_router.handle_chat_stream(db_session, user.id, "how many events?"))
    sql_evt = next((e for e in events if e["event"] == "sql"), None)
    assert sql_evt is not None
    assert "sql" in sql_evt["data"]


def test_action_branch_executes_tool(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """When `intent=action` and message matches a known verb, `tools.parse_and_execute` runs."""
    from app.domain import event_service
    from app.schemas.event import EventCreate

    user = user_service.create_user(db_session, UserCreate(email="rt-act@flo.dev", name="X"))
    ev = event_service.create_event(db_session, EventCreate(title="Actionable"))
    _force_intent(monkeypatch, "action")

    events = _collect(ai_router.handle_chat_stream(db_session, user.id, f"like event {ev.id}"))
    tool_evt = next((e for e in events if e["event"] == "tool"), None)
    assert tool_evt is not None
    assert tool_evt["data"]["type"] == "like"


def test_action_branch_unmatched_message(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    """If no verb matches, the router still emits a helpful chunk."""
    user = user_service.create_user(db_session, UserCreate(email="rt-noact@flo.dev", name="X"))
    _force_intent(monkeypatch, "action")
    events = _collect(ai_router.handle_chat_stream(db_session, user.id, "just say hello"))
    chunks = [e for e in events if e["event"] == "chunk"]
    assert chunks


def test_audit_persistence_records_intent_and_retrieved(seeded, db_session, monkeypatch) -> None:  # noqa: ANN001, ARG001
    user = user_service.create_user(db_session, UserCreate(email="audit@flo.dev", name="X"))
    _force_intent(monkeypatch, "semantic_search")
    _collect(ai_router.handle_chat_stream(db_session, user.id, "any AI safety talks?"))
    msg = db_session.execute(
        select(AIMessage).where(AIMessage.role == "assistant").order_by(AIMessage.id.desc())
    ).scalars().first()
    assert msg is not None
    # retrieved_chunks JSON is optional but if present must parse.
    if msg.retrieved_chunks:
        parsed = json.loads(msg.retrieved_chunks)
        assert isinstance(parsed, list)


def test_suggestions_for_returns_diverse_prompts(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """The router seeds the Ask Flo prompt tray with a mix of intents so users
    discover both semantic and structured/personal queries."""
    user = user_service.create_user(db_session, UserCreate(email="sug@flo.dev", name="X"))
    out = ai_router.suggestions_for(db_session, user.id)
    assert len(out) >= 4
    intents = {s["intent"] for s in out}
    # Every seeded suggestion should include personal + structured intents,
    # and at least one of the discovery intents (semantic or event lookup).
    assert {"personal_query", "structured_query"}.issubset(intents)
    assert intents & {"semantic_search", "event_lookup"}


def test_event_vibe_caches_result(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    """`event_vibe` writes `vibe_text` and reuses it when hash unchanged."""
    from app.models.event import Event

    ev = db_session.execute(select(Event).order_by(Event.id).limit(1)).scalar_one()
    ev.vibe_text = None
    ev.vibe_source_hash = None
    db_session.commit()
    text1 = ai_router.event_vibe(db_session, ev.id)
    text2 = ai_router.event_vibe(db_session, ev.id)
    assert text1 == text2
    assert text1


def test_event_vibe_missing_event_returns_none(db_session) -> None:  # noqa: ANN001
    from app.infra.db import ensure_schema

    ensure_schema()
    assert ai_router.event_vibe(db_session, 999_999) is None
