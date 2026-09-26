"""RedisTriageCache: keys, TTL, hit-rate counters, and never failing triage."""

from __future__ import annotations

import uuid

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.models.complaint import Category, Priority
from app.providers.triage.base import TriageResult
from app.providers.triage_cache import CachedTriage, CacheStats, RedisTriageCache, triage_cache_key
from app.services.triage import TriageService

RESULT = TriageResult(category=Category.roads, priority=Priority.normal, summary="Pothole", confidence=0.8)


def test_key_normalises_whitespace_and_case_and_scopes_by_provider():
    a = triage_cache_key("llm:groq", "Pothole  near\nthe school", "F-7 Markaz")
    b = triage_cache_key("llm:groq", "pothole near the school ", "f-7   markaz")
    assert a == b
    assert a.startswith("triage:llm:groq:")
    assert a != triage_cache_key("llm:ollama", "Pothole near the school", "F-7 Markaz")
    assert a != triage_cache_key("llm:groq", "Pothole near the school", "F-8 Markaz")


async def test_round_trip_with_24h_ttl_and_counters():
    redis = FakeAsyncRedis()
    cache = RedisTriageCache(redis, ttl_seconds=86400)
    key = triage_cache_key("llm:groq", "text", "place")

    assert await cache.get(key) is None
    await cache.set(key, CachedTriage(result=RESULT, triaged_by="llm:groq"))
    assert await cache.get(key) == CachedTriage(result=RESULT, triaged_by="llm:groq")

    ttl = await redis.ttl(key)
    assert 86000 < ttl <= 86400
    assert await cache.stats() == CacheStats(hits=1, misses=1)
    assert (await cache.stats()).hit_rate == 0.5


def test_hit_rate_is_none_before_any_lookup():
    assert CacheStats(hits=0, misses=0).hit_rate is None


async def test_corrupt_entry_is_a_miss():
    redis = FakeAsyncRedis()
    cache = RedisTriageCache(redis, ttl_seconds=60)
    await redis.set("triage:llm:groq:abc", "{not json")
    assert await cache.get("triage:llm:groq:abc") is None


class BrokenRedis:
    """Every command fails, as when Redis is down."""

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise RedisConnectionError("Connection refused")

        return fail


async def test_redis_outage_degrades_to_miss_without_failing():
    cache = RedisTriageCache(BrokenRedis(), ttl_seconds=60)  # type: ignore[arg-type]
    assert await cache.get("k") is None
    await cache.set("k", CachedTriage(result=RESULT, triaged_by="llm:groq"))  # no exception
    assert await cache.stats() == CacheStats(hits=0, misses=0)


async def test_triage_still_works_when_redis_is_down():
    class Provider:
        name = "llm:groq"

        def triage(self, text: str, location: str) -> TriageResult:
            return RESULT

    service = TriageService(Provider(), RedisTriageCache(BrokenRedis(), ttl_seconds=60))  # type: ignore[arg-type]
    outcome = await service.triage(uuid.uuid4(), "Pothole on main road", "F-7")
    assert (outcome.triaged_by, outcome.result) == ("llm:groq", RESULT)


@pytest.mark.parametrize("hits", [0, 3])
async def test_stats_read_shared_counters(hits):
    """Counters live in Redis, so every replica reports the same hit rate."""
    redis = FakeAsyncRedis()
    if hits:
        await redis.set("triage:cache:hits", hits)
    await redis.set("triage:cache:misses", 1)
    stats = await RedisTriageCache(redis, ttl_seconds=60).stats()
    assert stats == CacheStats(hits=hits, misses=1)
