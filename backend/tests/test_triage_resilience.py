"""TriageService: timeout, single jittered retry, fallback, AI cache (plan §10 mandatory tests)."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import status
from fastapi.testclient import TestClient

from app.core.dependencies import get_triage_provider
from app.models.complaint import Category, Priority
from app.providers.triage.base import (
    TriageBadRequestError,
    TriageInvalidOutputError,
    TriageRateLimitedError,
    TriageResult,
    TriageServerError,
    TriageTimeoutError,
)
from app.providers.triage_cache import RedisTriageCache
from app.services.triage import TriageService

TEXT = "Burst water main flooding Street 12 since fajr, water entering ground floors"
LOCATION = "Street 12, G-10/2"
GOOD = TriageResult(category=Category.water, priority=Priority.high, summary="Burst main", confidence=0.9)


class ScriptedProvider:
    """Plays back a script of results/exceptions, one per call, and counts calls."""

    def __init__(self, *script: Any, name: str = "llm:groq") -> None:
        self.name = name
        self.script = list(script)
        self.calls = 0

    def triage(self, text: str, location: str) -> TriageResult:
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(step, BaseException):
            raise step
        return step


class FakeSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _service(provider, *, cache=None, sleep=None, timeout=10.0):
    return TriageService(
        provider,
        cache or RedisTriageCache(FakeAsyncRedis(), ttl_seconds=86400),
        timeout_seconds=timeout,
        retry_base_seconds=0.5,
        sleep=sleep or FakeSleep(),
        jitter=lambda low, high: high,  # deterministic: always the maximum jitter
    )


async def _run(service: TriageService):
    return await service.triage(uuid.uuid4(), TEXT, LOCATION)


# ── 1–6: provider behaviour ──────────────────────────────────────────────────


async def test_1_success_records_provider_and_latency():
    provider = ScriptedProvider(GOOD)
    outcome = await _run(_service(provider))
    assert (outcome.triaged_by, outcome.fallback, outcome.cache_hit) == ("llm:groq", False, False)
    assert outcome.result == GOOD
    assert isinstance(outcome.latency_ms, int)
    assert provider.calls == 1


@pytest.mark.parametrize(
    "first_error",
    [TriageTimeoutError("t"), TriageRateLimitedError("429")],
    ids=["2_timeout", "3_rate_limited"],
)
async def test_retryable_error_retries_once_with_jitter_then_succeeds(first_error):
    provider, sleep = ScriptedProvider(first_error, GOOD), FakeSleep()
    outcome = await _run(_service(provider, sleep=sleep))
    assert outcome.triaged_by == "llm:groq"
    assert provider.calls == 2
    assert sleep.delays == [0.75]  # 0.5 base × 1.5 jitter; injected, so no real waiting


async def test_4_server_error_twice_retries_once_then_falls_back():
    provider, sleep = ScriptedProvider(TriageServerError("503")), FakeSleep()
    outcome = await _run(_service(provider, sleep=sleep))
    assert (outcome.triaged_by, outcome.fallback) == ("rules:fallback", True)
    assert provider.calls == 2  # exactly one retry, never more
    assert len(sleep.delays) == 1


@pytest.mark.parametrize(
    "error",
    [TriageBadRequestError("400"), TriageInvalidOutputError("prose")],
    ids=["5_bad_request", "6_malformed_output"],
)
async def test_non_retryable_errors_fall_back_without_retry(error):
    provider, sleep = ScriptedProvider(error), FakeSleep()
    outcome = await _run(_service(provider, sleep=sleep))
    assert outcome.triaged_by == "rules:fallback"
    assert provider.calls == 1
    assert sleep.delays == []


async def test_6b_output_that_fails_the_schema_is_rejected():
    bad = TriageResult.model_construct(category="panic", priority="now", summary="x" * 500, confidence=9)
    outcome = await _run(_service(ScriptedProvider(bad)))
    assert outcome.triaged_by == "rules:fallback"
    assert outcome.result.category == Category.water  # decided by the rules, not the bad output


async def test_hard_timeout_caps_a_hung_provider():
    """A provider that never returns is cut off by the service's deadline, not left hanging."""
    release = threading.Event()

    class HangingProvider:
        name = "llm:ollama"
        calls = 0

        def triage(self, text: str, location: str) -> TriageResult:
            HangingProvider.calls += 1
            release.wait(timeout=5)
            return GOOD

    try:
        outcome = await _run(_service(HangingProvider(), timeout=0.05))
    finally:
        release.set()
    assert outcome.triaged_by == "rules:fallback"
    assert HangingProvider.calls == 2  # timeout is retryable: one retry, then fallback
    assert outcome.latency_ms < 2000


# ── 7: the test to write if you write no other (assignment §2.5) ─────────────


def test_7_provider_that_always_raises_still_returns_201(client: TestClient, app):
    app.dependency_overrides[get_triage_provider] = lambda: ScriptedProvider(RuntimeError("boom"))
    response = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION})
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["triaged_by"] == "rules:fallback"


def test_7b_fallback_logs_exactly_one_warning_with_id_provider_and_error(client: TestClient, app):
    app.dependency_overrides[get_triage_provider] = lambda: ScriptedProvider(TriageServerError("503"))
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                records.append(record)

    handler = Capture()
    logging.getLogger("app.services.triage").addHandler(handler)
    try:
        body = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION}).json()
    finally:
        logging.getLogger("app.services.triage").removeHandler(handler)

    assert len(records) == 1
    event = records[0].msg
    assert isinstance(event, dict)
    assert event["event"] == "triage_fallback"
    assert event["complaint_id"] == body["id"]
    assert event["provider"] == "llm:groq"
    assert event["error_class"] == "TriageServerError"


def test_fallback_is_visible_in_meta(client: TestClient, app):
    app.dependency_overrides[get_triage_provider] = lambda: ScriptedProvider(TriageBadRequestError("400"))
    client.post("/api/complaints", json={"text": TEXT, "location": LOCATION})
    outcome = client.get("/api/meta/providers").json()["recent_outcomes"][0]
    assert (outcome["provider"], outcome["fallback"]) == ("rules:fallback", True)


# ── 8: AI cache ──────────────────────────────────────────────────────────────


def test_8_duplicate_complaint_is_a_cache_hit(client: TestClient, app):
    provider = ScriptedProvider(GOOD)
    app.dependency_overrides[get_triage_provider] = lambda: provider

    first = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION}).json()
    # A neighbour reports the same thing with different spacing and case.
    second = client.post(
        "/api/complaints", json={"text": "  " + TEXT.upper(), "location": "street 12,  g-10/2"}
    ).json()

    assert provider.calls == 1  # nine neighbours, one inference
    assert first["triaged_by"] == second["triaged_by"] == "llm:groq"
    assert second["category"] == "water"
    cache = client.get("/api/meta/providers").json()["cache"]
    assert cache == {"hits": 1, "misses": 1, "hit_rate": 0.5}


def test_8a_fallback_results_are_never_cached(client: TestClient, app):
    provider = ScriptedProvider(TriageBadRequestError("400"), GOOD)
    app.dependency_overrides[get_triage_provider] = lambda: provider

    first = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION}).json()
    second = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION}).json()

    assert first["triaged_by"] == "rules:fallback"
    assert second["triaged_by"] == "llm:groq"  # the provider was asked again
    assert provider.calls == 2


def test_cache_is_scoped_per_provider(client: TestClient, app):
    groq = ScriptedProvider(GOOD, name="llm:groq")
    ollama = ScriptedProvider(GOOD, name="llm:ollama")
    app.dependency_overrides[get_triage_provider] = lambda: groq
    client.post("/api/complaints", json={"text": TEXT, "location": LOCATION})
    app.dependency_overrides[get_triage_provider] = lambda: ollama
    body = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION}).json()
    assert body["triaged_by"] == "llm:ollama"
    assert ollama.calls == 1
