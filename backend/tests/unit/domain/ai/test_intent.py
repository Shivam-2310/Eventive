"""Deterministic intent classifier — covers the demo phrase surface.

The classifier must never return ``semantic_search`` for a question that is
clearly personal, structured, or an action, because the downstream router
uses ``kind`` to decide whether to hit the ORM / NL2SQL / tools / RAG paths.
Any regression here is user-visible garbage.
"""

from __future__ import annotations

import pytest

from app.domain.ai.intent import classify


@pytest.mark.parametrize(
    "message,kind,subkind",
    [
        # personal ------------------------------------------------------------
        ("my saved events", "personal_query", "my_saved_events"),
        ("what events have I saved?", "personal_query", "my_saved_events"),
        # Bug-fix regression: "list the events that I saved" was being
        # mis-classified as `structured_query → list_events`, so the bot
        # returned every event in the catalog instead of the user's own saves.
        ("list the events that I saved", "personal_query", "my_saved_events"),
        ("show events I have saved", "personal_query", "my_saved_events"),
        ("what did I save?", "personal_query", "my_saved_events"),
        ("my bookmarks", "personal_query", "my_saved_events"),
        ("show me the events I bookmarked", "personal_query", "my_saved_events"),
        ("events I liked", "personal_query", "my_liked_events"),
        ("list the events that I liked", "personal_query", "my_liked_events"),
        ("what did I like?", "personal_query", "my_liked_events"),
        ("my likes", "personal_query", "my_liked_events"),
        ("events I have attended", "personal_query", "my_attended_events"),
        ("show events that I attended", "personal_query", "my_attended_events"),
        ("events I RSVPed to", "personal_query", "my_rsvps"),
        ("list events I've rsvpd", "personal_query", "my_rsvps"),
        ("my upcoming events", "personal_query", "my_rsvps"),
        ("my day", "personal_query", "my_agenda"),
        ("events on my schedule", "personal_query", "my_agenda"),
        ("my agenda", "personal_query", "my_agenda"),
        ("what's my next event?", "personal_query", "my_next_event"),
        ("my interests", "personal_query", "my_interests"),
        ("my connections", "personal_query", "my_connections"),
        ("any pending connection requests?", "personal_query", "my_pending_requests"),
        ("who should I meet?", "personal_query", "recommend_people"),
        ("recommend events for me", "personal_query", "recommend_events"),
        ("my notifications", "personal_query", "my_notifications"),
        ("my missions", "personal_query", "my_missions"),
        ("who am I?", "personal_query", "my_profile"),
        # event / speaker lookup ---------------------------------------------
        ("tell me about event 3", "event_lookup", "by_id"),
        ("what is event 12 about?", "event_lookup", "by_id"),
        ("who is Harrison Chase?", "speaker_lookup", "by_name"),
        # structured ----------------------------------------------------------
        ("how many events are there?", "structured_query", "count_events"),
        ("how many talks tomorrow?", "structured_query", "count_events"),
        ("count sessions on the AI track", "structured_query", "count_events"),
        ("list all events", "structured_query", "list_events"),
        ("list AI events", "structured_query", "list_events"),
        ("show me robotics sessions", "structured_query", "list_events"),
        ("who's speaking about RAG?", "structured_query", "speakers_about"),
        ("list all speakers", "structured_query", "list_speakers"),
        ("what tracks are there?", "structured_query", "list_interests"),
        ("what's happening today?", "structured_query", "events_today_generic"),
        # actions -------------------------------------------------------------
        ("like event 5", "action", "like_or_rsvp_event"),
        ("rsvp to event 12", "action", "like_or_rsvp_event"),
        # fallback ------------------------------------------------------------
        ("what should I know about alignment?", "semantic_search", None),
        ("tell me about vector search", "semantic_search", None),
        ("", "semantic_search", None),
    ],
)
def test_classify(message: str, kind: str, subkind: str | None) -> None:
    intent = classify(message)
    assert intent.kind == kind, f"{message!r} → {intent}"
    if subkind is not None:
        assert intent.subkind == subkind, f"{message!r} → {intent}"


def test_event_lookup_captures_id() -> None:
    intent = classify("tell me about event 42")
    assert intent.kind == "event_lookup"
    assert (intent.args or {}).get("eid") == "42"


def test_speaker_lookup_captures_name() -> None:
    intent = classify("who is Andrej Karpathy?")
    assert intent.kind == "speaker_lookup"
    assert "Andrej Karpathy".lower() in (intent.args or {}).get("name", "").lower()


def test_action_captures_event_id() -> None:
    intent = classify("like event 7")
    assert intent.kind == "action"
    assert (intent.args or {}).get("eid") == "7"
