"""CivicPulse FastAPI Application Entrypoint.

Configures:
- Lifespan context manager with structured JSON logging
- X-Request-ID propagation middleware
- CORS middleware
- Domain and schema validation exception handlers
- OpenAPI documentation metadata
- Health, readiness, metrics, meta, and domain routers
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from redis.asyncio import Redis
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import get_settings
from app.core.dependencies import dispose_engine
from app.core.exceptions import (
    CivicPulseError,
    civicpulse_error_handler,
    generic_exception_handler,
    pydantic_validation_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware, RequestMetricsMiddleware
from app.providers.triage.factory import build_triage_provider
from app.routes.complaints import router as complaints_router
from app.routes.health import router as health_router
from app.routes.meta import router as meta_router
from app.routes.stats import router as stats_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and graceful shutdown.

    On SIGTERM uvicorn stops accepting connections and lets in-flight requests
    finish (bounded by --timeout-graceful-shutdown), then runs the ``finally``
    block below: close the DB pool, Redis and the provider's HTTP client.
    """
    settings = get_settings()
    logger.info(
        "Application starting up",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
    # One Redis client per process, bound to the server's event loop.
    app.state.redis = Redis.from_url(str(settings.redis_url), socket_timeout=2.0)
    try:
        yield
    finally:
        logger.info("Application shutting down", app_name=settings.app_name)
        await dispose_engine()
        await app.state.redis.aclose()  # type: ignore[attr-defined]
        close_provider = getattr(app.state.triage_provider, "close", None)
        if callable(close_provider):
            close_provider()
        logger.info("shutdown_complete", closed=["database_pool", "redis", "triage_provider"])


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()
    # Before anything logs, so uvicorn's own lines after import are JSON too.
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=(
            "CivicPulse: Municipal Complaint Intake, AI Triage, and Operations Platform.\n\n"
            "Features:\n"
            "- Multi-provider AI triage (Groq, Ollama, Rules, Simulated)\n"
            "- Resilient fallback architecture\n"
            "- Distributed Redis caching and rate-limiting\n"
            "- Production observability with Prometheus metrics and structured JSON logging"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Built here, not per request: an invalid TRIAGE_PROVIDER fails at startup.
    app.state.triage_provider = build_triage_provider(settings)
    app.state.triage_limiter = anyio.CapacityLimiter(settings.triage_max_concurrency)

    # ── Exception Handlers ──────────────────────────────────────────
    app.add_exception_handler(CivicPulseError, civicpulse_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, pydantic_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)

    # ── Middlewares ─────────────────────────────────────────────────
    # Note: Middlewares are executed in reverse order of registration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Cache", "Retry-After"],
    )
    app.add_middleware(RequestMetricsMiddleware)  # inside RequestID: logs carry request_id
    app.add_middleware(RequestIDMiddleware)
    # Outermost: resolve the real client IP from X-Forwarded-For, but only when
    # the request comes from a trusted proxy (nginx / Ingress).
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=[h.strip() for h in settings.forwarded_allow_ips.split(",") if h.strip()],
    )

    # ── Routers ─────────────────────────────────────────────────────
    # Health and operational probes mounted at root
    app.include_router(health_router)

    # API endpoints under /api prefix
    api_router = APIRouter(prefix=settings.api_prefix)
    api_router.include_router(meta_router)
    api_router.include_router(complaints_router)
    api_router.include_router(stats_router)
    app.include_router(api_router)

    return app


app = create_app()
