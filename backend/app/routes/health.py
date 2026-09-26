"""Health, readiness, and metrics endpoints.

Contracts:
- GET /health: MUST NOT touch database or Redis. Returns 200 when process is running.
- GET /ready: Verifies PostgreSQL and Redis connectivity. Returns 503 if any check fails,
  naming the failed dependency.
- GET /metrics: Exposes Prometheus metrics in standard exposition format.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.dependencies import _get_session_factory

logger = logging.getLogger(__name__)

# Each dependency check must finish well inside the Kubernetes probe timeout.
READINESS_CHECK_TIMEOUT_SECONDS = 2.0

router = APIRouter(tags=["Health & Diagnostics"])

# Prometheus Metrics
REQUEST_COUNT = Counter(
    "civicpulse_requests_total",
    "Total HTTP requests handled",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "civicpulse_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


@router.get("/health", status_code=status.HTTP_200_OK, summary="Liveness Probe")
async def health() -> dict[str, str]:
    """Lightweight liveness check.

    CRITICAL: Does NOT touch the database or Redis so it never produces false
    negatives under database load or transient connectivity blips.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/ready", summary="Readiness Probe")
async def ready() -> JSONResponse:
    """Readiness probe that checks backing infrastructure (PostgreSQL & Redis).

    Returns 200 if all dependencies are healthy.
    Returns 503 naming the specific failed dependency if any check fails.
    Only the exception class is returned; full errors go to the logs, since
    driver messages can include hostnames, usernames or DSN fragments.
    """
    settings = get_settings()
    checks: dict[str, dict[str, Any]] = {}
    is_ready = True

    # 1. Check PostgreSQL
    try:
        factory = _get_session_factory()
        async with factory() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")), READINESS_CHECK_TIMEOUT_SECONDS
            )
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        is_ready = False
        checks["database"] = {"status": "failed", "error": type(exc).__name__}
        logger.warning("Readiness probe: database check failed", exc_info=exc)

    # 2. Check Redis
    try:
        import redis.asyncio as aioredis  # type: ignore

        r = aioredis.from_url(
            str(settings.redis_url),
            socket_timeout=READINESS_CHECK_TIMEOUT_SECONDS,
            socket_connect_timeout=READINESS_CHECK_TIMEOUT_SECONDS,
        )
        try:
            await r.ping()
        finally:
            await r.aclose()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        is_ready = False
        checks["redis"] = {"status": "failed", "error": type(exc).__name__}
        logger.warning("Readiness probe: redis check failed", exc_info=exc)

    payload = {
        "status": "ready" if is_ready else "not_ready",
        "dependencies": checks,
    }

    if is_ready:
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload
    )


@router.get("/metrics", summary="Prometheus Metrics")
async def metrics() -> Response:
    """Export Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
