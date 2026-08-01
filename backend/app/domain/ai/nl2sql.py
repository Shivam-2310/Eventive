from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.ai.llm_provider import get_provider
from app.infra.timefmt import format_when

logger = logging.getLogger(__name__)

# Read-only views registered in migration 001 + Alembic 005 (widened set).
# `ai_public_events_full` joins events → speakers → tracks so a single SELECT
# can answer "who's speaking about X" / "events on the AI track today" without
# NL2SQL needing to know about joins.
SAFE_VIEWS = {
    "ai_public_events",
    "ai_public_speakers",
    "ai_public_events_full",
    "ai_public_interests",
    "ai_public_reels",
}

_FORBIDDEN = re.compile(
    r"\b(delete|update|drop|alter|insert|attach|detach|pragma|create|replace|vacuum)\b",
    re.IGNORECASE,
)
_SQLITE_META = re.compile(
    r"\bsqlite_master\b|\bsqlite_temp_master\b|\bpragma_", re.IGNORECASE
)


SCHEMA_HINT = """You may query only these read-only SQLite views:

  ai_public_events(id, title, track, start_time, end_time, location, room, capacity, status, abstract, description)
  ai_public_events_full(id, title, track, start_time, end_time, location, room, capacity, status, abstract, description, speakers, tags)
     -- `speakers` and `tags` are comma-joined strings, e.g. 'Harrison Chase, Andrej Karpathy' and 'MLOps, AI Safety'
  ai_public_speakers(id, name, title, company, bio)
  ai_public_interests(id, label, category)
  ai_public_reels(id, user_name, event_id, event_title, caption, duration_seconds, status)

Rules:
- Emit ONE SELECT statement. No CTEs, PRAGMAs, attaches, or subqueries that reference other schemas.
- Use LIMIT 25 unless the user explicitly asked for a count.
- Use date('now') / strftime('%H:%M', start_time) for time filters.
- For fuzzy text filters, use `LOWER(col) LIKE '%needle%'`.
- For "how many" questions, use `SELECT COUNT(*) AS count FROM ...`.
- When the user asks "who's speaking about X" or "events with Y", query `ai_public_events_full`
  and filter on `LOWER(tags) LIKE '%x%' OR LOWER(abstract) LIKE '%x%' OR LOWER(title) LIKE '%x%'`.
"""


def _basic_guard(sql: str) -> str | None:
    if not sql:
        return "empty sql"
    if _FORBIDDEN.search(sql):
        return "forbidden keyword"
    if _SQLITE_META.search(sql):
        return "sqlite metadata not allowed"
    if not re.search(r"\bselect\b", sql, re.IGNORECASE):
        return "must contain SELECT"
    for m in re.finditer(r"\b(from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.IGNORECASE):
        table = m.group(2).lower()
        if table not in SAFE_VIEWS:
            return f"disallowed table/view: {table}"
    return None


def generate_sql(question: str) -> str:
    provider = get_provider()
    prompt = (
        SCHEMA_HINT
        + "\nQuestion: "
        + question.strip()
        + "\n\nReturn ONLY the SQL query. No commentary, no markdown, no code fences."
    )
    raw = provider.chat([{"role": "user", "content": prompt}])
    sql = raw.strip()
    sql = re.sub(r"^```(sql)?", "", sql).strip()
    sql = re.sub(r"```$", "", sql).strip()
    sql = sql.split(";")[0].strip()
    return sql


def run(db: Session, question: str) -> dict[str, Any]:
    # Try deterministic fallback FIRST — it handles the common demo phrasings
    # perfectly and doesn't burn a Gemini quota. If nothing matches, fall back
    # to the LLM.
    sql = _fallback_sql(question)
    if not sql:
        try:
            sql = generate_sql(question)
        except Exception as exc:
            logger.warning("nl2sql llm gen failed: %s", exc)
            sql = ""
    # If provider is the stub (or Gemini regressed to stub), its raw output is
    # not real SQL — replace with fallback (or a safe listing) unconditionally.
    if provider_is_stub_output(sql):
        sql = _fallback_sql(question) or "SELECT id, title, track, start_time FROM ai_public_events ORDER BY start_time LIMIT 25"
    err = _basic_guard(sql)
    if err:
        return {"ok": False, "error": err, "sql": sql, "rows": []}
    try:
        result = db.execute(text(sql))
        cols = list(result.keys()) if result.returns_rows else []
        rows = [dict(zip(cols, r, strict=False)) for r in result.fetchall()] if cols else []
        return {"ok": True, "sql": sql, "columns": cols, "rows": rows[:100]}
    except Exception as exc:
        logger.warning("nl2sql exec failed: %s", exc)
        return {"ok": False, "error": str(exc)[:200], "sql": sql, "rows": []}


def provider_is_stub() -> bool:
    return get_provider().name == "stub"


def provider_is_stub_output(sql: str) -> bool:
    """Detect the `[stub-llm] echo:` prefix that the stub provider emits.

    Gemini can regress to stub silently if its quota is exhausted; we should
    never let that raw text hit the SQL guard.
    """
    return bool(sql) and sql.lower().startswith("[stub-llm]")


# ---- deterministic templates -----------------------------------------------


_TRACK_ALIASES = {
    "ai safety": "AI Safety",
    "ai": "AI",
    "infra": "Infra",
    "startups": "Startups",
    "edge": "Edge",
    "data": "Data",
    "healthcare": "Healthcare AI",
    "robotics": "Robotics",
    "climate": "Climate Tech",
    "fintech": "Fintech",
    "frontend": "Frontend",
}


def _fallback_sql(question: str) -> str | None:
    """Return a safe SELECT for common demo questions.

    Handles:
      - counts (events / speakers / today / on track X)
      - list events (optionally filtered by track/day/time)
      - who's speaking about topic X
      - events at time X / after X / before X
      - list speakers / speakers about X
      - list interests
    """
    q = (question or "").lower().strip()
    if not q:
        return None

    # ---- counts ------------------------------------------------------------
    if re.search(r"\bhow many speakers?\b|\bcount speakers?\b", q):
        return "SELECT COUNT(*) AS count FROM ai_public_speakers"

    if re.search(r"\bhow many (events?|talks?|sessions?)\b|\bcount (of )?(events?|talks?|sessions?)\b", q):
        clauses: list[str] = []
        # optional track filter
        for alias, official in _TRACK_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", q):
                clauses.append(f"track = '{_escape(official)}'")
                break
        # today / tomorrow / date
        if "today" in q:
            clauses.append("date(start_time) = date('now')")
        elif "tomorrow" in q:
            clauses.append("date(start_time) = date('now', '+1 day')")
        # after HH(:MM)? (am|pm)?
        m = re.search(r"(?:after|starting after|>=)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", q)
        if m:
            hh = _to_24h(int(m.group(1)), m.group(2), m.group(3))
            clauses.append(f"strftime('%H:%M', start_time) >= '{hh}'")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return f"SELECT COUNT(*) AS count FROM ai_public_events{where}"

    # ---- events on track / today / with speaker / about topic --------------
    is_events_list = bool(re.search(r"\b(list|show|which|find|any|what)\b.*\b(events?|talks?|sessions?)\b", q)) or q.startswith(
        ("events", "which events", "list events", "show events", "any events")
    )
    is_happening = bool(
        re.search(r"\bwhat(?:'s|\s+is)?\s+(happening|going\s+on|on|coming\s+up)\s+(today|tomorrow|now|next)\b", q)
    )
    if is_events_list or re.search(r"\bevents?\s+(on|for|about|with|at|today|tomorrow)\b", q) or is_happening:
        clauses: list[str] = []
        matched_track: str | None = None
        for alias, official in _TRACK_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", q):
                matched_track = alias
                clauses.append(f"track = '{_escape(official)}'")
                break
        if "today" in q:
            clauses.append("date(start_time) = date('now')")
        elif "tomorrow" in q:
            clauses.append("date(start_time) = date('now', '+1 day')")
        # after / before HH(:MM)? (am|pm)?
        m = re.search(r"(?:after|starting after|>=)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", q)
        if m:
            hh = _to_24h(int(m.group(1)), m.group(2), m.group(3))
            clauses.append(f"strftime('%H:%M', start_time) >= '{hh}'")
        m = re.search(r"before\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", q)
        if m:
            hh = _to_24h(int(m.group(1)), m.group(2), m.group(3))
            clauses.append(f"strftime('%H:%M', start_time) < '{hh}'")
        # about <topic> / on <topic> / with <speaker name>. Skip when a track
        # alias already matched (e.g. "on the Robotics track" — the "on" phrase
        # is just naming the track, not a topic filter).
        m = re.search(r"\b(?:about|on|with)\s+(?:the\s+)?([a-z0-9\-\+' ]{2,40}?)\s*\??$", q)
        if m:
            topic = m.group(1).strip().rstrip("?").strip()
            # Trim trailing "track"/"topic" words so "on the Robotics track" → "robotics"
            topic = re.sub(r"\s+(track|topic|stage|room)$", "", topic).strip()
            skip = (
                not topic
                or topic in {"track", "sessions", "talks", "events", "stage", "today", "tomorrow"}
                or (matched_track and topic == matched_track)
            )
            if not skip:
                esc = _escape(topic)
                clauses.append(
                    f"(LOWER(tags) LIKE '%{esc}%' OR LOWER(abstract) LIKE '%{esc}%' "
                    f"OR LOWER(title) LIKE '%{esc}%' OR LOWER(speakers) LIKE '%{esc}%')"
                )
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                return (
                    "SELECT id, title, track, start_time, location, room, speakers, tags "
                    f"FROM ai_public_events_full{where} ORDER BY start_time LIMIT 25"
                )
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return (
            "SELECT id, title, track, start_time, location, room "
            f"FROM ai_public_events{where} ORDER BY start_time LIMIT 25"
        )

    # ---- speakers about topic X --------------------------------------------
    m = re.search(
        r"\b(?:who|which\s+speakers?)(?:'s|s)?\s*(?:is|are)?\s*(?:speaking|talking|presenting)\s+(?:about|on)\s+([a-z0-9\-\+' ]{1,40}?)\s*\??$",
        q,
    )
    if m:
        topic = m.group(1).strip()
        esc = _escape(topic)
        return (
            "SELECT id, title, track, start_time, location, room, speakers "
            "FROM ai_public_events_full "
            f"WHERE LOWER(tags) LIKE '%{esc}%' OR LOWER(abstract) LIKE '%{esc}%' "
            f"OR LOWER(title) LIKE '%{esc}%' OR LOWER(speakers) LIKE '%{esc}%' "
            "ORDER BY start_time LIMIT 25"
        )

    if re.search(r"\b(list|show|which)\b.*\bspeakers?\b", q) or re.search(r"^\s*speakers?\s*$", q):
        return "SELECT id, name, title, company FROM ai_public_speakers ORDER BY name LIMIT 100"

    if re.search(r"\b(list|show)\b.*\binterests?\b|\bwhat\s+topics\b|\bwhat\s+tracks?\b", q):
        return "SELECT id, label, category FROM ai_public_interests ORDER BY category, label LIMIT 100"

    return None


def _escape(s: str) -> str:
    return s.replace("'", "''")


def _to_24h(hh: int, mm: str | None, ampm: str | None) -> str:
    minute = int(mm or 0)
    if (ampm or "").lower() == "pm" and hh < 12:
        hh += 12
    if (ampm or "").lower() == "am" and hh == 12:
        hh = 0
    return f"{hh:02d}:{minute:02d}"


# ---- prose summarizer ------------------------------------------------------


def summarize(res: dict[str, Any]) -> str:
    """Turn a NL2SQL result into a human-readable paragraph.

    Replaces the previous ``k=v, k=v`` dump. Handles:
      * scalar answers (`COUNT(*)` → "There are 12 events matching...")
      * lists of events / speakers → bulleted with when/where
      * mixed rows → compact top-5 with pretty column formatting
    """
    if not res.get("ok"):
        return f"I couldn't answer that with SQL ({res.get('error') or 'unknown error'})."

    cols: list[str] = res.get("columns") or []
    rows: list[dict[str, Any]] = res.get("rows") or []
    if not rows:
        return "No results matched that."

    # ---- scalar answer -----------------------------------------------------
    if len(rows) == 1 and len(cols) == 1:
        (_, v), = rows[0].items()
        col = cols[0].lower()
        if col in {"count", "count(*)", "n"}:
            return _count_prose(v, res.get("sql", ""))
        return f"Answer: {v}"

    if "count" in {c.lower() for c in cols} and len(rows) == 1:
        v = rows[0][next(k for k in rows[0] if k.lower() == "count")]
        return _count_prose(v, res.get("sql", ""))

    # ---- event listing -----------------------------------------------------
    lower_cols = [c.lower() for c in cols]
    if "title" in lower_cols and ("start_time" in lower_cols or "track" in lower_cols):
        lines: list[str] = [f"Found {len(rows)} matching event{'s' if len(rows) != 1 else ''}:"]
        for r in rows[:10]:
            eid = r.get("id") or r.get("event_id")
            title = r.get("title") or "(untitled)"
            track = r.get("track") or ""
            when = _fmt_dt(r.get("start_time"))
            where = " · ".join(x for x in (r.get("location"), r.get("room")) if x)
            speakers = r.get("speakers") or ""
            tail_bits = []
            if track:
                tail_bits.append(track)
            if when:
                tail_bits.append(when)
            if where:
                tail_bits.append(where)
            if speakers:
                tail_bits.append(f"with {speakers}")
            head = f"[event:{eid}]" if eid is not None else "•"
            lines.append(f"• {head} {title} — {' · '.join(tail_bits)}")
        if len(rows) > 10:
            lines.append(f"…and {len(rows) - 10} more.")
        return "\n".join(lines)

    # ---- speaker listing ---------------------------------------------------
    if "name" in lower_cols and ("title" in lower_cols or "company" in lower_cols):
        lines = [f"Found {len(rows)} speaker{'s' if len(rows) != 1 else ''}:"]
        for r in rows[:15]:
            sid = r.get("id") or r.get("speaker_id")
            name = r.get("name") or "(unknown)"
            tail = " · ".join(x for x in (r.get("title"), r.get("company")) if x)
            head = f"[speaker:{sid}]" if sid is not None else "•"
            lines.append(f"• {head} {name}" + (f" — {tail}" if tail else ""))
        if len(rows) > 15:
            lines.append(f"…and {len(rows) - 15} more.")
        return "\n".join(lines)

    # ---- interests / catch-all --------------------------------------------
    if "label" in lower_cols and "category" in lower_cols:
        by_cat: dict[str, list[str]] = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(r["label"])
        parts = [f"{cat}: " + ", ".join(labels) for cat, labels in by_cat.items()]
        return "Interests grouped by category:\n" + "\n".join(parts)

    # ---- generic pretty-print (max 5 rows, no key=value dump) -------------
    lines = [f"Here's what I found ({len(rows)} row{'s' if len(rows) != 1 else ''}):"]
    for r in rows[:5]:
        # pick the two most descriptive columns
        parts = []
        for c in cols[:6]:
            v = r.get(c)
            if v is None or v == "":
                continue
            parts.append(f"{c}: {v}")
        lines.append("• " + ", ".join(parts))
    if len(rows) > 5:
        lines.append(f"…and {len(rows) - 5} more.")
    return "\n".join(lines)


_KNOWN_TRACKS = {t.lower(): t for t in ("AI", "AI Safety", "Infra", "Startups", "Edge", "Data",
                                        "Healthcare AI", "Robotics", "Climate Tech", "Fintech", "Frontend")}


def _pretty_track(raw: str) -> str:
    return _KNOWN_TRACKS.get(raw.lower(), raw)


def _count_prose(n, sql: str) -> str:  # noqa: ANN001
    """Turn a bare COUNT(*) result into a natural sentence like
    'There are 9 events on the Infra track today.'"""
    s = (sql or "").lower()
    noun = "matching rows"
    if "ai_public_events" in s:
        noun = "events"
    elif "ai_public_speakers" in s:
        noun = "speakers"
    elif "ai_public_interests" in s:
        noun = "interests"

    qualifiers: list[str] = []
    # track = 'X'
    m = re.search(r"track\s*=\s*'([^']+)'", s)
    if m:
        track = m.group(1)
        # Preserve well-known upper-case tokens (AI, MLOps, RAG, etc.) — the
        # tracks come from the CSV catalog with proper casing already.
        pretty = _pretty_track(track)
        qualifiers.append(f"on the {pretty} track")
    # date filter (handles both `date('now')` and `date('now', '+1 day')`)
    if "date(start_time)" in s and "date('now'" in s:
        if "'+1 day'" in s:
            qualifiers.append("tomorrow")
        else:
            qualifiers.append("today")
    # time filter
    m = re.search(r"strftime\('%h:%m', start_time\) >= '(\d{2}:\d{2})'", s)
    if m:
        qualifiers.append(f"starting {m.group(1)} or later")
    m = re.search(r"strftime\('%h:%m', start_time\) < '(\d{2}:\d{2})'", s)
    if m:
        qualifiers.append(f"before {m.group(1)}")

    tail = (" " + " ".join(qualifiers)) if qualifiers else ""
    return f"There {'is' if int(n) == 1 else 'are'} {n} {noun}{tail}."


def _fmt_dt(v) -> str:  # noqa: ANN001
    """Route both datetime and sqlite-string inputs through the shared
    tz-aware formatter so NL2SQL rows show the same wall-clock time as
    the rest of the app (e.g. `Sat, Jul 12 · 5:00 PM IST`)."""
    if v in (None, ""):
        return "TBD"
    if isinstance(v, datetime):
        return format_when(v)
    try:
        dt = datetime.fromisoformat(str(v).replace("T", " ").split(".")[0])
        return format_when(dt)
    except Exception:
        return str(v)
