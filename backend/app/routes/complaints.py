"""Complaints API route placeholders (Phase 1 structure).

Full CRUD, AI triage, rate limiting, and status state machine
will be wired in Phase 3.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.get("", summary="List complaints placeholder")
async def list_complaints():
    return {"complaints": [], "total": 0, "page": 1, "page_size": 20}
