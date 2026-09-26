"""Complaint API contract: POST / GET / list (assignment §2.2)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.dependencies import get_db, get_triage_provider
from app.models.complaint import Category, Priority
from app.providers.triage.base import TriageResult

VALID = {
    "text": "Burst water main flooding Street 12 since fajr, water entering ground floors",
    "location": "Street 12, G-10/2, Islamabad",
    "reporter_contact": "03001234567",
}


def _create(client: TestClient, **overrides) -> dict:
    response = client.post("/api/complaints", json={**VALID, **overrides})
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# ── POST ─────────────────────────────────────────────────────────────────────


def test_create_complaint_triages_and_persists(client: TestClient):
    body = _create(client)

    assert body["category"] == "water"
    assert body["priority"] == "high"
    assert body["status"] == "open"
    assert body["triaged_by"] == "simulated"  # CI runs SimulatedTriage (assignment §2.5)
    assert body["ai_summary"].startswith("[simulated] ")
    assert isinstance(body["triage_latency_ms"], int)
    assert body["allowed_transitions"] == ["in_progress", "rejected"]
    uuid.UUID(body["id"])

    fetched = client.get(f"/api/complaints/{body['id']}")
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["id"] == body["id"]


def test_response_never_contains_reporter_contact(client: TestClient):
    body = _create(client)
    assert "reporter_contact" not in body
    assert "reporter_contact" not in client.get(f"/api/complaints/{body['id']}").json()
    listed = client.get("/api/complaints").json()["complaints"]
    assert all("reporter_contact" not in c for c in listed)


def test_create_uses_injected_provider(client: TestClient, app):
    class FixedProvider:
        name = "llm:groq"

        def triage(self, text: str, location: str) -> TriageResult:
            return TriageResult(
                category=Category.roads, priority=Priority.low, summary="Fixed", confidence=0.9
            )

    app.dependency_overrides[get_triage_provider] = FixedProvider
    body = _create(client)
    assert (body["category"], body["priority"], body["triaged_by"]) == ("roads", "low", "llm:groq")
    assert body["ai_summary"] == "Fixed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", "too short"),  # 9 chars
        ("text", "x" * 2001),
        ("location", "ab"),
        ("location", "x" * 201),
    ],
)
def test_invalid_input_returns_400_with_field_errors(client: TestClient, field: str, value: str):
    response = client.post("/api/complaints", json={**VALID, field: value})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["detail"][0]["loc"] == ["body", field]


def test_missing_fields_return_400(client: TestClient):
    response = client.post("/api/complaints", json={})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    missing = {tuple(e["loc"]) for e in response.json()["detail"]}
    assert {("body", "text"), ("body", "location")} <= missing


def test_failed_commit_is_an_error_not_a_201(client: TestClient, app, session_factory):
    """The service commits before responding, so a DB failure cannot be reported as success."""

    async def _failing_db():
        async with session_factory() as session:

            async def _boom() -> None:
                raise RuntimeError("commit failed")

            session.commit = _boom  # type: ignore[method-assign]
            try:
                yield session
            finally:
                await session.rollback()

    working_db = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = _failing_db
    try:
        with TestClient(app, raise_server_exceptions=False) as failing_client:
            response = failing_client.post("/api/complaints", json=VALID)
    finally:
        app.dependency_overrides[get_db] = working_db
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert client.get("/api/complaints").json()["total"] == 0


# ── GET one ──────────────────────────────────────────────────────────────────


def test_get_missing_complaint_returns_404(client: TestClient):
    response = client.get(f"/api/complaints/{uuid.uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["code"] == "not_found"


def test_get_malformed_id_returns_400(client: TestClient):
    response = client.get("/api/complaints/not-a-uuid")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── List ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def mixed(client: TestClient) -> None:
    _create(client, text="Bijli nahi aa rahi, transformer kharab hai teen din se")  # electricity
    _create(client, text="Kachra nahi uthaya gaya, gali mein badboo hai")  # sanitation
    _create(client, text="Minor pothole on the service road near the market")  # roads, low
    _create(client)  # water, high


def test_list_returns_total_and_newest_first(client: TestClient, mixed):
    body = client.get("/api/complaints").json()
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_pages"] == 1
    created = [c["created_at"] for c in body["complaints"]]
    assert created == sorted(created, reverse=True)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("category=electricity", {"electricity"}),
        ("priority=low", {"roads"}),
        ("priority=high&category=water", {"water"}),
        ("status=resolved", set()),
    ],
)
def test_list_filters(client: TestClient, mixed, query: str, expected: set[str]):
    body = client.get(f"/api/complaints?{query}").json()
    assert {c["category"] for c in body["complaints"]} == expected
    assert body["total"] == len(body["complaints"])


def test_list_status_filter(client: TestClient, mixed):
    first = client.get("/api/complaints").json()["complaints"][0]
    client.patch(f"/api/complaints/{first['id']}/status", json={"status": "in_progress"})
    body = client.get("/api/complaints?status=in_progress").json()
    assert [c["id"] for c in body["complaints"]] == [first["id"]]


def test_pagination_is_complete_and_stable(client: TestClient, mixed):
    page1 = client.get("/api/complaints?page=1&page_size=3").json()
    page2 = client.get("/api/complaints?page=2&page_size=3").json()
    assert page1["total"] == page2["total"] == 4
    assert page1["total_pages"] == 2
    ids = [c["id"] for c in page1["complaints"] + page2["complaints"]]
    assert len(ids) == len(set(ids)) == 4


@pytest.mark.parametrize(
    "query",
    ["page_size=101", "page_size=0", "page=0", "category=banana", "priority=urgent", "status=closed"],
)
def test_invalid_list_parameters_return_400(client: TestClient, query: str):
    response = client.get(f"/api/complaints?{query}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_page_size_100_is_allowed(client: TestClient):
    assert client.get("/api/complaints?page_size=100").status_code == status.HTTP_200_OK
