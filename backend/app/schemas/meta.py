"""Schemas for GET /api/meta/providers — the triage observability surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ProviderMeta(BaseModel):
    name: str  # TRIAGE_PROVIDER value that selects this provider
    triaged_by: str  # label recorded on complaints triaged by this provider
    active: bool
    timeout_seconds: int
    fallback_provider: str | None = None
    description: str


class TriageOutcome(BaseModel):
    """One recent triage: which provider answered, how long it took, and whether it fell back."""

    complaint_id: uuid.UUID
    provider: str
    latency_ms: int | None
    fallback: bool
    created_at: datetime


class ProvidersResponse(BaseModel):
    active_provider: str
    providers: list[ProviderMeta]
    recent_outcomes: list[TriageOutcome]
