"""Admin pulse: snapshot REST + /ws/admin/pulse WebSocket."""
from __future__ import annotations

import json


def test_pulse_snapshot_returns_expected_keys(seeded, client) -> None:  # noqa: ANN001, ARG001
    body = client.get("/admin/pulse/snapshot").json()
    for key in (
        "likes_today",
        "reel_likes_today",
        "total_users",
        "total_accepted_connections",
        "trending_events",
    ):
        assert key in body


def test_ws_admin_pulse_sends_first_snapshot(seeded, client) -> None:  # noqa: ANN001, ARG001
    """The WS handler immediately pushes a first snapshot on connect."""
    with client.websocket_connect("/ws/admin/pulse") as ws:
        raw = ws.receive_text()
        payload = json.loads(raw)
        assert payload["channel"] == "pulse"
        assert "likes_today" in payload["data"]
