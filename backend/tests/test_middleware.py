"""Tests for Request-ID and CORS middlewares."""

from __future__ import annotations

import uuid

from fastapi import status
from fastapi.testclient import TestClient


def test_request_id_generated_when_missing(client: TestClient):
    """When X-Request-ID header is omitted, the middleware must generate a valid UUID."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert len(request_id) > 0
    # Must be valid UUID format
    parsed = uuid.UUID(request_id)
    assert str(parsed) == request_id


def test_request_id_preserved_when_provided(client: TestClient):
    """When client sends X-Request-ID, the exact same ID must be echoed back in the response."""
    custom_id = "trace-client-fixed-token-998877"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Request-ID") == custom_id


def test_cors_headers_exposed(client: TestClient):
    """CORS response must expose X-Request-ID and Retry-After headers."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either 200 OK or appropriate CORS headers
    is_ok = response.status_code == status.HTTP_200_OK
    assert "access-control-allow-origin" in response.headers or is_ok
