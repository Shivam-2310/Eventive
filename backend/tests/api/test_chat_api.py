"""Chat REST + WebSocket coverage."""
from __future__ import annotations

import json


def _mk_user(client, email: str) -> int:  # noqa: ANN001
    return client.post("/users", json={"email": email, "name": "U"}).json()["id"]


def _accepted_pair(client) -> tuple[int, int, int]:  # noqa: ANN001
    """Create two users + accepted connection, return (a, b, thread_id)."""
    a = _mk_user(client, "ca@x.com")
    b = _mk_user(client, "cb@x.com")
    r = client.post(f"/connections?requester_id={a}", json={"receiver_id": b})
    assert r.status_code == 201
    conn_id = r.json()["id"]
    r = client.patch(f"/connections/{conn_id}?user_id={b}", json={"status": "accepted"})
    assert r.status_code == 200
    threads = client.get(f"/threads?user_id={a}").json()
    return a, b, threads[0]["id"]


def test_create_connection_pending_then_accept(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "p1@x.com")
    b = _mk_user(client, "p2@x.com")
    r = client.post(f"/connections?requester_id={a}", json={"receiver_id": b})
    assert r.status_code == 201
    conn = r.json()
    assert conn["status"] == "pending"

    r = client.patch(f"/connections/{conn['id']}?user_id={b}", json={"status": "accepted"})
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


def test_only_receiver_can_accept(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "r1@x.com")
    b = _mk_user(client, "r2@x.com")
    conn_id = client.post(f"/connections?requester_id={a}", json={"receiver_id": b}).json()["id"]
    r = client.patch(f"/connections/{conn_id}?user_id={a}", json={"status": "accepted"})
    assert r.status_code == 403


def test_thread_and_icebreaker_created_on_accept(client) -> None:  # noqa: ANN001
    a, b, thread_id = _accepted_pair(client)
    msgs = client.get(f"/threads/{thread_id}/messages?user_id={a}").json()
    assert msgs, "icebreaker message should be present"
    assert msgs[0]["kind"] == "icebreaker"


def test_post_message_and_broadcast(client) -> None:  # noqa: ANN001
    a, b, thread_id = _accepted_pair(client)
    r = client.post(
        f"/threads/{thread_id}/messages?user_id={a}",
        json={"body": "hello"},
    )
    assert r.status_code == 201
    assert r.json()["body"] == "hello"
    # non-participant cannot post
    stranger = _mk_user(client, "st@x.com")
    r = client.post(
        f"/threads/{thread_id}/messages?user_id={stranger}",
        json={"body": "sneak"},
    )
    assert r.status_code == 403


def test_list_messages_non_participant_403(client) -> None:  # noqa: ANN001
    a, b, thread_id = _accepted_pair(client)
    stranger = _mk_user(client, "st2@x.com")
    r = client.get(f"/threads/{thread_id}/messages?user_id={stranger}")
    assert r.status_code == 403


def test_attend_together_invite_and_accept(seeded, client) -> None:  # noqa: ANN001, ARG001
    a, b, thread_id = _accepted_pair(client)
    events = client.get("/events?limit=1").json()
    eid = events[0]["id"]
    r = client.post(
        f"/threads/{thread_id}/attend-together?user_id={a}",
        json={"event_id": eid},
    )
    assert r.status_code == 200
    invite_id = r.json()["id"]
    assert r.json()["kind"] == "attend_together_invite"

    r = client.post(
        f"/threads/{thread_id}/attend-together/{invite_id}/accept?user_id={b}"
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "attend_together_accepted"


def test_attend_together_missing_event_400(client) -> None:  # noqa: ANN001
    a, b, thread_id = _accepted_pair(client)
    r = client.post(
        f"/threads/{thread_id}/attend-together?user_id={a}",
        json={"event_id": 999999},
    )
    assert r.status_code == 400


def test_list_connections_returns_both_sides(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "l1@x.com")
    b = _mk_user(client, "l2@x.com")
    client.post(f"/connections?requester_id={a}", json={"receiver_id": b})
    rows = client.get(f"/connections?user_id={a}").json()
    assert rows and any(c["requester_id"] == a for c in rows)


def test_ws_chat_receives_broadcast(client) -> None:  # noqa: ANN001
    """WS: connect as user B, post a message from A, expect B to receive it."""
    a, b, thread_id = _accepted_pair(client)
    with client.websocket_connect(f"/ws/chat?user_id={b}") as ws:
        r = client.post(
            f"/threads/{thread_id}/messages?user_id={a}",
            json={"body": "ws-hello"},
        )
        assert r.status_code == 201
        # Read one frame — either the broadcast message or a ping (which we skip).
        raw = ws.receive_text()
        payload = json.loads(raw)
        if payload.get("channel") == "ping":
            raw = ws.receive_text()
            payload = json.loads(raw)
        assert payload.get("channel") == "chat"
        assert payload["data"]["body"] == "ws-hello"


def test_update_connection_invalid_status_400(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "iv1@x.com")
    b = _mk_user(client, "iv2@x.com")
    conn_id = client.post(f"/connections?requester_id={a}", json={"receiver_id": b}).json()["id"]
    r = client.patch(f"/connections/{conn_id}?user_id={b}", json={"status": "banana"})
    assert r.status_code == 400
