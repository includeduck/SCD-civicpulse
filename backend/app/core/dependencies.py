"""Dependency injection helpers — database session and settings.

Importing from this module is the only way routes obtain a DB session or the
settings object. This enforces the 4-layer contract:
  routes → depend on session/settings → repository layer uses session.

Never import SQLAlchemy Session directly into route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

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
