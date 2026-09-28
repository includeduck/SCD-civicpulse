"""Complaint repository — all SQL lives here.

Layer 3 of the 4-layer architecture. This module is the ONLY place
that issues SQL queries for complaints. Services receive a session
via dependency injection and pass it into repository functions.

Query → Index mapping:
  list_complaints(status=..., priority=...) → idx_complaint_status_priority
  list_complaints(order_by=created_at)      → idx_complaint_created_at
  stats_by_category / stats_by_priority     → full table scan (small table)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Category, Complaint, Priority, Status


async def create_complaint(
    session: AsyncSession,
    *,
    text: str,
    location: str,
    complaint_id: uuid.UUID | None = None,
    reporter_contact: str | None = None,
    category: str = Category.other,
    priority: str = Priority.normal,
    status: str = Status.open,
    ai_summary: str | None = None,
    triaged_by: str | None = None,
    triage_latency_ms: int | None = None,
) -> Complaint:
    """Persist a new complaint and return the hydrated ORM object.

    ``complaint_id`` lets the service assign the id before triage, so a triage
    fallback warning can name the complaint it belongs to.
    """
    complaint = Complaint(
        id=complaint_id or uuid.uuid4(),
        text=text,
        location=location,
        reporter_contact=reporter_contact,
        category=category,
        priority=priority,
        status=status,
        ai_summary=ai_summary,
        triaged_by=triaged_by,
        triage_latency_ms=triage_latency_ms,
    )
    session.add(complaint)
    await session.flush()  # populate .id without closing the transaction
    await session.refresh(complaint)
    return complaint


async def get_complaint(session: AsyncSession, complaint_id: uuid.UUID) -> Complaint | None:
    """Return a single Complaint by primary key, or None if not found."""
    result = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
    return result.scalar_one_or_none()


async def list_complaints(
    session: AsyncSession,
    *,
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[Complaint]:
    """Return a paginated list of complaints with optional enum filters.

    Served by idx_complaint_status_priority (when filtering on status+priority)
    and idx_complaint_created_at (ordering).
    """
    # id is a tie-breaker so rows sharing a created_at never shift between pages.
    stmt = select(Complaint).order_by(Complaint.created_at.desc(), Complaint.id.desc())

    if category is not None:
        stmt = stmt.where(Complaint.category == category)
    if priority is not None:
        stmt = stmt.where(Complaint.priority == priority)
    if status is not None:
        stmt = stmt.where(Complaint.status == status)

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_complaints(
    session: AsyncSession,
    *,
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
) -> int:
    """Return total matching count for a filtered list query (for pagination metadata)."""
    stmt = select(func.count()).select_from(Complaint)

    if category is not None:
        stmt = stmt.where(Complaint.category == category)
    if priority is not None:
        stmt = stmt.where(Complaint.priority == priority)
    if status is not None:
        stmt = stmt.where(Complaint.status == status)

    result = await session.execute(stmt)
    return result.scalar_one()


async def update_status(
    session: AsyncSession,
    complaint_id: uuid.UUID,
    new_status: str,
    *,
    expected_status: str,
) -> Complaint | None:
    """Atomically move a complaint from ``expected_status`` to ``new_status``.

    The WHERE clause includes the expected current status (compare-and-set), so
    two concurrent transitions cannot both succeed. Returns the updated complaint,
    or None if the complaint does not exist *or* its status is no longer
    ``expected_status``; the caller re-reads to tell 404 from 409.
    """
    stmt = (
        update(Complaint)
        .where(Complaint.id == complaint_id, Complaint.status == expected_status)
        .values(status=new_status, updated_at=datetime.now(UTC))
        .returning(Complaint)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_triage(
    session: AsyncSession,
    complaint_id: uuid.UUID,
    *,
    category: str | None = None,
    priority: str | None = None,
    corrected_at: datetime | None = None,
) -> Complaint | None:
    """Update a complaint's category and/or priority and set triage_corrected_at.

    Returns the updated Complaint, or None if no complaint with complaint_id exists.
    """
    values: dict[str, Any] = {
        "updated_at": datetime.now(UTC),
        "triage_corrected_at": corrected_at or datetime.now(UTC),
    }
    if category is not None:
        values["category"] = category
    if priority is not None:
        values["priority"] = priority

    stmt = (
        update(Complaint).where(Complaint.id == complaint_id).values(**values).returning(Complaint)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def stats_by_category(session: AsyncSession) -> list[dict[str, Any]]:
    """Return complaint counts grouped by category.

    The aggregate is labelled "total", not "count": ``row.count`` would collide
    with the ``Row.count()`` sequence method.
    """
    stmt = (
        select(Complaint.category, func.count().label("total"))
        .group_by(Complaint.category)
        .order_by(Complaint.category)
    )
    result = await session.execute(stmt)
    return [{"category": row.category, "count": row.total} for row in result]


async def stats_by_priority(session: AsyncSession) -> list[dict[str, Any]]:
    """Return complaint counts grouped by priority."""
    stmt = (
        select(Complaint.priority, func.count().label("total"))
        .group_by(Complaint.priority)
        .order_by(Complaint.priority)
    )
    result = await session.execute(stmt)
    return [{"priority": row.priority, "count": row.total} for row in result]


async def stats_by_status(session: AsyncSession) -> dict[str, int]:
    """Return complaint counts keyed by status string."""
    stmt = select(Complaint.status, func.count().label("total")).group_by(Complaint.status)
    result = await session.execute(stmt)
    return {row.status: row.total for row in result}


async def recent_triage_outcomes(session: AsyncSession, limit: int = 10) -> list[Complaint]:
    """Return the most recent complaints with their triage results (for /api/meta)."""
    stmt = (
        select(Complaint)
        .where(Complaint.triaged_by.isnot(None))
        .order_by(Complaint.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
