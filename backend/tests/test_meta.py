"""Tests for metadata and provider introspection endpoints."""

from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient


def test_get_providers_metadata(client: TestClient):
    """GET /api/meta/providers must list all configured providers and active status."""
    response = client.get("/api/meta/providers")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "active_provider" in data
    assert "providers" in data
    assert len(data["providers"]) == 4

    provider_names = {p["name"] for p in data["providers"]}
    assert provider_names == {"simulated", "rules", "llm:groq", "llm:ollama"}

    # Check that active_provider matches exactly one active flag
    active_in_list = [p for p in data["providers"] if p["active"]]
    assert len(active_in_list) == 1
    assert active_in_list[0]["name"] == data["active_provider"]
