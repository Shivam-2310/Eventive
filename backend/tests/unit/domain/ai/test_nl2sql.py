"""NL2SQL: SELECT-only guard + safe view execution.

The `_basic_guard` denylist rejects mutation keywords and metadata reads
regardless of the LLM output; safe SELECTs against `ai_public_events`
and `ai_public_speakers` should execute against the seeded DB.
"""
from __future__ import annotations

from app.domain.ai import nl2sql


def test_guard_rejects_mutations() -> None:
    for sql in (
        "DELETE FROM event",
        "UPDATE event SET title='x'",
        "INSERT INTO event(title) VALUES ('x')",
        "DROP TABLE event",
        "ALTER TABLE event ADD COLUMN x TEXT",
    ):
        err = nl2sql._basic_guard(sql)
        assert err is not None
        assert "forbidden" in err


def test_guard_requires_select() -> None:
    err = nl2sql._basic_guard("PRAGMA table_info('event')")
    assert err is not None


def test_guard_rejects_sqlite_meta() -> None:
    for sql in (
        "SELECT * FROM sqlite_master",
        "SELECT * FROM pragma_table_info('event')",
    ):
        err = nl2sql._basic_guard(sql)
        assert err is not None


def test_guard_rejects_disallowed_table() -> None:
    err = nl2sql._basic_guard("SELECT * FROM user")
    assert err is not None and "disallowed table/view" in err


def test_guard_allows_safe_view() -> None:
    assert nl2sql._basic_guard("SELECT id FROM ai_public_events LIMIT 5") is None
    assert nl2sql._basic_guard("SELECT id FROM ai_public_speakers") is None


def test_run_select_returns_rows(seeded: dict, db_session) -> None:  # noqa: ANN001, ARG001
    """The stub provider's `chat` returns the question text; the fallback SQL
    kicks in to produce a legitimate SELECT against the events view."""
    res = nl2sql.run(db_session, "How many events?")
    assert res["ok"] is True
    assert res["rows"]
    assert isinstance(res["rows"][0], dict)


def test_run_rejects_mutation_via_fallback(db_session) -> None:  # noqa: ANN001
    """Even if the LLM returned a mutation, the guard blocks execution before DB touch."""
    from app.domain.ai import llm_provider as _llm
    from app.infra.db import ensure_schema

    ensure_schema()

    class _MutationProvider:
        name = "test-mutant"  # non-stub, so `_fallback_sql` is not consulted

        def chat(self, messages, **_):  # noqa: ANN001, ARG002
            return "DELETE FROM event"

        async def chat_stream(self, messages, **_):  # noqa: ANN001, ARG002
            yield ""

        def chat_with_tools(self, messages, tools, **_):  # noqa: ANN001, ARG002
            return {"intent": "structured_query"}

        def generate_short_text(self, prompt, max_words: int = 30):  # noqa: ANN001, ARG002
            return ""

    _llm._chat_provider = _MutationProvider()
    try:
        res = nl2sql.run(db_session, "delete everything")
        assert res["ok"] is False
        assert "forbidden" in (res.get("error") or "")
    finally:
        _llm.reset_provider()


def test_fallback_counts_with_track(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    res = nl2sql.run(db_session, "how many events on the AI track?")
    assert res["ok"] is True
    assert "count" in res["columns"]
    assert res["rows"][0]["count"] > 0
    prose = nl2sql.summarize(res)
    assert "AI track" in prose


def test_fallback_events_today(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    res = nl2sql.run(db_session, "events today")
    assert res["ok"] is True
    prose = nl2sql.summarize(res)
    # either "Found N matching events" or "No results matched" — both are prose
    assert "row" not in prose.lower()  # legacy k=v dump had "matching rows"


def test_fallback_who_speaking_about_hits_full_view(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    res = nl2sql.run(db_session, "who's speaking about RAG?")
    assert res["ok"] is True
    assert "ai_public_events_full" in res["sql"]


def test_fallback_list_speakers(seeded, db_session) -> None:  # noqa: ANN001, ARG001
    res = nl2sql.run(db_session, "list all speakers")
    assert res["ok"] is True
    assert res["rows"], "seed should have ~20 speakers"


def test_summarize_count_prose_singular_plural() -> None:
    assert "There is 1 event" in nl2sql._count_prose(1, "SELECT COUNT(*) FROM ai_public_events")
    assert "There are 5 events" in nl2sql._count_prose(5, "SELECT COUNT(*) FROM ai_public_events")


def test_summarize_events_list_uses_bullets() -> None:
    res = {
        "ok": True,
        "sql": "SELECT id, title, track, start_time FROM ai_public_events",
        "columns": ["id", "title", "track", "start_time"],
        "rows": [
            {"id": 1, "title": "Talk A", "track": "AI", "start_time": "2026-07-11 09:00:00"},
            {"id": 2, "title": "Talk B", "track": "Infra", "start_time": "2026-07-11 10:15:00"},
        ],
    }
    prose = nl2sql.summarize(res)
    assert "Found 2 matching events" in prose
    assert "[event:1] Talk A" in prose
    assert "[event:2] Talk B" in prose
    # no k=v dumps
    assert "start_time=" not in prose


def test_summarize_empty_rows_is_polite() -> None:
    prose = nl2sql.summarize({"ok": True, "columns": ["id"], "rows": []})
    assert "No results matched" in prose


def test_stub_output_never_reaches_guard() -> None:
    """The Gemini adapter regresses to stub silently — the stub echo must be
    intercepted before the SQL guard sees it, otherwise every question yields
    an ugly `must contain SELECT` error."""
    from app.domain.ai import llm_provider as _llm

    class _StubEchoProvider:
        name = "stub"

        def chat(self, messages, **_):  # noqa: ANN001, ARG002
            return "[stub-llm] echo: schema hint garbage"

        async def chat_stream(self, messages, **_):  # noqa: ANN001, ARG002
            yield ""

        def chat_with_tools(self, messages, tools, **_):  # noqa: ANN001, ARG002
            return {"intent": "structured_query"}

        def generate_short_text(self, prompt, max_words: int = 30):  # noqa: ANN001, ARG002
            return ""

    from app.infra.db import SessionLocal, ensure_schema

    ensure_schema()
    _llm._chat_provider = _StubEchoProvider()
    try:
        assert nl2sql.provider_is_stub_output("[stub-llm] anything") is True
        session = SessionLocal()
        try:
            res = nl2sql.run(session, "list events")
        finally:
            session.close()
        assert res["ok"] is True
        assert "ai_public_events" in res["sql"]
    finally:
        _llm.reset_provider()


def test_generate_sql_strips_code_fences() -> None:
    """The provider's raw output is de-fenced before the guard."""
    from app.domain.ai import llm_provider as _llm

    class _FencedProvider:
        name = "stub"

        def chat(self, messages, **_):  # noqa: ANN001, ARG002
            return "```sql\nSELECT id FROM ai_public_events LIMIT 5\n```"

        async def chat_stream(self, messages, **_):  # noqa: ANN001, ARG002
            yield ""

        def chat_with_tools(self, messages, tools, **_):  # noqa: ANN001, ARG002
            return {"intent": "structured_query"}

        def generate_short_text(self, prompt, max_words: int = 30):  # noqa: ANN001, ARG002
            return ""

    _llm._chat_provider = _FencedProvider()
    try:
        sql = nl2sql.generate_sql("list events")
        assert sql.startswith("SELECT")
        assert "```" not in sql
    finally:
        _llm.reset_provider()
