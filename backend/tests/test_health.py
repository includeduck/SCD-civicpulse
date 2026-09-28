"""Tests for health, readiness, and metrics endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient):
    """GET /health must return 200 OK with app name and version."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert "app" in data
    assert "version" in data


def test_health_does_not_touch_db(client: TestClient):
    """GET /health must not attempt any database access or connection."""
    with patch("app.core.dependencies._get_session_factory") as mock_factory:
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        # Factory must NOT be called by /health
        mock_factory.assert_not_called()


def test_ready_unreachable_dependencies_returns_503(client: TestClient):
    """GET /ready must return 503 and name failed dependencies when unreachable."""
    response = client.get("/ready")
    # In test environment without running Postgres/Redis, returns 503
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["status"] == "not_ready"
    assert "dependencies" in data
    assert "database" in data["dependencies"]
    assert data["dependencies"]["database"]["status"] == "failed"


def test_ready_when_dependencies_healthy_returns_200(client: TestClient, app, fake_redis):
    """GET /ready must return 200 when both DB and Redis are reachable."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_session
    mock_context.__aexit__.return_value = None

    def mock_factory():
        return mock_context

    app.state.redis = fake_redis  # /ready pings the app's own pooled Redis client
    with patch("app.routes.health._get_session_factory", return_value=mock_factory):
        response = client.get("/ready")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"]["status"] == "ok"
        assert data["dependencies"]["redis"]["status"] == "ok"


def test_metrics_endpoint_returns_prometheus_format(client: TestClient):
    """GET /metrics must return standard Prometheus text exposition format."""
    response = client.get("/metrics")
    assert response.status_code == status.HTTP_200_OK
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type or "version=0.0.4" in content_type
    assert "civicpulse_" in response.text
