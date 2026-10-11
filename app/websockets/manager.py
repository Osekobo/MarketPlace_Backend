"""WebSocket connection manager backed by a shared Redis pub/sub subscription.

One Redis subscription is maintained per order id regardless of how many local
clients are connected, and messages are fanned out to every socket on this
process. Because delivery is via Redis, this scales horizontally: clients on
any instance receive broadcasts published by any other instance.
"""
from __future__ import annotations

import asyncio
import logging

import orjson
from fastapi import WebSocket
from redis.asyncio.client import PubSub

from app.core.redis import create_pubsub
from app.websockets.events import order_channel

logger = logging.getLogger("app.websockets")


class OrderConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._pubsubs: dict[str, PubSub] = {}
        self._listeners: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, order_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(order_id, set()).add(websocket)
            if order_id not in self._pubsubs:
                await self._start_listener(order_id)

    async def disconnect(self, order_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(order_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if sockets:
                return
            self._connections.pop(order_id, None)
        await self._teardown(order_id)

    async def broadcast_local(self, order_id: str, message: str) -> None:
        await self._fan_out(order_id, message)

    async def _start_listener(self, order_id: str) -> None:
        pubsub = create_pubsub()
        await pubsub.subscribe(order_channel(order_id))
        self._pubsubs[order_id] = pubsub
        self._listeners[order_id] = asyncio.create_task(
            self._listen(order_id, pubsub), name=f"ws-pubsub-{order_id}"
        )

    async def _teardown(self, order_id: str) -> None:
        async with self._lock:
            task = self._listeners.pop(order_id, None)
            pubsub = self._pubsubs.pop(order_id, None)
        # Never cancel the task we are currently running in (teardown may be
        # invoked from within the listener during fan-out).
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        if pubsub is not None:
            try:
                await pubsub.aclose()
            except Exception:  # pragma: no cover
                logger.debug("Error closing pubsub for order %s", order_id, exc_info=True)

    async def _listen(self, order_id: str, pubsub: PubSub) -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await self._fan_out(order_id, data)
        except asyncio.CancelledError:  # graceful shutdown
            raise
        except Exception:  # pragma: no cover
            logger.exception("Redis pub/sub listener crashed for order %s", order_id)

    async def _fan_out(self, order_id: str, message: str) -> None:
        for websocket in list(self._connections.get(order_id, ())):
            try:
                await websocket.send_text(message)
            except Exception:
                # Defer teardown so we don't cancel the listener from within it.
                asyncio.create_task(self.disconnect(order_id, websocket))


def json_dumps(payload: dict) -> str:
    return orjson.dumps(payload).decode("utf-8")


manager = OrderConnectionManager()
