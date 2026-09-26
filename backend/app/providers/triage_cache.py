"""AI triage cache in Redis (assignment §2.5 item 5).

Duplicate complaints ("a burst main gets reported by nine neighbours") cost one
inference, not nine. Keys are a SHA-256 of the normalised complaint and include
the provider label, so switching TRIAGE_PROVIDER never serves another
provider's answers. TTL is 24 h.

Hit and miss counts are kept in Redis, not in process memory, so the reported
hit rate covers every backend replica.

The cache is an optimisation: if Redis fails, lookups count as misses and
writes are skipped. Triage never fails because the cache did.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.providers.triage.base import TriageResult

logger = get_logger(__name__)

_HITS_KEY = "triage:cache:hits"
_MISSES_KEY = "triage:cache:misses"


def _normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def triage_cache_key(provider: str, text: str, location: str) -> str:
    digest = hashlib.sha256(f"{_normalise(text)}\x00{_normalise(location)}".encode()).hexdigest()
    return f"triage:{provider}:{digest}"


@dataclass(frozen=True)
class CachedTriage:
    result: TriageResult
    triaged_by: str


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int

    @property
    def hit_rate(self) -> float | None:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else None


class TriageCache(Protocol):
    async def get(self, key: str) -> CachedTriage | None: ...

    async def set(self, key: str, value: CachedTriage) -> None: ...

    async def stats(self) -> CacheStats: ...


class RedisTriageCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> CachedTriage | None:
        try:
            raw = await self._redis.get(key)
            await self._redis.incr(_HITS_KEY if raw is not None else _MISSES_KEY)
        except RedisError as exc:
            logger.warning("triage_cache_unavailable", operation="get", error_class=type(exc).__name__)
            return None
        if raw is None:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            return CachedTriage(
                result=TriageResult.model_validate(data["result"]),
                triaged_by=str(data["triaged_by"]),
            )
        except (ValueError, KeyError, TypeError):
            # A corrupt entry is treated as a miss and overwritten on the next set.
            logger.warning("triage_cache_corrupt_entry")
            return None

    async def set(self, key: str, value: CachedTriage) -> None:
        payload = json.dumps(
            {"result": value.result.model_dump(mode="json"), "triaged_by": value.triaged_by}
        )
        try:
            await self._redis.set(key, payload, ex=self._ttl)
        except RedisError as exc:
            logger.warning("triage_cache_unavailable", operation="set", error_class=type(exc).__name__)

    async def stats(self) -> CacheStats:
        try:
            hits, misses = await self._redis.mget(_HITS_KEY, _MISSES_KEY)
        except RedisError:
            return CacheStats(hits=0, misses=0)
        return CacheStats(hits=int(hits or 0), misses=int(misses or 0))
