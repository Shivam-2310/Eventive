"""LangChain-based Ask Flo agent.

Design (deliberately minimal — one agent, one tool):

    handle_chat_stream(user_id, message)
        ├─ build_user_snapshot(user_id)   ← 1–2 KB profile+agenda+connections
        │
        └─ LangChain chat model (Groq → Gemini fallback)
             ├─ 1st call: `.bind_tools([search_catalog]).ainvoke(msgs)`
             │     ├─ no tool_calls → stream `resp.content` back → done
             │     └─ tool_calls  → run `search_catalog` → append ToolMessage
             │
             └─ 2nd call: `.astream(msgs)` → stream final synthesis

The single tool `search_catalog(question: str)` wraps the existing
:func:`app.domain.ai.nl2sql.run` (deterministic templates + LLM fallback over
5 read-only SQLite views). The catalog is the only thing the agent can't
answer from the user snapshot, so one tool is enough.

If neither ``GROQ_API_KEY`` nor ``GEMINI_API_KEY`` is set the agent isn't
available and the router.py caller falls back to its deterministic regex
path. Same story on any exception thrown by the LLM (429, timeout, malformed
JSON): the router catches and re-routes so demos can't die on a bad key.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.ai import nl2sql, personal
from app.infra.config import get_settings
from app.models.event import Event, Speaker

logger = logging.getLogger(__name__)

# ---- LLM factory -----------------------------------------------------------

_llm: Any | None = None
_llm_name: str = ""


def reset_llm() -> None:
    """Drop the cached chat model. Handy for tests + env changes."""
    global _llm, _llm_name
    _llm = None
    _llm_name = ""


def get_llm() -> Any | None:
    """Return a LangChain chat model with function-calling, or ``None``.

    Priority:
      1. Groq (``GROQ_API_KEY`` set) — free-tier friendly (~30 rpm on
         Llama-3.3-70B), native tool-calling.
      2. Gemini (``GEMINI_API_KEY`` set) — via ``langchain-google-genai``.
      3. None → caller must use the deterministic fallback in router.py.
    """
    global _llm, _llm_name
    if _llm is not None:
        return _llm
    settings = get_settings()

    if settings.GROQ_API_KEY:
        try:
            from langchain_groq import ChatGroq

            _llm = ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model=settings.GROQ_MODEL,
                temperature=0.2,
            )
            _llm_name = f"groq:{settings.GROQ_MODEL}"
            logger.info("Ask Flo agent using %s", _llm_name)
            return _llm
        except Exception as exc:
            logger.warning("Groq init failed (%s); trying Gemini next.", exc)

    if settings.GEMINI_API_KEY:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            _llm = ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_CHAT_MODEL,
                temperature=0.2,
            )
            _llm_name = f"gemini:{settings.GEMINI_CHAT_MODEL}"
            logger.info("Ask Flo agent using %s", _llm_name)
            return _llm
        except Exception as exc:
            logger.warning("Gemini init failed (%s); agent unavailable.", exc)

    logger.info("No LLM key configured; Ask Flo agent will use deterministic fallback.")
    return None


def llm_name() -> str:
    _ = get_llm()
    return _llm_name or "none"


def available() -> bool:
    return get_llm() is not None


# ---- user snapshot ---------------------------------------------------------

def _one_line_bullets(items: list[dict[str, Any]], key: str,
                       id_key: str = "event_id", max_items: int = 6) -> str:
    """Compact list rendering — [event:12] Title, [event:7] Title, …
    Uses ~10 tokens per item vs ~60 for the full prose bullets.
    """
    if not items:
        return "—"
    parts = []
    for it in items[:max_items]:
        eid = it.get(id_key) or it.get("id")
        label = it.get(key) or it.get("name") or "?"
        prefix = "event:" if id_key == "event_id" else ("user:" if id_key == "user_id" else "")
        parts.append(f"[{prefix}{eid}] {label}" if eid else label)
    if len(items) > max_items:
        parts.append(f"+{len(items) - max_items} more")
    return "; ".join(parts)


def build_user_snapshot(db: Session, user_id: int) -> str:
    """One-page dossier about the current user (~400-600 tokens). Fed into
    the system prompt so the agent can answer personal questions with no
    tool calls. Kept deliberately short to preserve Groq TPD quota.
    """
    lines: list[str] = [f"user_id={user_id}"]

    # Profile → one line ("Pooja Menon · pooja@x.com · role @ company · headline")
    try:
        u = personal._get_user(db, user_id)  # type: ignore[attr-defined]
        if u:
            bits = [u.name, u.email]
            if u.role or u.company:
                bits.append(" @ ".join(x for x in (u.role, u.company) if x))
            if u.headline:
                bits.append(u.headline)
            lines.append("profile: " + " · ".join(b for b in bits if b))
    except Exception as exc:
        logger.debug("snapshot profile failed: %s", exc)

    # Interests → comma-joined labels only
    try:
        interests = personal.my_interests(db, user_id).get("data") or []
        if interests:
            lines.append("interests: " + ", ".join(i["label"] for i in interests[:10]))
    except Exception as exc:
        logger.debug("snapshot interests failed: %s", exc)

    # Event collections → one-liners with [event:ID] Title
    def _events_for(kind: str) -> list[dict[str, Any]]:
        res = personal.HANDLERS[kind](db, user_id)  # type: ignore[index]
        return res.get("data") or []

    for label, kind in (
        ("saved", "my_saved_events"),
        ("liked", "my_liked_events"),
        ("rsvps", "my_rsvps"),
        ("attended", "my_attended_events"),
        ("calendar", "my_calendar_events"),
        ("myday", "my_agenda"),
    ):
        try:
            evs = _events_for(kind)
        except Exception:
            continue
        if evs:
            lines.append(f"{label}: {_one_line_bullets(evs, 'title')}")

    # Next event → 1 line
    try:
        nxt = personal.my_next_event(db, user_id)
        nxt_data = nxt.get("data")
        if nxt_data:
            lines.append(f"next_event: [event:{nxt_data['event_id']}] {nxt_data['title']}"
                         f" @ {nxt_data.get('start_time', '')}")
    except Exception:
        pass

    # Connections → id + name only
    try:
        conns = personal.my_connections(db, user_id).get("data") or []
        if conns:
            lines.append(
                "connections: "
                + "; ".join(f"[user:{c['user_id']}] {c['name']}" for c in conns[:8])
                + (f" +{len(conns) - 8} more" if len(conns) > 8 else "")
            )
    except Exception:
        pass

    # Pending requests → counts only
    try:
        pen = personal.my_pending_requests(db, user_id).get("data") or {}
        ni, no = pen.get("incoming", 0), pen.get("outgoing", 0)
        if ni or no:
            lines.append(f"pending_requests: incoming={ni} outgoing={no}")
    except Exception:
        pass

    # Notifications → count only (title/body detail rarely needed)
    try:
        nrows = personal.my_notifications(db, user_id).get("data") or []
        if nrows:
            unread = sum(1 for n in nrows if not n.get("read"))
            lines.append(f"notifications: {len(nrows)} recent ({unread} unread)")
    except Exception:
        pass

    lines.append("now: " + datetime.now().strftime("%a %b %d %Y %H:%M"))
    return "\n".join(lines)


# ---- the single tool -------------------------------------------------------

class SearchCatalogInput(BaseModel):
    question: str = Field(
        description=(
            "A natural-language question about the public event catalog. "
            "Examples: 'events on the AI track today', 'events in room Hall 4', "
            "'events starting after 3pm today', 'details of event 12', "
            "'who is speaking about RAG?'. Keep it specific and short."
        )
    )


def _make_search_tool(db: Session):
    """Build a request-scoped LangChain tool bound to ``db``."""
    from langchain_core.tools import tool as lc_tool

    @lc_tool("search_catalog", args_schema=SearchCatalogInput)
    def search_catalog(question: str) -> str:  # noqa: D401 — LC needs a short summary line
        """Search the public event catalog (events, speakers, tracks, rooms,
        interests, times). Use for any question that isn't answered by the
        USER SNAPSHOT in the system prompt. Returns JSON with rows.
        """
        raw = nl2sql.run(db, question)
        return json.dumps(_compact(raw), default=str)

    return search_catalog


def _compact(raw: dict) -> dict:
    """Trim NL2SQL output before feeding it to the LLM (saves tokens)."""
    rows = raw.get("rows") or []
    stripped = [
        {k: v for k, v in r.items() if k not in {"abstract", "description"}}
        for r in rows[:25]
    ]
    return {
        "ok": bool(raw.get("ok")),
        "sql": raw.get("sql"),
        "columns": raw.get("columns"),
        "rows": stripped,
        "row_count": len(rows),
    }


# ---- prompt + streaming agent ---------------------------------------------

SYSTEM_PROMPT = """You are **Flo**, a warm, concise AI assistant for a corporate hackathon event.

Your job: help the current user (see USER SNAPSHOT below) navigate the event,
discover talks and speakers, and plan their day.

Behaviour rules:
- For greetings, thanks, or small talk — answer directly in one friendly sentence.
- Questions about the user's **own** stuff (their agenda, saved / liked / RSVP'd
  events, their connections, interests, next event, notifications) — answer from
  USER SNAPSHOT. Do NOT call any tool for these.
- Questions about the **catalog** (any event/speaker/track/room/time filter,
  "what's happening at 3pm", "events in Hall 4", "who is Karpathy", "how many
  AI talks tomorrow") — call `search_catalog(question=…)` with a short, precise
  rephrased query. Then summarize the returned rows in plain English.
- When mentioning an event, cite it as `[event:ID]`; a speaker `[speaker:ID]`;
  another user `[user:ID]`. Only cite IDs actually present in the data you saw.
- Keep answers 2–4 sentences unless the user explicitly asks for a full list.
  Don't expose raw SQL. Don't invent events, speakers, or IDs.
- If a tool call returns no rows, say so honestly and suggest a nearby query.
"""


async def run_agent_stream(
    db: Session, user_id: int, message: str
) -> AsyncIterator[dict[str, Any]]:
    """Run one Ask Flo turn. Yields SSE-shaped dicts compatible with the
    router's existing envelope (intent, tool, sql, citation, chunk).
    """
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    llm = get_llm()
    if llm is None:
        raise RuntimeError("no LLM configured")

    snapshot = build_user_snapshot(db, user_id)
    system_content = (
        SYSTEM_PROMPT
        + "\n\nUSER SNAPSHOT (facts about the current user — trust this):\n"
        + snapshot
    )
    search_catalog = _make_search_tool(db)
    llm_with_tools = llm.bind_tools([search_catalog])

    messages: list[Any] = [
        SystemMessage(content=system_content),
        HumanMessage(content=message),
    ]

    # ---- Step 1: decision call (may return tool_calls OR a direct answer)
    # Do the LLM call BEFORE yielding the intent frame — if it raises, the
    # router should fall back cleanly with only ONE `intent` frame in the
    # SSE stream (the deterministic one).
    first = await llm_with_tools.ainvoke(messages)
    tool_calls = list(getattr(first, "tool_calls", None) or [])

    yield {
        "event": "intent",
        "data": {"intent": "agent", "subkind": llm_name(), "args": {}},
    }

    if not tool_calls:
        # Direct answer — happens for greetings and personal questions.
        text = (getattr(first, "content", "") or "").strip() or "(no answer)"
        for piece in _word_chunks(text):
            yield {"event": "chunk", "data": {"text": piece}}
        return

    # ---- Step 2: execute each tool call, up to 3 per turn
    messages.append(first)
    for tc in tool_calls[:3]:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
        tc_id = (
            tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        ) or "call_0"
        if name != "search_catalog":
            messages.append(
                ToolMessage(
                    content=json.dumps({"error": f"unknown tool: {name}"}),
                    tool_call_id=tc_id,
                )
            )
            continue
        question = args.get("question", "") if isinstance(args, dict) else ""
        raw = nl2sql.run(db, question)
        yield {"event": "sql", "data": raw}
        yield {
            "event": "tool",
            "data": {
                "tool": "search_catalog",
                "args": {"question": question},
                "row_count": len(raw.get("rows") or []),
            },
        }
        for cite in _row_citations(db, raw):
            yield {"event": "citation", "data": cite}
        messages.append(
            ToolMessage(
                content=json.dumps(_compact(raw), default=str),
                tool_call_id=tc_id,
            )
        )

    # ---- Step 3: stream the final synthesis
    streamed_any = False
    try:
        async for chunk in llm.astream(messages):
            piece = getattr(chunk, "content", "") or ""
            if piece:
                streamed_any = True
                yield {"event": "chunk", "data": {"text": piece}}
    except Exception as exc:
        logger.warning("LLM final-stream failed (%s); using non-stream fallback.", exc)
    if not streamed_any:
        follow = await llm.ainvoke(messages)
        text = (getattr(follow, "content", "") or "").strip() or "(no answer)"
        for piece in _word_chunks(text):
            yield {"event": "chunk", "data": {"text": piece}}


# ---- helpers ---------------------------------------------------------------

def _row_citations(db: Session, res: dict) -> list[dict]:
    """Best-effort citations for the frontend. Copies the logic from
    router._sql_citations so the SSE frames look identical to the old path.
    """
    if not res or not res.get("ok"):
        return []
    rows = res.get("rows") or []
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows[:8]:
        eid = r.get("id") if ("title" in r or "track" in r) else r.get("event_id")
        if isinstance(eid, int):
            key = f"event:{eid}"
            if key in seen:
                continue
            ev = db.get(Event, eid)
            if ev:
                seen.add(key)
                out.append(
                    {"citation": key, "title": ev.title, "url": f"/events/{ev.id}"}
                )
                continue
        sid = r.get("speaker_id")
        if isinstance(sid, int):
            key = f"speaker:{sid}"
            if key in seen:
                continue
            sp = db.get(Speaker, sid)
            if sp:
                seen.add(key)
                out.append(
                    {"citation": key, "title": sp.name, "url": f"/speakers/{sp.id}"}
                )
    return out


def _word_chunks(text: str) -> list[str]:
    """Fake-stream a completed string word-by-word so the SSE UX matches the
    real streaming path (frontend just concatenates)."""
    parts = re.findall(r"\S+\s*|\n", text or "")
    return parts or ([text] if text else [])
