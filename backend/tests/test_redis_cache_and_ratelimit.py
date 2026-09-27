"""Redis job 1 (stats cache) and job 2 (distributed rate limiter), assignment §2.4."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import status
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.dependencies import get_db, get_rate_limiter, get_redis, get_triage_provider
from app.providers.cache import STATS_CACHE_KEY, RedisStatsCache
from app.providers.rate_limit import KEY_PREFIX, RedisFixedWindowRateLimiter
from app.providers.triage.simulated import SimulatedTriage

COMPLAINT = {"text": "Pipe burst ho gaya hai, paani sarak par beh raha hai", "location": "F-8"}


class BrokenRedis:
    """Every command fails, as when Redis is down."""

    def __getattr__(self, name):
        if name == "pipeline":
            return lambda **kwargs: _BrokenPipeline()

        async def fail(*args, **kwargs):
            raise RedisConnectionError("Connection refused")

        return fail


class _BrokenPipeline:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __getattr__(self, name):
        if name == "execute":

            async def fail():
                raise RedisConnectionError("Connection refused")

            return fail
        return lambda *args, **kwargs: self


def _limit(app, redis, limit: int, window: int = 60) -> None:
    app.dependency_overrides[get_rate_limiter] = lambda: RedisFixedWindowRateLimiter(
        redis, limit=limit, window_seconds=window
    )


# ── Job 1: /api/stats read-through cache ─────────────────────────────────────


def test_stats_miss_then_hit_then_miss_after_write(client: TestClient, fake_redis):
    assert client.get("/api/stats").headers["X-Cache"] == "MISS"
    hit = client.get("/api/stats")
    assert hit.headers["X-Cache"] == "HIT"
    assert hit.json()["total_complaints"] == 0

    client.post("/api/complaints", json=COMPLAINT)  # invalidates
    after = client.get("/api/stats")
    assert after.headers["X-Cache"] == "MISS"
    assert after.json()["total_complaints"] == 1  # visible immediately, not 30 s later


def test_status_change_invalidates_stats(client: TestClient):
    complaint_id = client.post("/api/complaints", json=COMPLAINT).json()["id"]
    client.get("/api/stats")
    assert client.get("/api/stats").headers["X-Cache"] == "HIT"
    client.patch(f"/api/complaints/{complaint_id}/status", json={"status": "in_progress"})
    after = client.get("/api/stats")
    assert (after.headers["X-Cache"], after.json()["in_progress_count"]) == ("MISS", 1)


async def test_stats_entry_has_30s_ttl(client: TestClient, fake_redis):
    client.get("/api/stats")
    assert 0 < await fake_redis.ttl(STATS_CACHE_KEY) <= 30


async def test_corrupt_stats_entry_is_a_miss():
    redis = FakeAsyncRedis()
    await redis.set(STATS_CACHE_KEY, "{not json")
    assert await RedisStatsCache(redis, ttl_seconds=30).get() is None


async def test_failed_invalidation_is_bounded_by_ttl():
    """If DEL fails, the stale entry still expires: TTL is the safety net for invalidation."""
    cache = RedisStatsCache(BrokenRedis(), ttl_seconds=30)  # type: ignore[arg-type]
    await cache.invalidate()  # logs, does not raise
    assert await cache.get() is None


# ── Job 2: distributed rate limiter ──────────────────────────────────────────


def test_limit_then_429_with_retry_after(client: TestClient, app, fake_redis):
    _limit(app, fake_redis, limit=3, window=60)
    for _ in range(3):
        assert client.post("/api/complaints", json=COMPLAINT).status_code == status.HTTP_201_CREATED

    blocked = client.post("/api/complaints", json=COMPLAINT)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert "at most 3 complaints per 60 s" in body["detail"]
    assert client.get("/api/complaints").json()["total"] == 3


def test_rate_limit_is_checked_before_triage(client: TestClient, app, fake_redis):
    """A blocked request must not spend LLM quota."""
    calls: list[str] = []

    class CountingProvider(SimulatedTriage):
        def triage(self, text, location):
            calls.append(text)
            return super().triage(text, location)

    provider = CountingProvider()
    app.dependency_overrides[get_triage_provider] = lambda: provider
    _limit(app, fake_redis, limit=1)
    client.post("/api/complaints", json=COMPLAINT)
    client.post("/api/complaints", json={**COMPLAINT, "text": COMPLAINT["text"] + " dobara"})
    assert len(calls) == 1


async def test_counter_key_always_has_an_expiry(fake_redis):
    limiter = RedisFixedWindowRateLimiter(fake_redis, limit=5, window_seconds=60)
    await limiter.check("203.0.113.7")
    key = f"{KEY_PREFIX}:203.0.113.7"
    assert await fake_redis.get(key) == b"1"
    assert 0 < await fake_redis.ttl(key) <= 60


async def test_window_resets_when_the_key_expires(fake_redis):
    from app.core.exceptions import RateLimitError

    limiter = RedisFixedWindowRateLimiter(fake_redis, limit=1, window_seconds=60)
    await limiter.check("203.0.113.8")
    with pytest.raises(RateLimitError):
        await limiter.check("203.0.113.8")
    await fake_redis.delete(f"{KEY_PREFIX}:203.0.113.8")  # what expiry does at window end
    await limiter.check("203.0.113.8")


async def test_two_replicas_share_one_limit():
    """The HPA case: separate backend processes, one Redis, one budget per client."""
    from app.core.exceptions import RateLimitError

    shared = FakeAsyncRedis()
    replica_a = RedisFixedWindowRateLimiter(shared, limit=4, window_seconds=60)
    replica_b = RedisFixedWindowRateLimiter(shared, limit=4, window_seconds=60)

    allowed = 0
    for replica in [replica_a, replica_b] * 3:  # 6 requests round-robined across pods
        try:
            await replica.check("198.51.100.1")
            allowed += 1
        except RateLimitError:
            pass
    assert allowed == 4  # an in-process counter would have allowed 6 (3 per pod)


async def test_clients_have_separate_budgets(fake_redis):
    from app.core.exceptions import RateLimitError

    limiter = RedisFixedWindowRateLimiter(fake_redis, limit=1, window_seconds=60)
    await limiter.check("198.51.100.1")
    await limiter.check("198.51.100.2")
    with pytest.raises(RateLimitError):
        await limiter.check("198.51.100.1")


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (5, 0)])
def test_rejects_bad_configuration(limit, window):
    with pytest.raises(ValueError):
        RedisFixedWindowRateLimiter(FakeAsyncRedis(), limit=limit, window_seconds=window)


# ── Client IP behind a proxy ─────────────────────────────────────────────────


@pytest.fixture
def proxied_client(session_factory, fake_redis, monkeypatch) -> Generator[TestClient, None, None]:
    """An app that trusts the test client as its reverse proxy (like nginx / Ingress)."""
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "testclient")
    get_settings.cache_clear()
    proxied_app = create_app()

    async def _db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    proxied_app.dependency_overrides[get_db] = _db
    proxied_app.dependency_overrides[get_redis] = lambda: fake_redis
    proxied_app.dependency_overrides[get_rate_limiter] = lambda: RedisFixedWindowRateLimiter(
        fake_redis, limit=1, window_seconds=60
    )
    with TestClient(proxied_app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_clients_behind_a_trusted_proxy_get_separate_buckets(proxied_client, fake_redis):
    first = proxied_client.post("/api/complaints", json=COMPLAINT, headers={"X-Forwarded-For": "203.0.113.10"})
    second = proxied_client.post("/api/complaints", json=COMPLAINT, headers={"X-Forwarded-For": "203.0.113.11"})
    again = proxied_client.post("/api/complaints", json=COMPLAINT, headers={"X-Forwarded-For": "203.0.113.10"})
    assert (first.status_code, second.status_code, again.status_code) == (201, 201, 429)


def test_spoofed_forwarded_for_from_untrusted_peer_is_ignored(client: TestClient, app, fake_redis):
    """The default app trusts only 127.0.0.1, so a client cannot mint new IPs to dodge the limit."""
    _limit(app, fake_redis, limit=1)
    first = client.post("/api/complaints", json=COMPLAINT, headers={"X-Forwarded-For": "203.0.113.20"})
    second = client.post("/api/complaints", json=COMPLAINT, headers={"X-Forwarded-For": "203.0.113.21"})
    assert (first.status_code, second.status_code) == (201, 429)


# ── Redis down: the service degrades, it does not fail ───────────────────────


def test_whole_request_path_survives_redis_outage(client: TestClient, app):
    """Rate limiter fails open, AI cache and stats cache become misses; nothing 500s."""
    app.dependency_overrides[get_redis] = lambda: BrokenRedis()

    created = client.post("/api/complaints", json=COMPLAINT)
    assert created.status_code == status.HTTP_201_CREATED
    assert created.json()["triaged_by"] == "simulated"

    stats = client.get("/api/stats")
    assert (stats.status_code, stats.headers["X-Cache"]) == (200, "MISS")
    assert stats.json()["total_complaints"] == 1
