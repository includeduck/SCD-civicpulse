"""SimulatedTriage: seeded, deterministic, offline, with failure injection."""

from __future__ import annotations

import socket

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.dependencies import get_triage_provider
from app.providers.triage.base import (
    TriageBadRequestError,
    TriageError,
    TriageProvider,
    TriageRateLimitedError,
    TriageResult,
    TriageServerError,
    TriageTimeoutError,
)
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage.simulated import SimulatedTriage

TEXT = "Burst water main flooding Street 12 since fajr, water entering ground floors"
LOCATION = "Street 12, G-10/2"
INPUTS = [(f"Complaint {i}: paani ki pipe phat gayi hai", f"Sector {i}") for i in range(200)]


def test_satisfies_provider_protocol():
    provider = SimulatedTriage()
    assert isinstance(provider, TriageProvider)
    assert provider.name == "simulated"


def test_deterministic_across_calls_and_instances():
    first = SimulatedTriage(seed=7).triage(TEXT, LOCATION)
    assert all(SimulatedTriage(seed=7).triage(TEXT, LOCATION) == first for _ in range(5))


def test_seed_changes_confidence_not_classification():
    a = SimulatedTriage(seed=1).triage(TEXT, LOCATION)
    b = SimulatedTriage(seed=2).triage(TEXT, LOCATION)
    assert (a.category, a.priority) == (b.category, b.priority)
    assert a.confidence != b.confidence


def test_outcome_is_predictable_from_input():
    """Category/priority follow the rule engine, so CI can assert a real category."""
    simulated = SimulatedTriage().triage(TEXT, LOCATION)
    ruled = RuleBasedTriage().triage(TEXT, LOCATION)
    assert (simulated.category, simulated.priority) == (ruled.category, ruled.priority)
    assert simulated.summary.startswith("[simulated] ")


def test_output_always_valid():
    provider = SimulatedTriage()
    for text, location in INPUTS[:50] + [("x" * 2000, "Anywhere")]:
        result = provider.triage(text, location)
        TriageResult.model_validate(result.model_dump())
        assert len(result.summary) <= 140
        assert 0.5 <= result.confidence <= 1.0


def test_never_touches_the_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("SimulatedTriage opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    SimulatedTriage().triage(TEXT, LOCATION)


@pytest.mark.parametrize(
    ("mode", "error", "retryable"),
    [
        ("timeout", TriageTimeoutError, True),
        ("rate_limited", TriageRateLimitedError, True),
        ("server_error", TriageServerError, True),
        ("bad_request", TriageBadRequestError, False),
        ("error", TriageError, False),
    ],
)
def test_failure_injection_raises_typed_errors(mode, error, retryable):
    provider = SimulatedTriage(failure_mode=mode)
    with pytest.raises(error) as caught:
        provider.triage(TEXT, LOCATION)
    assert type(caught.value) is error
    assert caught.value.retryable is retryable


def test_invalid_mode_returns_output_that_fails_validation():
    result = SimulatedTriage(failure_mode="invalid").triage(TEXT, LOCATION)
    with pytest.raises(ValueError):
        TriageResult.model_validate(result.model_dump())


def test_failure_rate_zero_never_fails():
    provider = SimulatedTriage(failure_mode="error", failure_rate=0.0)
    for text, location in INPUTS:
        provider.triage(text, location)


def test_partial_failure_rate_is_deterministic_per_input():
    provider = SimulatedTriage(seed=3, failure_mode="timeout", failure_rate=0.3)
    decisions = [provider.should_fail(t, loc) for t, loc in INPUTS]
    assert decisions == [provider.should_fail(t, loc) for t, loc in INPUTS]
    assert 0.2 < sum(decisions) / len(decisions) < 0.4


@pytest.mark.parametrize(("kwargs"), [{"failure_rate": 1.5}, {"failure_mode": "explode"}])
def test_rejects_bad_configuration(kwargs):
    with pytest.raises(ValueError):
        SimulatedTriage(**kwargs)


# ── Through the API: failures fall back to rules (Phase 5) ──────────────────


@pytest.mark.parametrize("mode", ["invalid", "timeout", "bad_request", "error"])
def test_injected_failures_fall_back_to_rules(client: TestClient, app, mode):
    """Bad provider output is never blamed on the citizen, and never a 500."""
    app.dependency_overrides[get_triage_provider] = lambda: SimulatedTriage(failure_mode=mode)
    response = client.post("/api/complaints", json={"text": TEXT, "location": LOCATION})
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["triaged_by"] == "rules:fallback"
    assert (body["category"], body["priority"]) == ("water", "high")
