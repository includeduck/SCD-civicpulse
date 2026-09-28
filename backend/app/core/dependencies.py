"""Dependency injection helpers — database session, settings, providers, services.

Importing from this module is the only way routes obtain a DB session or the
settings object. This enforces the 4-layer contract:
  routes → depend on session/settings → repository layer uses session.

Never import SQLAlchemy Session directly into route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.providers.cache import RedisStatsCache, StatsCache
from app.providers.rate_limit import RateLimiter, RedisFixedWindowRateLimiter
from app.providers.triage.base import TriageProvider
from app.providers.triage_cache import RedisTriageCache, TriageCache
from app.services.complaints import ComplaintService
from app.services.meta import MetaService
from app.services.stats import StatsService
from app.services.status import StatusService
from app.services.triage import TriageService
from app.services.triage_correction import TriageCorrectionService

# ── Engine / session factory (created lazily on first request) ──────────────
# The engine is module-level so it is shared across the process lifetime.
# In tests, patch get_settings() to point at a test database.


def _make_engine(settings: Settings):
    """Create an async SQLAlchemy engine from Settings."""
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
        future=True,
    )


def _make_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = _make_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Module-level singleton — recreated if settings change (tests).
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = _make_session_factory(get_settings())
    return _session_factory


async def dispose_engine() -> None:
    """Close every pooled DB connection (graceful shutdown)."""
    global _session_factory
    if _session_factory is not None:
        await _session_factory.kw["bind"].dispose()
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session.

    The session is NOT committed here. FastAPI runs the code after ``yield``
    once the response has been sent, so a commit here could fail after the
    client already received 201. Services own the unit of work: they call
    ``await session.commit()`` before returning, then perform post-commit side
    effects (e.g. cache invalidation). Anything left uncommitted is rolled back.
    Routes must not manage transactions themselves.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


# ── Typed dependency aliases ────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ── Providers and services ──────────────────────────────────────────────────
# Wiring lives here so routes only ever receive ready-made services. Tests swap
# any of these via app.dependency_overrides.


def get_triage_provider(request: Request) -> TriageProvider:
    """The provider built once by the factory in ``create_app``."""
    provider: TriageProvider = request.app.state.triage_provider
    return provider


def get_redis(request: Request) -> Redis:
    """Process-wide Redis client, created and closed by the app lifespan."""
    redis: Redis = request.app.state.redis
    return redis


def get_triage_cache(
    redis: Annotated[Redis, Depends(get_redis)], settings: SettingsDep
) -> TriageCache:
    return RedisTriageCache(redis, ttl_seconds=settings.redis_ai_cache_ttl)


def get_triage_service(
    request: Request,
    provider: Annotated[TriageProvider, Depends(get_triage_provider)],
    cache: Annotated[TriageCache, Depends(get_triage_cache)],
    settings: SettingsDep,
) -> TriageService:
    return TriageService(
        provider,
        cache,
        timeout_seconds=settings.triage_timeout_seconds,
        retry_base_seconds=settings.triage_retry_base_seconds,
        limiter=request.app.state.triage_limiter,
    )


def get_stats_cache(
    redis: Annotated[Redis, Depends(get_redis)], settings: SettingsDep
) -> StatsCache:
    return RedisStatsCache(redis, ttl_seconds=settings.redis_stats_ttl)


def get_rate_limiter(
    redis: Annotated[Redis, Depends(get_redis)], settings: SettingsDep
) -> RateLimiter:
    return RedisFixedWindowRateLimiter(
        redis, limit=settings.rate_limit_requests, window_seconds=settings.rate_limit_window
    )


def get_complaint_service(
    db: DbSession,
    triage: Annotated[TriageService, Depends(get_triage_service)],
    cache: Annotated[StatsCache, Depends(get_stats_cache)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ComplaintService:
    return ComplaintService(db, triage, cache, limiter)


def get_status_service(
    db: DbSession, cache: Annotated[StatsCache, Depends(get_stats_cache)]
) -> StatusService:
    return StatusService(db, cache)


def get_triage_correction_service(
    db: DbSession, cache: Annotated[StatsCache, Depends(get_stats_cache)]
) -> TriageCorrectionService:
    return TriageCorrectionService(db, cache)


def get_stats_service(
    db: DbSession, cache: Annotated[StatsCache, Depends(get_stats_cache)]
) -> StatsService:
    return StatsService(db, cache)


def get_meta_service(
    db: DbSession,
    settings: SettingsDep,
    cache: Annotated[TriageCache, Depends(get_triage_cache)],
) -> MetaService:
    return MetaService(db, settings, cache)


ComplaintServiceDep = Annotated[ComplaintService, Depends(get_complaint_service)]
StatusServiceDep = Annotated[StatusService, Depends(get_status_service)]
TriageCorrectionServiceDep = Annotated[
    TriageCorrectionService, Depends(get_triage_correction_service)
]
StatsServiceDep = Annotated[StatsService, Depends(get_stats_service)]
MetaServiceDep = Annotated[MetaService, Depends(get_meta_service)]
