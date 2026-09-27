"""Phase 7: JSON logs everywhere, request metrics, and resource cleanup on shutdown."""

from __future__ import annotations

import io
import json
import logging
import threading
import uuid
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.models.complaint import Category, Priority
from app.providers.triage.base import TriageResult
from app.providers.triage.simulated import SimulatedTriage
from app.providers.triage_cache import RedisTriageCache
from app.services.triage import TriageService

COMPLAINT = {"text": "Pipe burst ho gaya hai, paani sarak par beh raha hai", "location": "F-8"}


@pytest.fixture
def json_logs():
    """Capture everything the root JSON handler writes, as parsed events."""
    configure_logging("INFO", "json")
    root = logging.getLogger()
    stream = io.StringIO()
    root.handlers[0].stream = stream  # type: ignore[attr-defined]

    def events() -> list[dict]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.startswith("{")]

    return events


# ── Logging ───────────────────────────────────────────────────────────────────


def test_uvicorn_lifecycle_logs_are_json(json_logs):
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 42)
    event = json_logs()[-1]
    assert event["event"] == "Started server process [42]"
    assert event["level"] == "info"
    assert event["logger"] == "uvicorn.error"


def test_uvicorn_access_log_is_disabled(json_logs):
    logging.getLogger("uvicorn.access").info('127.0.0.1:5000 - "GET / HTTP/1.1" 200')
    assert json_logs() == []


def test_every_request_logs_one_json_line_with_request_id(client: TestClient, json_logs):
    response = client.post("/api/complaints", json=COMPLAINT, headers={"X-Request-ID": "trace-abc"})
    completed = [e for e in json_logs() if e["event"] == "request_completed"]
    assert len(completed) == 1
    event = completed[0]
    assert event["request_id"] == "trace-abc" == response.headers["X-Request-ID"]
    assert (event["method"], event["endpoint"], event["status_code"]) == ("POST", "/api/complaints", 201)
    assert isinstance(event["duration_ms"], float)
    assert "client" not in event and "client_ip" not in event  # no personal data (ADR 0004)

    created = [e for e in json_logs() if e["event"] == "complaint_created"]
    assert created[0]["request_id"] == "trace-abc"  # service logs share the request's id


# ── Metrics ───────────────────────────────────────────────────────────────────


def _metric(client: TestClient, line_prefix: str) -> float:
    for line in client.get("/metrics").text.splitlines():
        if line.startswith(line_prefix):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_request_metrics_use_route_templates_not_ids(client: TestClient):
    """One series per endpoint, not one per complaint id (bounded label cardinality)."""
    series = (
        'civicpulse_requests_total{endpoint="/api/complaints/{complaint_id}",'
        'method="GET",status_code="404"}'
    )
    before = _metric(client, series)
    for _ in range(3):
        client.get(f"/api/complaints/{uuid.uuid4()}")
    assert _metric(client, series) == before + 3

    text = client.get("/metrics").text
    assert "civicpulse_request_duration_seconds_bucket" in text
    assert 'endpoint="/api/complaints/{complaint_id}"' in text
    assert str(uuid.UUID(int=0))[:8] not in text


def test_unmatched_paths_share_one_label(client: TestClient):
    client.get("/definitely/not/a/route/123")
    client.get("/another/unknown/456")
    assert 'endpoint="unmatched"' in client.get("/metrics").text
    assert "/definitely/not" not in client.get("/metrics").text


def test_triage_and_fallback_metrics_are_exported(client: TestClient):
    client.post("/api/complaints", json=COMPLAINT)
    text = client.get("/metrics").text
    for name in (
        "civicpulse_requests_total",
        "civicpulse_request_duration_seconds",
        "civicpulse_triage_duration_seconds",
        "civicpulse_triage_fallbacks_total",
    ):
        assert name in text, name


def test_server_errors_are_counted_as_500(app, client: TestClient):
    @app.get("/test-boom-metrics")
    async def boom():
        raise RuntimeError("boom")

    series = 'civicpulse_requests_total{endpoint="/test-boom-metrics",method="GET",status_code="500"}'
    with TestClient(app, raise_server_exceptions=False) as failing:
        failing.get("/test-boom-metrics")
        assert _metric(failing, series) == 1


# ── Graceful shutdown ─────────────────────────────────────────────────────────


def test_shutdown_closes_db_pool_redis_and_provider(app, fake_redis, json_logs):
    closed: list[str] = []

    class ClosableProvider(SimulatedTriage):
        def close(self) -> None:
            closed.append("provider")

    app.state.triage_provider = ClosableProvider()
    with patch("app.main.dispose_engine", new=AsyncMock(side_effect=lambda: closed.append("db"))):
        with TestClient(app):
            redis = app.state.redis
            redis.aclose = AsyncMock(side_effect=lambda: closed.append("redis"))
    assert closed == ["db", "redis", "provider"]
    assert any(e["event"] == "shutdown_complete" for e in json_logs())
    app.state.triage_provider = SimulatedTriage()


async def test_dispose_engine_closes_the_pool():
    from app.core import dependencies

    engine = AsyncMock()
    factory = type("Factory", (), {"kw": {"bind": engine}})()
    dependencies._session_factory = factory  # type: ignore[assignment]
    await dependencies.dispose_engine()
    engine.dispose.assert_awaited_once()
    assert dependencies._session_factory is None
    await dependencies.dispose_engine()  # idempotent


# ── Triage has its own thread budget ──────────────────────────────────────────


async def test_saturated_triage_pool_degrades_to_fallback_not_a_hang():
    """With the triage limiter full, a new call waits, hits the deadline and falls back."""
    release = threading.Event()
    result = TriageResult(category=Category.water, priority=Priority.high, summary="x", confidence=0.9)

    class HangingProvider:
        name = "llm:groq"

        def triage(self, text: str, location: str) -> TriageResult:
            release.wait(timeout=5)
            return result

    limiter = anyio.CapacityLimiter(1)
    service = TriageService(
        HangingProvider(),
        RedisTriageCache(FakeAsyncRedis(), ttl_seconds=60),
        timeout_seconds=0.05,
        limiter=limiter,
        sleep=AsyncMock(),
    )
    try:
        outcome = await service.triage(uuid.uuid4(), "Pipe burst on main road", "F-8")
    finally:
        release.set()
    assert outcome.triaged_by == "rules:fallback"


def test_simulated_latency_is_applied_in_the_worker_thread():
    import time

    provider = SimulatedTriage(latency_ms=30)
    started = time.perf_counter()
    provider.triage("Pipe burst on main road", "F-8")
    assert time.perf_counter() - started >= 0.03
