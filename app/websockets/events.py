"""Publish order lifecycle events to Redis pub/sub channels."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import orjson

from app.core.redis import get_redis

CHANNEL_PREFIX = "order_updates"


def order_channel(order_id: uuid.UUID | str) -> str:
    return f"{CHANNEL_PREFIX}:{order_id}"


async def publish_order_event(
    order_id: uuid.UUID | str,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Publish a JSON event to the order's channel.

    Any process / worker subscribed to the channel (including WebSocket
    listeners) receives the message, enabling horizontal scaling.
    """
    message = {
        "event": event_type,
        "order_id": str(order_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    client = get_redis()
    try:
        await client.publish(order_channel(order_id), orjson.dumps(message))
    finally:
        await client.aclose()
