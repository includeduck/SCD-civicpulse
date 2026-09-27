"""Stats cache (assignment §2.4, Job 1): read-through, 30 s TTL, invalidated on write.

Why both a TTL *and* explicit invalidation?
  - Invalidation makes a new complaint or status change show up in the stats
    immediately, instead of up to 30 s later.
  - The TTL is the safety net for writes the invalidation cannot see: a failed
    DEL during a Redis blip, a row changed directly in the database, a replica
    that crashed between commit and invalidate. Staleness is bounded at 30 s
    whatever goes wrong.

Redis is an optimisation here, not a dependency of correctness: if it fails,
reads are misses (computed from Postgres) and the request still succeeds.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.metrics import STATS_CACHE

logger = get_logger(__name__)

# Versioned so a change to the stats shape never reads an old payload.
STATS_CACHE_KEY = "stats:v1"


class StatsCache(Protocol):
    async def get(self) -> dict[str, Any] | None:
        """Return the cached stats payload, or None on a miss."""
        ...

    async def set(self, value: dict[str, Any]) -> None:
        """Store the stats payload with the configured TTL."""
        ...

    async def invalidate(self) -> None:
        """Drop the cached payload after a write."""
        ...


class RedisStatsCache:
    def __init__(self, redis: Redis, ttl_seconds: int, key: str = STATS_CACHE_KEY) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._key = key

    async def get(self) -> dict[str, Any] | None:
        try:
            raw = await self._redis.get(self._key)
        except RedisError as exc:
            STATS_CACHE.labels(result="error").inc()
            logger.warning("stats_cache_unavailable", operation="get", error_class=type(exc).__name__)
            return None
        if raw is None:
            STATS_CACHE.labels(result="miss").inc()
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            STATS_CACHE.labels(result="miss").inc()
            return None
        STATS_CACHE.labels(result="hit").inc()
        return value if isinstance(value, dict) else None

    async def set(self, value: dict[str, Any]) -> None:
        try:
            await self._redis.set(self._key, json.dumps(value), ex=self._ttl)
        except RedisError as exc:
            logger.warning("stats_cache_unavailable", operation="set", error_class=type(exc).__name__)

    async def invalidate(self) -> None:
        try:
            await self._redis.delete(self._key)
        except RedisError as exc:
            # The TTL bounds how long the stale entry can survive.
            logger.warning(
                "stats_cache_unavailable", operation="invalidate", error_class=type(exc).__name__
            )
