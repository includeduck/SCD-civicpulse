"""Tests for PATCH /api/complaints/{id}/triage (issue #46: operator triage correction)."""

from __future__ import annotations

import uuid

from fastapi import status
from fastapi.testclient import TestClient

VALID = {
    "text": "Electric wire sparked and fell across the road near market entrance",
    "location": "Sector F-7/2, Islamabad",
}


def _create(client: TestClient) -> dict:
    response = client.post("/api/complaints", json=VALID)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def test_correct_triage_both_category_and_priority(client: TestClient):
    created = _create(client)
    cid = created["id"]
    assert created["triage_corrected_at"] is None

    response = client.patch(
        f"/api/complaints/{cid}/triage",
        json={"category": "electricity", "priority": "high"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["category"] == "electricity"
    assert body["priority"] == "high"
    assert body["triage_corrected_at"] is not None

    # Verify persistence via GET
    fetched = client.get(f"/api/complaints/{cid}").json()
    assert fetched["category"] == "electricity"
    assert fetched["priority"] == "high"
    assert fetched["triage_corrected_at"] == body["triage_corrected_at"]


def test_correct_triage_category_only(client: TestClient):
    created = _create(client)
    cid = created["id"]
    original_priority = created["priority"]

    response = client.patch(
        f"/api/complaints/{cid}/triage",
        json={"category": "roads"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["category"] == "roads"
    assert body["priority"] == original_priority
    assert body["triage_corrected_at"] is not None


def test_correct_triage_priority_only(client: TestClient):
    created = _create(client)
    cid = created["id"]
    original_category = created["category"]

    response = client.patch(
        f"/api/complaints/{cid}/triage",
        json={"priority": "low"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["priority"] == "low"
    assert body["category"] == original_category
    assert body["triage_corrected_at"] is not None


def test_correct_triage_empty_body_fails_400(client: TestClient):
    created = _create(client)
    response = client.patch(f"/api/complaints/{created['id']}/triage", json={})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_correct_triage_invalid_enum_fails_400(client: TestClient):
    created = _create(client)
    response = client.patch(
        f"/api/complaints/{created['id']}/triage",
        json={"priority": "ultra-urgent"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_correct_triage_not_found_fails_404(client: TestClient):
    missing_id = uuid.uuid4()
    response = client.patch(
        f"/api/complaints/{missing_id}/triage",
        json={"priority": "low"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_correct_triage_invalidates_stats_cache(client: TestClient):
    created = _create(client)
    cid = created["id"]

    # Initial stats fetch caches the counts
    r1 = client.get("/api/stats")
    assert r1.status_code == status.HTTP_200_OK
    assert r1.headers.get("X-Cache") == "MISS"

    # Second fetch should hit the cache
    r2 = client.get("/api/stats")
    assert r2.headers.get("X-Cache") == "HIT"

    # Operator corrects triage
    patch_res = client.patch(
        f"/api/complaints/{cid}/triage",
        json={"priority": "low", "category": "sanitation"},
    )
    assert patch_res.status_code == status.HTTP_200_OK

    # Next stats fetch must be a cache MISS because cache was invalidated
    r3 = client.get("/api/stats")
    assert r3.status_code == status.HTTP_200_OK
    assert r3.headers.get("X-Cache") == "MISS"


def test_correct_triage_invalid_uuid_fails_422(client: TestClient):
    response = client.patch(
        "/api/complaints/not-a-valid-uuid/triage",
        json={"priority": "low"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
