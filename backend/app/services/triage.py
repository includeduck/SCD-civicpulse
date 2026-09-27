"""The reliability boundary around any triage provider (assignment §2.5 items 2–5).

    cache hit?  ── yes ─► return cached result (triaged_by = original provider)
       │ no
    call provider (hard 10 s cap)
       │ retryable error (timeout / 429 / 5xx)?  ── once ─► jittered wait, call again
       │ success                     │ any failure
    validate + cache                 rules fallback, triaged_by = "rules:fallback",
                                     exactly one WARNING, never cached

A citizen never sees a 500 because a third party was slow, rate-limited or wrong.
"""

from __future__ import annotations

import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import anyio
from pydantic import ValidationError

from app.core.logging import get_logger
from app.core.metrics import TRIAGE_CACHE, TRIAGE_FALLBACKS, TRIAGE_LATENCY, TRIAGE_RETRIES
from app.models.complaint import TriagedBy
from app.providers.triage.base import (
    TriageError,
    TriageInvalidOutputError,
    TriageProvider,
    TriageResult,
    TriageTimeoutError,
)
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage_cache import CachedTriage, TriageCache, triage_cache_key

logger = get_logger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[float, float], float]


@dataclass(frozen=True)
class TriageOutcome:
    result: TriageResult
    triaged_by: str
    latency_ms: int
    fallback: bool = False
    cache_hit: bool = False


class TriageService:
    def __init__(
        self,
        provider: TriageProvider,
        cache: TriageCache,
        *,
        timeout_seconds: float = 10.0,
        retry_base_seconds: float = 0.5,
        fallback: TriageProvider | None = None,
        sleep: Sleep = anyio.sleep,
        jitter: Jitter = random.uniform,
        limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._timeout = timeout_seconds
        self._retry_base = retry_base_seconds
        self._fallback = fallback or RuleBasedTriage()
        # Injected so tests exercise the retry path without real waiting.
        self._sleep = sleep
        self._jitter = jitter
        # Provider calls get their own thread budget. Waiting for a slot counts
        # against the deadline, so saturation degrades to fallback, not a hang.
        self._limiter = limiter

    async def triage(self, complaint_id: uuid.UUID, text: str, location: str) -> TriageOutcome:
        started = time.perf_counter()
        key = triage_cache_key(self._provider.name, text, location)

        cached = await self._cache.get(key)
        if cached is not None:
            TRIAGE_CACHE.labels(result="hit").inc()
            return self._finish(started, cached.result, cached.triaged_by, cache_hit=True)
        TRIAGE_CACHE.labels(result="miss").inc()

        try:
            result = await self._call_with_retry(text, location)
        except Exception as exc:  # noqa: BLE001 — any provider failure must fall back
            error_class = type(exc).__name__
            logger.warning(
                "triage_fallback",
                complaint_id=str(complaint_id),
                provider=self._provider.name,
                error_class=error_class,
            )
            TRIAGE_FALLBACKS.labels(provider=self._provider.name, error_class=error_class).inc()
            fallback_result = self._fallback.triage(text, location)
            return self._finish(started, fallback_result, TriagedBy.rules_fallback, fallback=True)

        await self._cache.set(key, CachedTriage(result=result, triaged_by=self._provider.name))
        return self._finish(started, result, self._provider.name)

    async def _call_with_retry(self, text: str, location: str) -> TriageResult:
        try:
            return await self._call_once(text, location)
        except TriageError as exc:
            if not exc.retryable:
                raise
            TRIAGE_RETRIES.labels(provider=self._provider.name, error_class=type(exc).__name__).inc()
            delay = self._retry_base * self._jitter(0.5, 1.5)
            logger.info("triage_retry", provider=self._provider.name,
                        error_class=type(exc).__name__, delay_seconds=round(delay, 3))
            await self._sleep(delay)
            return await self._call_once(text, location)  # a second failure propagates

    async def _call_once(self, text: str, location: str) -> TriageResult:
        """One provider call under a hard deadline, with its output re-validated.

        The deadline covers the whole call, not just each socket operation.
        ``abandon_on_cancel`` lets the request move on while a stuck worker
        thread finishes on its own (bounded by the provider's HTTP timeout).
        """
        try:
            with anyio.fail_after(self._timeout):
                result = await anyio.to_thread.run_sync(
                    self._provider.triage,
                    text,
                    location,
                    abandon_on_cancel=True,
                    limiter=self._limiter,
                )
        except TimeoutError as exc:
            raise TriageTimeoutError(
                f"{self._provider.name}: exceeded {self._timeout:g}s"
            ) from exc
        try:
            return TriageResult.model_validate(result.model_dump())
        except (ValidationError, AttributeError) as exc:
            raise TriageInvalidOutputError(f"{self._provider.name}: invalid output") from exc

    @staticmethod
    def _finish(
        started: float,
        result: TriageResult,
        triaged_by: str,
        *,
        fallback: bool = False,
        cache_hit: bool = False,
    ) -> TriageOutcome:
        elapsed = time.perf_counter() - started
        TRIAGE_LATENCY.labels(triaged_by=str(triaged_by)).observe(elapsed)
        return TriageOutcome(
            result=result,
            triaged_by=str(triaged_by),
            latency_ms=round(elapsed * 1000),
            fallback=fallback,
            cache_hit=cache_hit,
        )
