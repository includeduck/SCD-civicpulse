"""Pydantic schemas for the Complaint API.

Separates transport-layer validation (schemas) from persistence (models).

Schema hierarchy:
  ComplaintCreate  → validated input for POST /api/complaints
  ComplaintResponse → full representation in API responses
  ComplaintListResponse → paginated list response
  StatusUpdateRequest → PATCH /api/complaints/{id}/status body
  StatsResponse → GET /api/stats response
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.complaint import Category, Priority, Status, TriagedBy


class ComplaintCreate(BaseModel):
    """Validated input payload for creating a new complaint (POST /api/complaints)."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Full description of the municipal complaint",
        examples=["Bijli nahin aa rahi, transformer khrab ho gaya hai pichle teen din se."],
    )
    location: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Physical location or area of the issue",
        examples=["Gulberg III, Main Boulevard, Block C"],
    )
    reporter_contact: str | None = Field(
        default=None,
        max_length=255,
        description="Optional contact (email, phone) for follow-up",
        examples=["03001234567"],
    )


class ComplaintResponse(BaseModel):
    """Complaint object returned by GET and POST responses.

    ``reporter_contact`` is deliberately excluded: the API has no
    authentication, so returning it would publish every reporter's phone or
    email on the public list endpoint (see ADR 0004). Enum-typed fields make
    the allowed values visible in OpenAPI for the typed frontend client.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    location: str
    category: Category
    priority: Priority
    status: Status
    ai_summary: str | None
    triaged_by: TriagedBy | None
    triage_latency_ms: int | None
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[Status] = Field(
        ...,
        description=(
            "Statuses this complaint may move to next, computed by the backend's "
            "state machine. The frontend renders these; it never hardcodes them."
        ),
    )


class ComplaintListResponse(BaseModel):
    """Paginated list of complaints."""

    complaints: list[ComplaintResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class StatusUpdateRequest(BaseModel):
    """Request body for PATCH /api/complaints/{id}/status."""

    status: Status = Field(..., description="Target status to transition to")


class CategoryCount(BaseModel):
    category: str
    count: int


class PriorityCount(BaseModel):
    priority: str
    count: int


class StatsResponse(BaseModel):
    """Aggregated statistics for GET /api/stats."""

    total_complaints: int
    by_category: list[CategoryCount]
    by_priority: list[PriorityCount]
    open_count: int
    in_progress_count: int
    resolved_count: int
    rejected_count: int
