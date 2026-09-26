"""GET /api/stats and GET /api/meta/providers."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.dependencies import get_stats_cache
from app.models.complaint import TriagedBy
from app.providers.triage.rules import RuleBasedTriage

WATER = {"text": "Pipe burst ho gaya hai, paani sarak par beh raha hai", "location": "F-8"}
ROADS = {"text": "Minor pothole on the service road near the market", "location": "G-9"}


class RecordingCache:
    """In-memory StatsCache that records invalidations (stand-in until Phase 6)."""

    def __init__(self) -> None:
        self.value: dict[str, Any] | None = None
        self.invalidations = 0

    async def get(self) -> dict[str, Any] | None:
        return self.value

    async def set(self, value: dict[str, Any]) -> None:
        self.value = value

    async def invalidate(self) -> None:
        self.value = None
        self.invalidations += 1


@pytest.fixture
def cache(app) -> RecordingCache:
    recording = RecordingCache()
    app.dependency_overrides[get_stats_cache] = lambda: recording
    return recording


def test_stats_counts_every_dimension(client: TestClient):
    client.post("/api/complaints", json=WATER)
    client.post("/api/complaints", json=WATER)
    roads_id = client.post("/api/complaints", json=ROADS).json()["id"]
    client.patch(f"/api/complaints/{roads_id}/status", json={"status": "rejected"})

    response = client.get("/api/stats")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["X-Cache"] == "MISS"  # no-op cache until Phase 6

    body = response.json()
    assert body["total_complaints"] == 3
    by_category = {row["category"]: row["count"] for row in body["by_category"]}
    assert by_category == {
        "water": 2, "electricity": 0, "sanitation": 0, "roads": 1, "streetlights": 0, "other": 0,
    }
    by_priority = {row["priority"]: row["count"] for row in body["by_priority"]}
    assert by_priority == {"high": 2, "normal": 0, "low": 1}
    assert (body["open_count"], body["rejected_count"]) == (2, 1)


def test_stats_on_empty_database(client: TestClient):
    body = client.get("/api/stats").json()
    assert body["total_complaints"] == 0
    assert all(row["count"] == 0 for row in body["by_category"] + body["by_priority"])


def test_stats_read_through_hit_then_miss_after_write(client: TestClient, cache: RecordingCache):
    assert client.get("/api/stats").headers["X-Cache"] == "MISS"
    second = client.get("/api/stats")
    assert second.headers["X-Cache"] == "HIT"
    assert second.json()["total_complaints"] == 0

    client.post("/api/complaints", json=WATER)
    assert cache.invalidations == 1
    after_create = client.get("/api/stats")
    assert after_create.headers["X-Cache"] == "MISS"
    assert after_create.json()["total_complaints"] == 1


def test_status_change_invalidates_stats(client: TestClient, cache: RecordingCache):
    complaint_id = client.post("/api/complaints", json=WATER).json()["id"]
    client.get("/api/stats")
    before = cache.invalidations

    client.patch(f"/api/complaints/{complaint_id}/status", json={"status": "in_progress"})
    assert cache.invalidations == before + 1
    assert client.get("/api/stats").json()["in_progress_count"] == 1


def test_rejected_transition_does_not_invalidate(client: TestClient, cache: RecordingCache):
    complaint_id = client.post("/api/complaints", json=WATER).json()["id"]
    before = cache.invalidations
    client.patch(f"/api/complaints/{complaint_id}/status", json={"status": "resolved"})  # 409
    assert cache.invalidations == before


def test_meta_reports_recent_triage_outcomes(client: TestClient):
    for _ in range(3):
        client.post("/api/complaints", json=WATER)

    body = client.get("/api/meta/providers").json()
    outcomes = body["recent_outcomes"]
    assert len(outcomes) == 3
    for outcome in outcomes:
        assert outcome["provider"] == RuleBasedTriage.name
        assert outcome["fallback"] is False
        assert isinstance(outcome["latency_ms"], int)


def test_meta_limits_outcomes_to_20_and_flags_fallback(client: TestClient, session_factory):
    import asyncio

    from app.repositories.complaint import create_complaint

    async def seed() -> None:
        async with session_factory() as session:
            for i in range(25):
                await create_complaint(
                    session,
                    text=f"Complaint number {i} about a leaking pipe",
                    location="I-10",
                    triaged_by=TriagedBy.rules_fallback if i % 2 else TriagedBy.llm_groq,
                    triage_latency_ms=100 + i,
                )
            await session.commit()

    asyncio.run(seed())
    outcomes = client.get("/api/meta/providers").json()["recent_outcomes"]
    assert len(outcomes) == 20
    for outcome in outcomes:
        assert outcome["fallback"] is (outcome["provider"] == "rules:fallback")
