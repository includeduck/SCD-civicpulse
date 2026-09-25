"""Pytest test configuration and fixtures for CivicPulse backend."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Set test environment variables before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://civicpulse:civicpulse@localhost:5432/civicpulse_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["TRIAGE_PROVIDER"] = "simulated"

from app.core.config import get_settings
from app.main import create_app

# Clear cached settings so test environment variables take effect
get_settings.cache_clear()


@pytest.fixture(scope="session")
def app():
    """Create a FastAPI application instance configured for tests."""
    return create_app()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Synchronous test client."""
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous test client for async endpoint tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
