"""ConnectionManager: per-user + per-channel register/broadcast."""
from __future__ import annotations

import pytest


class _FakeWS:
    """Minimal stand-in for `fastapi.WebSocket` — used by ConnectionManager tests.

    Only `accept()` and `send_text()` are required — the app's manager uses
    those two methods exclusively for the paths we test here.
    """

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.raise_on_send = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.raise_on_send:
            raise RuntimeError("send failed")
        self.sent.append(text)


@pytest.mark.asyncio
async def test_connect_and_send_to_user() -> None:
    from app.infra.ws_manager import ConnectionManager

    mgr = ConnectionManager()
    ws = _FakeWS()

    await mgr.connect_user(7, ws)
    assert ws.accepted is True
    assert mgr.user_online(7) is True

    delivered = await mgr.send_to_user(7, {"hello": "world"})
    assert delivered == 1
    assert ws.sent and "hello" in ws.sent[0]


@pytest.mark.asyncio
async def test_send_to_unknown_user_delivers_zero() -> None:
    from app.infra.ws_manager import ConnectionManager

    mgr = ConnectionManager()
    delivered = await mgr.send_to_user(999, {"x": 1})
    assert delivered == 0


@pytest.mark.asyncio
async def test_broadcast_channel_reaches_all_and_drops_dead() -> None:
    from app.infra.ws_manager import ConnectionManager

    mgr = ConnectionManager()
    good = _FakeWS()
    bad = _FakeWS()
    bad.raise_on_send = True

    await mgr.connect_channel("admin:pulse", good)
    await mgr.connect_channel("admin:pulse", bad)

    delivered = await mgr.broadcast_channel("admin:pulse", {"tick": 1})
    # `good` receives; `bad` raises and is pruned.
    assert delivered == 1
    assert good.sent
    # A second broadcast still lands on good (bad is gone).
    delivered_2 = await mgr.broadcast_channel("admin:pulse", {"tick": 2})
    assert delivered_2 == 1


@pytest.mark.asyncio
async def test_disconnect_user_and_channel() -> None:
    from app.infra.ws_manager import ConnectionManager

    mgr = ConnectionManager()
    ws = _FakeWS()
    await mgr.connect_user(1, ws)
    assert mgr.user_online(1) is True
    await mgr.disconnect_user(1, ws)
    assert mgr.user_online(1) is False

    other = _FakeWS()
    await mgr.connect_channel("chan", other)
    await mgr.disconnect_channel("chan", other)
    # broadcasting to a channel with no subscribers is a no-op.
    assert await mgr.broadcast_channel("chan", {"x": 1}) == 0


@pytest.mark.asyncio
async def test_module_singleton_exists() -> None:
    """`manager` is a module-level singleton the app imports directly."""
    from app.infra.ws_manager import ConnectionManager, manager

    assert isinstance(manager, ConnectionManager)
