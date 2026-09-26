"""Tests for Pydantic schema validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.complaint import Category, Priority, Status
from app.schemas.complaint import (
    CategoryCount,
    ComplaintCreate,
    ComplaintResponse,
    PriorityCount,
    StatsResponse,
    StatusUpdateRequest,
)


def test_complaint_create_valid():
    data = ComplaintCreate(
        text="Pani ka masla hai pichle teen din se.",
        location="Gulberg III, Main Market",
        reporter_contact="03001234567",
    )
    assert data.text == "Pani ka masla hai pichle teen din se."
    assert data.location == "Gulberg III, Main Market"
    assert data.reporter_contact == "03001234567"


def test_complaint_create_too_short_text():
    with pytest.raises(ValidationError) as exc_info:
        ComplaintCreate(
            text="Too short",
            location="Gulberg",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("text",) for e in errors)


def test_complaint_create_too_short_location():
    with pytest.raises(ValidationError) as exc_info:
        ComplaintCreate(
            text="Valid complaint text with sufficient length.",
            location="No",
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("location",) for e in errors)


def test_complaint_response_from_attributes():
    cid = uuid.uuid4()
    now = datetime.now(UTC)
    res = ComplaintResponse(
        id=cid,
        text="Valid text description of issue",
        location="Some location",
        category="water",
        priority="high",
        status="open",
        ai_summary="Summary",
        triaged_by="simulated",
        triage_latency_ms=120,
        created_at=now,
        updated_at=now,
        allowed_transitions=["in_progress", "rejected"],
    )
    assert res.id == cid
    assert res.category == Category.water
    assert res.priority == Priority.high


def test_complaint_response_never_exposes_reporter_contact():
    """Contact details are PII and must not leak through the unauthenticated API."""
    from types import SimpleNamespace

    now = datetime.now(UTC)
    orm_like = SimpleNamespace(
        id=uuid.uuid4(),
        text="Valid text description of issue",
        location="Some location",
        reporter_contact="03001234567",
        category="water",
        priority="high",
        status="open",
        ai_summary=None,
        triaged_by="rules",
        triage_latency_ms=5,
        created_at=now,
        updated_at=now,
        allowed_transitions=[],
    )
    dumped = ComplaintResponse.model_validate(orm_like).model_dump()
    assert "reporter_contact" not in dumped
    assert "reporter_contact" not in ComplaintResponse.model_json_schema()["properties"]


def test_complaint_response_rejects_unknown_enum_values():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ComplaintResponse(
            id=uuid.uuid4(),
            text="Valid text description of issue",
            location="Some location",
            category="banana",
            priority="high",
            status="open",
            ai_summary=None,
            triaged_by=None,
            triage_latency_ms=None,
            created_at=now,
            updated_at=now,
            allowed_transitions=[],
        )


def test_status_update_request():
    req = StatusUpdateRequest(status=Status.in_progress)
    assert req.status == Status.in_progress

    with pytest.raises(ValidationError):
        StatusUpdateRequest(status="invalid_status")  # type: ignore[arg-type]


def test_stats_response():
    stats = StatsResponse(
        total_complaints=10,
        by_category=[CategoryCount(category="water", count=6), CategoryCount(category="roads", count=4)],
        by_priority=[PriorityCount(priority="high", count=7), PriorityCount(priority="normal", count=3)],
        open_count=5,
        in_progress_count=3,
        resolved_count=2,
        rejected_count=0,
    )
    assert stats.total_complaints == 10
    assert len(stats.by_category) == 2
