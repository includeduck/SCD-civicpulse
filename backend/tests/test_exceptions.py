"""Tests for domain error and global exception handlers."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, status
from fastapi.testclient import TestClient

from app.core.exceptions import (
    CivicPulseError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    civicpulse_error_handler,
    generic_exception_handler,
)


def _create_test_app() -> FastAPI:
    """Create a minimal app with exception handlers to test custom errors."""
    app = FastAPI()
    app.add_exception_handler(CivicPulseError, civicpulse_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)

    test_router = APIRouter()

    @test_router.get("/trigger-404")
    async def trigger_404():
        raise NotFoundError("Complaint with ID 123 not found")

    @test_router.get("/trigger-409")
    async def trigger_409():
        raise ConflictError("Cannot transition from resolved to open")

    @test_router.get("/trigger-429")
    async def trigger_429():
        raise RateLimitError("Rate limit exceeded for IP", retry_after=45)

    @test_router.get("/trigger-500")
    async def trigger_500():
        raise RuntimeError("Unexpected failure")

    app.include_router(test_router)
    return app


def test_not_found_exception_handling():
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/trigger-404")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "not_found"
        assert "not found" in data["detail"]


def test_conflict_exception_handling():
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/trigger-409")
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "invalid_transition"
        assert "Cannot transition" in data["detail"]


def test_rate_limit_exception_handling():
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/trigger-429")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers.get("Retry-After") == "45"
        data = response.json()
        assert data["code"] == "rate_limited"


def test_generic_exception_handling():
    app = _create_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/trigger-500")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert data["code"] == "internal_error"
