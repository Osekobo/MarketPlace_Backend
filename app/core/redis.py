"""Shared async Redis client (cache + pub/sub broker)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio.client import PubSub, Redis

from app.core.config import settings

_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> "redis.ConnectionPool":
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            str(settings.REDIS_URL),
            decode_responses=True,
            max_connections=50,
        )
    return _pool


def get_redis() -> Redis:
    """Return a Redis client backed by the shared connection pool."""
    return aioredis.Redis(connection_pool=get_redis_pool())


async def get_redis_dep() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding a pooled Redis client."""
    client = get_redis()
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


def create_pubsub() -> PubSub:
    """Create a pub/sub handle using the shared connection pool."""
    return get_redis().pubsub()


__all__ = [
    "get_redis",
    "get_redis_pool",
    "get_redis_dep",
    "close_redis_pool",
    "create_pubsub",
]
