"""Status state machine (assignment §2.2): explicit table, 409 naming the transition."""

from __future__ import annotations

import itertools
import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.models.complaint import Status
from app.services import status as status_service
from app.services.status import ALLOWED_TRANSITIONS, allowed_transitions

VALID = {"text": "Kachra teen din se nahi uthaya gaya, gali mein badboo hai", "location": "Saddar"}

# Shortest path from "open" to each status, used to put a complaint into that state.
PATH_TO = {
    Status.open: [],
    Status.in_progress: [Status.in_progress],
    Status.resolved: [Status.in_progress, Status.resolved],
    Status.rejected: [Status.rejected],
}

VALID_EDGES = {
    (Status.open, Status.in_progress),
    (Status.open, Status.rejected),
    (Status.in_progress, Status.resolved),
    (Status.in_progress, Status.rejected),
}


def _complaint_in(client: TestClient, state: Status) -> str:
    complaint_id = client.post("/api/complaints", json=VALID).json()["id"]
    for step in PATH_TO[state]:
        response = client.patch(f"/api/complaints/{complaint_id}/status", json={"status": step})
        assert response.status_code == status.HTTP_200_OK, response.text
    return complaint_id


def test_table_matches_assignment():
    assert {(a, b) for a, targets in ALLOWED_TRANSITIONS.items() for b in targets} == VALID_EDGES
    assert set(ALLOWED_TRANSITIONS) == set(Status)


@pytest.mark.parametrize(("current", "target"), sorted(VALID_EDGES))
def test_every_valid_transition(client: TestClient, current: Status, target: Status):
    complaint_id = _complaint_in(client, current)
    response = client.patch(f"/api/complaints/{complaint_id}/status", json={"status": target})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == target
    assert body["allowed_transitions"] == allowed_transitions(target)
    assert client.get(f"/api/complaints/{complaint_id}").json()["status"] == target


INVALID_EDGES = sorted(set(itertools.product(Status, Status)) - VALID_EDGES)


@pytest.mark.parametrize(("current", "target"), INVALID_EDGES)
def test_every_invalid_transition_is_409_naming_it(
    client: TestClient, current: Status, target: Status
):
    """Includes same-status requests and every move out of a terminal state."""
    complaint_id = _complaint_in(client, current)
    response = client.patch(f"/api/complaints/{complaint_id}/status", json={"status": target})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f"Cannot transition complaint from '{current}' to '{target}'.",
        "code": "invalid_transition",
    }
    assert client.get(f"/api/complaints/{complaint_id}").json()["status"] == current


@pytest.mark.parametrize("terminal", [Status.resolved, Status.rejected])
def test_terminal_states_offer_no_transitions(client: TestClient, terminal: Status):
    complaint_id = _complaint_in(client, terminal)
    assert client.get(f"/api/complaints/{complaint_id}").json()["allowed_transitions"] == []


def test_unknown_complaint_is_404(client: TestClient):
    response = client.patch(
        f"/api/complaints/{uuid.uuid4()}/status", json={"status": "in_progress"}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_unknown_status_value_is_400(client: TestClient):
    complaint_id = _complaint_in(client, Status.open)
    response = client.patch(f"/api/complaints/{complaint_id}/status", json={"status": "closed"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_concurrent_transition_loses_with_409(client: TestClient, monkeypatch):
    """Two operators act on the same open complaint; the second must not overwrite the first."""
    complaint_id = _complaint_in(client, Status.open)
    real_update = status_service.complaint_repo.update_status

    async def racing_update(session, cid, new_status, *, expected_status):
        # Another request rejects the complaint between our read and our write.
        await real_update(session, cid, Status.rejected, expected_status=Status.open)
        return await real_update(session, cid, new_status, expected_status=expected_status)

    monkeypatch.setattr(status_service.complaint_repo, "update_status", racing_update)
    response = client.patch(
        f"/api/complaints/{complaint_id}/status", json={"status": "in_progress"}
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert (
        response.json()["detail"] == "Cannot transition complaint from 'rejected' to 'in_progress'."
    )
