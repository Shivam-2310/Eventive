from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Single-replica in-memory registry of user -> WebSocket connections."""

    def __init__(self) -> None:
        self._per_user: dict[str, set[WebSocket]] = defaultdict(set)
        self._per_channel: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect_user(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._per_user[str(user_id)].add(ws)

    async def connect_channel(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._per_channel[channel].add(ws)

    async def disconnect_user(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._per_user.get(str(user_id), set()).discard(ws)

    async def disconnect_channel(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            self._per_channel.get(channel, set()).discard(ws)

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> int:
        conns = list(self._per_user.get(str(user_id), set()))
        dead: list[WebSocket] = []
        text = json.dumps(payload, default=str)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception as exc:  # pragma: no cover
                logger.info("dropping ws for user %s: %s", user_id, exc)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._per_user.get(str(user_id), set()).discard(ws)
        return len(conns) - len(dead)

    async def broadcast_channel(self, channel: str, payload: dict[str, Any]) -> int:
        conns = list(self._per_channel.get(channel, set()))
        dead: list[WebSocket] = []
        text = json.dumps(payload, default=str)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:  # pragma: no cover
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._per_channel.get(channel, set()).discard(ws)
        return len(conns) - len(dead)

    def user_online(self, user_id: int) -> bool:
        return bool(self._per_user.get(str(user_id)))


manager = ConnectionManager()
