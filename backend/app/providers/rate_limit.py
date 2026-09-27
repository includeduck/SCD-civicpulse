"""Distributed rate limiter (assignment §2.4, Job 2).

Fixed window in Redis, keyed by client IP, protecting POST /api/complaints.
The counter lives in Redis, never in process memory: with the HPA running four
replicas, an in-process limiter would let a client through four times over.

Algorithm (one atomic MULTI/EXEC per request):
    SET  rate_limit:complaints:{ip} 0 EX {window} NX   # start a window if none
    INCR rate_limit:complaints:{ip}                    # count this request
    TTL  rate_limit:complaints:{ip}                    # seconds until reset
Count > limit -> 429 with Retry-After = TTL. Because the key and its expiry are
created together, a crash can never leave a counter without an expiry.

Why fixed window over token bucket: it is two Redis commands, easy to reason
about at viva, and its known weakness (a burst of up to 2x the limit across a
window boundary) is acceptable for protecting an LLM quota of "tens of
requests per minute".

If Redis is unreachable the limiter fails OPEN: the complaint is accepted, a
WARNING is logged and a metric incremented. A citizen reporting a burst water
main should not be turned away because the cache is down; the provider-side
quota and the triage fallback still bound the damage.
"""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.core.metrics import RATE_LIMIT

logger = get_logger(__name__)

KEY_PREFIX = "rate_limit:complaints"


class RateLimiter(Protocol):
    async def check(self, client_ip: str) -> None:
        """Return if the request is allowed; raise ``RateLimitError`` otherwise."""
        ...


class RedisFixedWindowRateLimiter:
    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def check(self, client_ip: str) -> None:
        key = f"{KEY_PREFIX}:{client_ip}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(key, 0, ex=self._window, nx=True)
                pipe.incr(key)
                pipe.ttl(key)
                _, count, ttl = await pipe.execute()
        except RedisError as exc:
            RATE_LIMIT.labels(outcome="error").inc()
            logger.warning("rate_limiter_unavailable", error_class=type(exc).__name__)
            return  # fail open, see module docstring

        if int(count) > self._limit:
            RATE_LIMIT.labels(outcome="rejected").inc()
            retry_after = int(ttl) if int(ttl) > 0 else self._window
            # No client IP in the log: logs carry no personal data (ADR 0004).
            logger.info("rate_limited", retry_after=retry_after)
            raise RateLimitError(
                f"Rate limit exceeded: at most {self._limit} complaints per "
                f"{self._window} s. Try again in {retry_after} s.",
                retry_after=retry_after,
            )
        RATE_LIMIT.labels(outcome="allowed").inc()
