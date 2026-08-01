"""Notifications REST + WebSocket coverage."""
from __future__ import annotations

import json


def _mk_user(client, email: str) -> int:  # noqa: ANN001
    return client.post("/users", json={"email": email, "name": "U"}).json()["id"]


def test_list_notifications_and_filter_unread(client, db_session) -> None:  # noqa: ANN001
    from app.domain import notification_service

    uid = _mk_user(client, "n@x.com")
    notification_service.push(db_session, uid, "t", "First")
    notification_service.push(db_session, uid, "t", "Second")

    all_rows = client.get(f"/notifications?user_id={uid}").json()
    assert len(all_rows) == 2
    unread = client.get(f"/notifications?user_id={uid}&unread_only=true").json()
    assert len(unread) == 2


def test_mark_notification_read(client, db_session) -> None:  # noqa: ANN001
    from app.domain import notification_service

    uid = _mk_user(client, "mr@x.com")
    n = notification_service.push(db_session, uid, "t", "X")
    r = client.post(f"/notifications/{n.id}/read?user_id={uid}")
    assert r.status_code == 200
    unread = client.get(f"/notifications?user_id={uid}&unread_only=true").json()
    assert unread == []


def test_mark_notification_read_wrong_user_404(client, db_session) -> None:  # noqa: ANN001
    from app.domain import notification_service

    a = _mk_user(client, "wu-a@x.com")
    b = _mk_user(client, "wu-b@x.com")
    n = notification_service.push(db_session, a, "t", "X")
    r = client.post(f"/notifications/{n.id}/read?user_id={b}")
    assert r.status_code == 404


def test_mark_missing_notification_404(client) -> None:  # noqa: ANN001
    uid = _mk_user(client, "mm@x.com")
    r = client.post(f"/notifications/999999/read?user_id={uid}")
    assert r.status_code == 404


def test_connection_request_creates_notification(client) -> None:  # noqa: ANN001
    """Connection creation via API pushes a `connection_request` to the receiver."""
    a = _mk_user(client, "ca@x.com")
    b = _mk_user(client, "cb@x.com")
    client.post(f"/connections?requester_id={a}", json={"receiver_id": b})
    inbox = client.get(f"/notifications?user_id={b}").json()
    assert any(n["type"] == "connection_request" for n in inbox)


def test_connection_accepted_notifies_requester(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "cr1@x.com")
    b = _mk_user(client, "cr2@x.com")
    conn_id = client.post(f"/connections?requester_id={a}", json={"receiver_id": b}).json()["id"]
    client.patch(f"/connections/{conn_id}?user_id={b}", json={"status": "accepted"})
    inbox = client.get(f"/notifications?user_id={a}").json()
    assert any(n["type"] == "connection_accepted" for n in inbox)


def test_dm_new_notification_on_message(client) -> None:  # noqa: ANN001
    a = _mk_user(client, "dm1@x.com")
    b = _mk_user(client, "dm2@x.com")
    conn_id = client.post(f"/connections?requester_id={a}", json={"receiver_id": b}).json()["id"]
    client.patch(f"/connections/{conn_id}?user_id={b}", json={"status": "accepted"})
    thread_id = client.get(f"/threads?user_id={a}").json()[0]["id"]
    client.post(f"/threads/{thread_id}/messages?user_id={a}", json={"body": "yo"})
    inbox = client.get(f"/notifications?user_id={b}").json()
    assert any(n["type"] == "dm_new" for n in inbox)


def test_ws_notifications_receives_push(client) -> None:  # noqa: ANN001
    """Trigger a notification via a REST call (connection request) — the sync
    request handler runs inside FastAPI's threadpool where `anyio.from_thread`
    can reach the running event loop and deliver the WS frame."""
    a = _mk_user(client, "wsn-a@x.com")
    b = _mk_user(client, "wsn-b@x.com")
    with client.websocket_connect(f"/ws/notifications?user_id={b}") as ws:
        client.post(f"/connections?requester_id={a}", json={"receiver_id": b})
        raw = ws.receive_text()
        payload = json.loads(raw)
        if payload.get("channel") == "ping":
            raw = ws.receive_text()
            payload = json.loads(raw)
        assert payload["channel"] == "notification"
        assert payload["data"]["type"] == "connection_request"
