"""Deterministic intent classifier for Ask Eventive.

Rationale
---------
The LLM-based ``chat_with_tools`` classifier (see `stub_provider.py`) is a naive
keyword matcher; the Gemini adapter even delegates its own classifier to the
stub. That's brittle: "who should I meet?" got routed to ``semantic_search``
when it's clearly a **personal** question that should hit the recommendation
engine, and "list all events" scraped through the keyword filter but the
render was garbage.

This module owns *all* routing decisions for the Ask Eventive pipeline. It's
deterministic, unit-testable, and covers every question the demo needs to
answer end-to-end:

* ``personal_query``   — anything about the current user's own records
                         (my saved events, my liked events, my agenda,
                          my connections, who should I meet, my interests,
                          my messages, my profile, my notifications,
                          my missions, my rsvps, my next event).
* ``structured_query`` — aggregate/factual questions over the public catalog
                         (counts, filters, "which events at 3pm", "who's
                          speaking about X", list events on a track/day).
* ``action``           — imperatives that mutate state (like/rsvp/save/
                         message/connect).
* ``event_lookup``     — "tell me about event 12" / "what is event 3 about?"
                         handled deterministically by pulling that event's
                         full record.
* ``speaker_lookup``   — "who is Harrison Chase" — same, for a speaker.
* ``semantic_search``  — everything else → RAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Intent:
    kind: str
    """One of: personal_query, structured_query, action, event_lookup,
    speaker_lookup, semantic_search."""
    subkind: str | None = None
    """Fine-grained bucket inside kind (e.g. ``my_saved_events``)."""
    args: dict | None = None
    """Extracted args (event_id, speaker_name, filter, ...)."""


# ---- pattern tables --------------------------------------------------------


# The order matters: more-specific patterns must come first. Each entry is
# (regex, kind, subkind). Patterns are compiled case-insensitively at import.
_PATTERNS: list[tuple[str, str, str]] = [
    # ---- actions -----------------------------------------------------------
    (r"\b(like|save|rsvp|register)\s+(to\s+)?event\s+(?P<eid>\d+)\b", "action", "like_or_rsvp_event"),
    (r"\bmark\s+event\s+(?P<eid>\d+)\s+attended\b", "action", "mark_attended"),
    (r"\b(open|start)\s+match\s+with\s+user\s+(?P<uid>\d+)\b", "action", "open_match"),
    (r"\bmessage\s+user\s+(?P<uid>\d+)\b.*", "action", "message_user"),

    # ---- personal (my/I) -- highest priority so "my agenda" doesn't fall to structured
    # Match any word order: "my saved events", "events I saved", "events that
    # I've saved", "list events I have saved", "what did I save", etc.
    # The `\bi\b` word-boundary matches "I" case-insensitively.
    (r"\bmy\s+saved(\s+events?)?\b", "personal_query", "my_saved_events"),
    (r"\bmy\s+bookmarks?\b", "personal_query", "my_saved_events"),
    (r"\bmy\s+bookmarked\s+events?\b", "personal_query", "my_saved_events"),
    (r"\b(saved|bookmark(?:ed)?)\s+events?\s+(of\s+mine|for\s+me)\b", "personal_query", "my_saved_events"),
    (r"\bevents?\b.*\bi\b.*\b(saved|bookmarked)\b", "personal_query", "my_saved_events"),
    (r"\b(what|which)\s+(events?\s+)?(?:have\s+|did\s+)?i\s+(save|saved|bookmark|bookmarked)\b",
     "personal_query", "my_saved_events"),
    (r"\bi\b.*\b(saved|bookmarked)\b.*\bevents?\b", "personal_query", "my_saved_events"),

    (r"\bmy\s+likes?\b", "personal_query", "my_liked_events"),
    (r"\bmy\s+liked\s+events?\b", "personal_query", "my_liked_events"),
    (r"\bevents?\b.*\bi\b.*\bliked\b", "personal_query", "my_liked_events"),
    (r"\bi\b.*\bliked\b.*\bevents?\b", "personal_query", "my_liked_events"),
    (r"\b(what|which)\s+(events?\s+)?(?:have\s+|did\s+)?i\s+(like|liked)\b",
     "personal_query", "my_liked_events"),

    (r"\bmy\s+attended\s+events?\b", "personal_query", "my_attended_events"),
    (r"\bevents?\s+i\s+(?:have\s+)?attended\b", "personal_query", "my_attended_events"),
    (r"\bevents?\b.*\bi\b.*\battended\b", "personal_query", "my_attended_events"),

    (r"\bmy\s+rsvps?\b", "personal_query", "my_rsvps"),
    (r"\bmy\s+upcoming(\s+events?)?\b", "personal_query", "my_rsvps"),
    (r"\bevents?\s+i(?:'m|\s+am)?\s+(attending|going\s+to)\b", "personal_query", "my_rsvps"),
    (r"\bevents?\b.*\bi\b.*\brsvp'?e?d?\b", "personal_query", "my_rsvps"),
    (r"\bi\b.*\brsvp'?e?d?\b.*\bevents?\b", "personal_query", "my_rsvps"),

    (r"\bmy\s+day\b", "personal_query", "my_agenda"),
    (r"\bmy\s+(agenda|schedule|itinerary)\b", "personal_query", "my_agenda"),
    (r"\bevents?\s+(on|in)\s+my\s+(day|schedule|agenda|itinerary)\b",
     "personal_query", "my_agenda"),
    # "my calendar" specifically maps to the add_to_calendar bucket.
    (r"\bmy\s+calendar(\s+events?)?\b", "personal_query", "my_calendar_events"),
    (r"\bevents?\s+(on|in)\s+my\s+calendar\b", "personal_query", "my_calendar_events"),
    (r"\bevents?\b.*\bi\b.*\badded\s+to\s+(my\s+)?calendar\b", "personal_query", "my_calendar_events"),
    (r"\bwhat(?:'s|\s+is)?\s+(my\s+)?next\s+(event|talk|session)\b", "personal_query", "my_next_event"),
    (r"\b(my\s+)?next\s+(event|talk|session)\s+(is|for me)\b", "personal_query", "my_next_event"),

    (r"\bmy\s+interests?\b", "personal_query", "my_interests"),
    (r"\bwhat\s+(topics|interests|tags)\s+do\s+i\s+follow\b", "personal_query", "my_interests"),

    (r"\bmy\s+(connections|friends|network)\b", "personal_query", "my_connections"),
    (r"\bwho\s+am\s+i\s+connected\s+to\b", "personal_query", "my_connections"),
    (r"\b(connection|friend)\s+requests?\b", "personal_query", "my_pending_requests"),
    (r"\bpending\s+(connection|friend)s?\b", "personal_query", "my_pending_requests"),

    (r"\bwho\s+should\s+i\s+(meet|connect|talk\s+to|network\s+with)\b", "personal_query", "recommend_people"),
    (r"\brecommend\s+(some\s+)?(people|folks|users|attendees)\b", "personal_query", "recommend_people"),
    (r"\bpeople\s+(i\s+should\s+)?meet\b", "personal_query", "recommend_people"),

    (r"\brecommend\s+(some\s+)?(events?|talks?|sessions?)\b", "personal_query", "recommend_events"),
    (r"\bwhat\s+events?\s+should\s+i\s+(go\s+to|attend|check\s+out)\b", "personal_query", "recommend_events"),
    (r"\b(good|best)\s+events?\s+for\s+me\b", "personal_query", "recommend_events"),

    (r"\bmy\s+(notifications|inbox|alerts)\b", "personal_query", "my_notifications"),
    (r"\bmy\s+(missions|badges|streaks?|points)\b", "personal_query", "my_missions"),
    (r"\b(my\s+)?wrapped\b", "personal_query", "my_wrapped"),
    (r"\bmy\s+(profile|account|info)\b", "personal_query", "my_profile"),
    (r"\bwho\s+am\s+i\b", "personal_query", "my_profile"),

    # ---- event / speaker lookup --------------------------------------------
    (r"\b(tell|show|describe)\s+(me\s+)?about\s+event\s+(?P<eid>\d+)\b", "event_lookup", "by_id"),
    (r"\bwhat(?:'s|\s+is)?\s+event\s+(?P<eid>\d+)\s+about\b", "event_lookup", "by_id"),
    (r"\bevent\s+(?P<eid>\d+)\s+details?\b", "event_lookup", "by_id"),
    (r"^event\s+(?P<eid>\d+)$", "event_lookup", "by_id"),

    # Speaker-lookup requires a Capitalized proper-noun-like name, so
    # "tell me about vector search" (a topic) doesn't get mis-routed.
    (r"(?-i:\bwho\s+is\s+(?P<name>[A-Z][A-Za-z\.\-']*(?:\s+[A-Z][A-Za-z\.\-']*){0,3})\s*\??\s*$)",
     "speaker_lookup", "by_name"),
    (r"(?-i:\btell\s+me\s+about\s+(?P<name>[A-Z][A-Za-z\.\-']*(?:\s+[A-Z][A-Za-z\.\-']*){0,3})\s*\??\s*$)",
     "speaker_lookup", "by_name"),

    # ---- structured (aggregate / list over the catalog) --------------------
    (r"\bhow\s+many\s+(events?|talks?|sessions?)\b", "structured_query", "count_events"),
    (r"\bhow\s+many\s+speakers?\b", "structured_query", "count_speakers"),
    (r"\bcount\s+(events?|talks?|sessions?)\b", "structured_query", "count_events"),

    # "list AI events" / "show all sessions" / "which talks about vector search"
    (r"\b(list|show|which|find|any)\s+(?:all\s+)?(?:[a-z0-9\+\-\s]{1,40}\s+)?(events?|talks?|sessions?)\b",
     "structured_query", "list_events"),
    (r"\b(events?|talks?|sessions?)\s+(on|for|about|with|at)\s+[a-z0-9\s\-\+]+",
     "structured_query", "events_by_track"),
    (r"\bevents?\s+today\b", "structured_query", "events_today"),
    (r"\bevents?\s+tomorrow\b", "structured_query", "events_tomorrow"),
    (r"\bevents?\s+(starting|after|before)\s+\d", "structured_query", "events_by_time"),
    (r"\bwhat(?:'s|\s+is)?\s+(happening|going\s+on|on|coming\s+up)\s+(today|tomorrow|now|next)\b",
     "structured_query", "events_today_generic"),
    (r"\bwhen\s+does\s+(?P<title>.+?)\s+(start|begin|happen)\b", "structured_query", "event_time"),

    # "who's speaking about RAG?" (handles the "'s" contraction)
    (r"\b(?:who|which\s+speakers?)(?:'s|s)?\s*(?:is|are)?\s*(?:speaking|talking|presenting)\s+(?:about|on)\s+(?P<topic>.+?)\s*\??$",
     "structured_query", "speakers_about"),
    (r"\b(list|show|which)\s+(all\s+)?speakers?\b", "structured_query", "list_speakers"),
    (r"\bspeakers?\s+(list|for)\b", "structured_query", "list_speakers"),

    (r"\b(list|show|which)\s+(all\s+)?interests?\b|\bwhat\s+topics\b|\bwhat\s+tracks?\b",
     "structured_query", "list_interests"),
]

_COMPILED: list[tuple[re.Pattern, str, str]] = [
    (re.compile(p, re.IGNORECASE), kind, subkind) for p, kind, subkind in _PATTERNS
]


def classify(message: str) -> Intent:
    """Return the best-matching intent for ``message`` (never None)."""
    text = (message or "").strip()
    if not text:
        return Intent(kind="semantic_search")
    for regex, kind, subkind in _COMPILED:
        m = regex.search(text)
        if m:
            args = {k: v for k, v in (m.groupdict() or {}).items() if v is not None}
            return Intent(kind=kind, subkind=subkind, args=args)
    return Intent(kind="semantic_search")
