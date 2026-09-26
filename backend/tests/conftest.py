"""Pytest test configuration and fixtures for CivicPulse backend."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://civicpulse:civicpulse@localhost:5432/civicpulse_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["TRIAGE_PROVIDER"] = "simulated"

from app.core.config import get_settings
from app.core.dependencies import get_db
from app.main import create_app
from app.models.complaint import Base

# Clear cached settings so test environment variables take effect
get_settings.cache_clear()


@pytest.fixture(scope="session")
def app():
    """Create a FastAPI application instance configured for tests."""
    return create_app()


@pytest.fixture
def session_factory() -> Generator[async_sessionmaker[AsyncSession], None, None]:
    """A fresh in-memory SQLite database per test.

    StaticPool keeps one connection so every session sees the same in-memory DB.
    Tables come from the ORM metadata here only; the application itself never
    creates schema (Alembic owns it). Postgres-specific behaviour is covered by
    tests/test_postgres.py.
    """
    import asyncio

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    asyncio.run(engine.dispose())


@pytest.fixture
def client(app, session_factory) -> Generator[TestClient, None, None]:
    """Synchronous test client backed by the per-test SQLite database."""

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous test client for async endpoint tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
