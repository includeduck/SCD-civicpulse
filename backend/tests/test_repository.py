"""Tests for Phase 2: Database Models and Repository Layer.

Uses an in-memory SQLite database via aiosqlite to verify all repository operations,
model constraints, ordering, filtering, aggregations, and seed idempotency.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.complaint import Base, Category, Priority, Status
from app.repositories.complaint import (
    count_complaints,
    create_complaint,
    get_complaint,
    list_complaints,
    recent_triage_outcomes,
    stats_by_category,
    stats_by_priority,
    stats_by_status,
    update_status,
)
from scripts.seed_db import COMPLAINTS, seed_uuid


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, clean SQLite in-memory database session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_complaint(db_session: AsyncSession):
    """Test creating a complaint and retrieving it by primary key."""
    complaint = await create_complaint(
        db_session,
        text="Gutter line block ho gayi hai aur gandagi sarak par phail rahi hai.",
        location="Gulshan-e-Iqbal Block 13D",
        category=Category.sanitation,
        priority=Priority.high,
        status=Status.open,
        ai_summary="Blocked gutter causing sewage on road",
        triaged_by="simulated",
        triage_latency_ms=150,
    )
    await db_session.commit()

    assert complaint.id is not None
    assert isinstance(complaint.id, uuid.UUID)
    assert complaint.status == Status.open
    assert complaint.category == Category.sanitation
    assert complaint.created_at is not None

    # Retrieve existing
    fetched = await get_complaint(db_session, complaint.id)
    assert fetched is not None
    assert fetched.id == complaint.id
    assert fetched.text == complaint.text

    # Retrieve non-existent
    missing = await get_complaint(db_session, uuid.uuid4())
    assert missing is None


@pytest.mark.asyncio
async def test_list_and_count_complaints(db_session: AsyncSession):
    """Test listing complaints with pagination and counting."""
    for i in range(5):
        await create_complaint(
            db_session,
            text=f"Complaint description test number {i:02d} for municipal area.",
            location=f"Area Block {i}",
            category=Category.water if i % 2 == 0 else Category.electricity,
            priority=Priority.high if i < 3 else Priority.low,
            status=Status.open,
        )
    await db_session.commit()

    # Total count
    total = await count_complaints(db_session)
    assert total == 5

    # Paginated page 1
    page1 = await list_complaints(db_session, page=1, page_size=2)
    assert len(page1) == 2

    # Paginated page 2
    page2 = await list_complaints(db_session, page=2, page_size=2)
    assert len(page2) == 2
    assert page1[0].id != page2[0].id

    # Filter by category
    water_complaints = await list_complaints(db_session, category=Category.water)
    assert len(water_complaints) == 3

    # Filter by priority
    high_count = await count_complaints(db_session, priority=Priority.high)
    assert high_count == 3


@pytest.mark.asyncio
async def test_update_status(db_session: AsyncSession):
    """Test updating the status of a complaint."""
    complaint = await create_complaint(
        db_session,
        text="Bijli ki taar gir gayi hai sarak ke beech mein.",
        location="Mall Road near High Court",
        category=Category.electricity,
        priority=Priority.high,
        status=Status.open,
    )
    await db_session.commit()

    updated = await update_status(
        db_session, complaint.id, Status.in_progress, expected_status=Status.open
    )
    await db_session.commit()

    assert updated is not None
    assert updated.status == Status.in_progress
    c_time = complaint.created_at if complaint.created_at.tzinfo else complaint.created_at.replace(tzinfo=UTC)
    u_time = updated.updated_at if updated.updated_at.tzinfo else updated.updated_at.replace(tzinfo=UTC)
    assert u_time >= c_time

    # Update non-existent complaint
    missing = await update_status(
        db_session, uuid.uuid4(), Status.resolved, expected_status=Status.in_progress
    )
    assert missing is None


@pytest.mark.asyncio
async def test_update_status_is_compare_and_set(db_session: AsyncSession):
    """A transition based on a stale status must not apply (concurrent PATCH race)."""
    complaint = await create_complaint(
        db_session,
        text="Sarak par bara gharha hai, gaariyan phas rahi hain.",
        location="Canal Road, Faisal Town",
        status=Status.open,
    )
    await db_session.commit()

    first = await update_status(
        db_session, complaint.id, Status.in_progress, expected_status=Status.open
    )
    assert first is not None

    # A second request that also read "open" before the first one committed.
    second = await update_status(
        db_session, complaint.id, Status.rejected, expected_status=Status.open
    )
    assert second is None

    current = await get_complaint(db_session, complaint.id)
    assert current is not None
    assert current.status == Status.in_progress


@pytest.mark.asyncio
async def test_list_order_is_stable_for_equal_timestamps(db_session: AsyncSession):
    """Rows with identical created_at must page deterministically (id tie-breaker)."""
    from datetime import datetime

    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        c = await create_complaint(
            db_session, text=f"Kachra nahin uthaya gaya {i} din se.", location="DHA Phase 5"
        )
        c.created_at = same_time
    await db_session.commit()

    page1 = await list_complaints(db_session, page=1, page_size=3)
    page2 = await list_complaints(db_session, page=2, page_size=3)
    ids = [c.id for c in page1 + page2]
    assert len(ids) == len(set(ids)) == 5
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_stats_aggregations(db_session: AsyncSession):
    """Test category, priority, and status aggregation queries."""
    await create_complaint(
        db_session,
        text="Water supply issue in block A",
        location="Block A",
        category=Category.water,
        priority=Priority.high,
        status=Status.open,
    )
    await create_complaint(
        db_session,
        text="Water supply issue in block B",
        location="Block B",
        category=Category.water,
        priority=Priority.normal,
        status=Status.in_progress,
    )
    await create_complaint(
        db_session,
        text="Road pothole near intersection",
        location="Main intersection",
        category=Category.roads,
        priority=Priority.high,
        status=Status.resolved,
    )
    await db_session.commit()

    cat_stats = await stats_by_category(db_session)
    cat_map = {item["category"]: item["count"] for item in cat_stats}
    assert cat_map[Category.water] == 2
    assert cat_map[Category.roads] == 1

    prio_stats = await stats_by_priority(db_session)
    prio_map = {item["priority"]: item["count"] for item in prio_stats}
    assert prio_map[Priority.high] == 2
    assert prio_map[Priority.normal] == 1

    status_map = await stats_by_status(db_session)
    assert status_map[Status.open] == 1
    assert status_map[Status.in_progress] == 1
    assert status_map[Status.resolved] == 1


@pytest.mark.asyncio
async def test_recent_triage_outcomes(db_session: AsyncSession):
    """Test querying recent triage outcomes."""
    await create_complaint(
        db_session,
        text="Complaint without triage result",
        location="Location 1",
        category=Category.other,
    )
    await create_complaint(
        db_session,
        text="Complaint with simulated triage",
        location="Location 2",
        category=Category.sanitation,
        triaged_by="simulated",
        triage_latency_ms=100,
    )
    await db_session.commit()

    recent = await recent_triage_outcomes(db_session, limit=5)
    assert len(recent) == 1
    assert recent[0].triaged_by == "simulated"


@pytest.mark.asyncio
async def test_seed_idempotency(db_session: AsyncSession):
    """Verify seed execution idempotency: running twice does not produce duplicates."""
    from app.models.complaint import Complaint

    # First run
    for data in COMPLAINTS:
        det_id = seed_uuid(data["seed_key"])
        c = Complaint(
            id=det_id,
            text=data["text"],
            location=data["location"],
            category=data["category"],
            priority=data["priority"],
            status=data["status"],
            ai_summary=data.get("ai_summary"),
            triaged_by=data.get("triaged_by"),
            triage_latency_ms=data.get("triage_latency_ms"),
        )
        db_session.add(c)
    await db_session.commit()

    count_first_run = await count_complaints(db_session)
    assert count_first_run >= 30

    # Second run: attempt to insert again, skipping existing IDs
    skipped_count = 0
    for data in COMPLAINTS:
        det_id = seed_uuid(data["seed_key"])
        existing = await get_complaint(db_session, det_id)
        if existing is not None:
            skipped_count += 1
            continue
        c = Complaint(
            id=det_id,
            text=data["text"],
            location=data["location"],
        )
        db_session.add(c)
    await db_session.commit()

    count_second_run = await count_complaints(db_session)
    assert skipped_count == len(COMPLAINTS)
    assert count_second_run == count_first_run
