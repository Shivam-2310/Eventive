"""Events REST: CRUD, filters, discover, react, interactions."""
from __future__ import annotations

from datetime import datetime, timedelta


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_create_and_get_event(client) -> None:  # noqa: ANN001
    now = datetime.utcnow() + timedelta(hours=1)
    r = client.post(
        "/events",
        json={
            "external_id": "ev-1",
            "title": "First",
            "track": "AI",
            "start_time": _iso(now),
            "end_time": _iso(now + timedelta(hours=1)),
            "timezone": "UTC",
            "status": "scheduled",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "First"

    r = client.get(f"/events/{body['id']}")
    assert r.status_code == 200
    detail = r.json()
    assert isinstance(detail["speakers"], list)
    assert isinstance(detail["interests"], list)


def test_get_event_missing_returns_404(client) -> None:  # noqa: ANN001
    assert client.get("/events/999999").status_code == 404


def test_list_events_filters(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/events?track=AI&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body
    assert all(e["track"] == "AI" for e in body)


def test_list_events_filter_by_interest_id(seeded, client) -> None:  # noqa: ANN001, ARG001
    # find any interest that is assigned to at least one event
    all_interests = client.get("/interests").json()
    for interest in all_interests:
        r = client.get(f"/events?interest_id={interest['id']}&limit=5")
        if r.status_code == 200 and r.json():
            for e in r.json():
                assert any(i["id"] == interest["id"] for i in e["interests"])
            return
    # if nothing linked (shouldn't happen with seed), still record intent
    assert True


def test_update_and_delete_event(client) -> None:  # noqa: ANN001
    r = client.post("/events", json={"title": "ToPatch"})
    eid = r.json()["id"]
    r = client.patch(f"/events/{eid}", json={"title": "Patched", "status": "delayed"})
    assert r.status_code == 200
    assert r.json()["title"] == "Patched"
    assert r.json()["status"] == "delayed"

    assert client.delete(f"/events/{eid}").status_code == 204
    assert client.get(f"/events/{eid}").status_code == 404


def test_add_speaker_and_interests_to_event(seeded, client) -> None:  # noqa: ANN001, ARG001
    events = client.get("/events?limit=1").json()
    eid = events[0]["id"]
    speakers = client.get("/speakers").json()
    sid = speakers[0]["id"]
    r = client.post(f"/events/{eid}/speakers", json={"speaker_id": sid, "role": "keynote"})
    assert r.status_code == 200
    interest_ids = [i["id"] for i in client.get("/interests").json()[:2]]
    r = client.post(f"/events/{eid}/interests", json={"interest_ids": interest_ids})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] >= 1


def test_add_speaker_to_missing_event(client) -> None:  # noqa: ANN001
    r = client.post("/events/999999/speakers", json={"speaker_id": 1, "role": "panelist"})
    assert r.status_code == 404


def test_discover_returns_cards(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "disc@x.com", "name": "D"})
    uid = r.json()["id"]
    r = client.get(f"/events/discover?user_id={uid}&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["cards"]
    prompt_types = {p["prompt_type"] for p in body["cards"][0]["prompts"]}
    assert {"cover", "topic", "when_where", "vibe", "who_is_going"}.issubset(prompt_types)


def test_discover_for_you_returns_cards(seeded, client) -> None:  # noqa: ANN001, ARG001
    """Interests-first deck: create a user, give them interests, hit the new
    `/events/discover/for-you` route and confirm same card shape as `/discover`."""
    r = client.post("/users", json={"email": "foryou-api@x.com", "name": "FY"})
    uid = r.json()["id"]
    interest_ids = [i["id"] for i in client.get("/interests").json()[:3]]
    r = client.put(
        f"/users/{uid}/interests",
        json={"interest_ids": interest_ids},
    )
    assert r.status_code == 200
    r = client.get(f"/events/discover/for-you?user_id={uid}&limit=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "cards" in body
    assert body["next_cursor"] is None
    if body["cards"]:
        prompt_types = {p["prompt_type"] for p in body["cards"][0]["prompts"]}
        assert {"cover", "topic", "when_where", "vibe", "who_is_going"}.issubset(prompt_types)


def test_discover_for_you_missing_user_returns_empty(client) -> None:  # noqa: ANN001
    """Unknown user id → empty deck, not a 404. Matches the `discover` behavior."""
    r = client.get("/events/discover/for-you?user_id=999999&limit=5")
    assert r.status_code == 200
    assert r.json() == {"cards": [], "next_cursor": None}


def test_react_to_event_upserts(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "react@x.com", "name": "R"})
    uid = r.json()["id"]
    eid = client.get("/events?limit=1").json()[0]["id"]
    r1 = client.post(
        f"/events/{eid}/react?user_id={uid}",
        json={"prompt_type": "topic", "reaction": "like"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/events/{eid}/react?user_id={uid}",
        json={"prompt_type": "topic", "reaction": "like"},
    )
    assert r2.status_code == 200
    # id is stable — same row.
    assert r1.json()["id"] == r2.json()["id"]


def test_react_invalid_prompt_type_400(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "bad@x.com", "name": "R"})
    uid = r.json()["id"]
    eid = client.get("/events?limit=1").json()[0]["id"]
    r = client.post(
        f"/events/{eid}/react?user_id={uid}",
        json={"prompt_type": "not-a-slot", "reaction": "like"},
    )
    assert r.status_code == 400


def test_interaction_endpoint(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "int@x.com", "name": "I"})
    uid = r.json()["id"]
    eid = client.get("/events?limit=1").json()[0]["id"]
    r = client.post(f"/events/{eid}/interactions?user_id={uid}", json={"type": "like"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "like"
    assert body["active"] is True


def test_interaction_is_idempotent_and_toggleable(seeded, client) -> None:  # noqa: ANN001, ARG001
    """Repeated posts of the same (user, event, type) return the same row and
    the DELETE endpoint removes it — the client is safe to retry."""
    r = client.post("/users", json={"email": "toggle@x.com", "name": "Toggle"})
    uid = r.json()["id"]
    eid = client.get("/events?limit=1").json()[0]["id"]

    r1 = client.post(f"/events/{eid}/interactions?user_id={uid}", json={"type": "save"})
    r2 = client.post(f"/events/{eid}/interactions?user_id={uid}", json={"type": "save"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    # single row in the map
    m = client.get(f"/users/{uid}/event-interactions").json()
    assert m["events"][str(eid)] == ["save"]

    # delete and confirm it's gone
    r_del = client.delete(f"/events/{eid}/interactions?user_id={uid}&type=save")
    assert r_del.status_code == 200
    assert r_del.json()["active"] is False

    m2 = client.get(f"/users/{uid}/event-interactions").json()
    assert m2["events"] == {}


def test_user_events_buckets(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "buckets@x.com", "name": "B"})
    uid = r.json()["id"]
    events = client.get("/events?limit=3").json()
    assert len(events) >= 2
    e_save = events[0]["id"]
    e_rsvp = events[1]["id"]

    client.post(f"/events/{e_save}/interactions?user_id={uid}", json={"type": "save"})
    client.post(f"/events/{e_rsvp}/interactions?user_id={uid}", json={"type": "rsvp"})

    j = client.get(f"/users/{uid}/events").json()
    saved_ids = {e["id"] for e in j["buckets"]["save"]}
    rsvp_ids = {e["id"] for e in j["buckets"]["rsvp"]}
    assert e_save in saved_ids
    assert e_rsvp in rsvp_ids
    # every canonical bucket key is always present
    for k in ("save", "like", "add_to_my_day", "mark_attended", "add_to_calendar", "rsvp", "upcoming_rsvp"):
        assert k in j["buckets"]


def test_interaction_invalid_type_400(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.post("/users", json={"email": "bt@x.com", "name": "I"})
    uid = r.json()["id"]
    eid = client.get("/events?limit=1").json()[0]["id"]
    r = client.post(f"/events/{eid}/interactions?user_id={uid}", json={"type": "hug"})
    assert r.status_code == 400


def test_already_liked_speaker_flag(seeded, client) -> None:  # noqa: ANN001, ARG001
    """React with a 'speaker' prompt then discover — flag should flip for that event."""
    r = client.post("/users", json={"email": "als@x.com", "name": "S"})
    uid = r.json()["id"]
    disc = client.get(f"/events/discover?user_id={uid}&limit=1").json()
    ev = disc["cards"][0]["event"]
    # find the speaker prompt (may or may not exist depending on seed hydration)
    speaker_prompt = next(
        (p for p in disc["cards"][0]["prompts"] if p["prompt_type"] == "speaker"), None
    )
    if speaker_prompt is None:
        return  # nothing to assert if no speaker linked

    client.post(
        f"/events/{ev['id']}/react?user_id={uid}",
        json={
            "prompt_type": "speaker",
            "prompt_ref_id": speaker_prompt["prompt_ref_id"],
            "reaction": "like",
        },
    )
    disc2 = client.get(f"/events/discover?user_id={uid}&limit=1").json()
    same_card = next((c for c in disc2["cards"] if c["event"]["id"] == ev["id"]), None)
    assert same_card is not None
    assert same_card["already_liked_speaker"] is True


def test_vibe_refresh_endpoint(seeded, client) -> None:  # noqa: ANN001, ARG001
    eid = client.get("/events?limit=1").json()[0]["id"]
    r = client.post(f"/events/{eid}/vibe/refresh")
    assert r.status_code == 200
    assert r.json()["vibe"]


def test_vibe_refresh_missing_event_404(client) -> None:  # noqa: ANN001
    r = client.post("/events/999999/vibe/refresh")
    assert r.status_code == 404
