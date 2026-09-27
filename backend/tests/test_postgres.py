"""Behaviour that SQLite cannot prove, run against a real PostgreSQL 16.

Skipped unless TEST_DATABASE_URL points at a disposable database, e.g.

    docker run -d --name civicpulse-pg-test -e POSTGRES_USER=civicpulse \\
        -e POSTGRES_PASSWORD=civicpulse -e POSTGRES_DB=civicpulse_test \\
        -p 55432:5432 postgres:16-alpine
    TEST_DATABASE_URL=postgresql+asyncpg://civicpulse:civicpulse@localhost:55432/civicpulse_test pytest tests/test_postgres.py

The schema is created with Alembic (never metadata.create_all), so these tests
also prove the migration itself.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.complaint import Status
from app.repositories.complaint import create_complaint, get_complaint, update_status

PG_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic(direction: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    getattr(command, direction)(cfg, target)


@pytest.fixture(scope="module", autouse=True)
def migrated(monkeypatch_module) -> Generator[None, None, None]:
    monkeypatch_module.setenv("DATABASE_URL", PG_URL)
    _alembic("downgrade", "base")
    _alembic("upgrade", "head")
    yield
    _alembic("downgrade", "base")


@pytest.fixture(scope="module")
def monkeypatch_module() -> Generator[pytest.MonkeyPatch, None, None]:
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(PG_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        await s.execute(text("TRUNCATE complaints"))
        await s.commit()
        yield s
    await engine.dispose()


async def test_migration_creates_required_indexes(session: AsyncSession):
    rows = await session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'complaints'")
    )
    names = {r.indexname for r in rows}
    assert {"idx_complaint_status_priority", "idx_complaint_created_at"} <= names


@pytest.mark.parametrize(
    ("column", "value"),
    [("text", "too short"), ("text", "x" * 2001), ("location", "ab"), ("location", "x" * 201)],
)
async def test_length_checks_are_enforced_by_the_database(session: AsyncSession, column, value):
    """Raw SQL bypasses Pydantic; the DB must still refuse out-of-range values.

    Too-short values hit the CHECK constraints (IntegrityError); an over-long
    location hits VARCHAR(200) (DataError). Both are DBAPIErrors.
    """
    values = {"text": "A valid complaint text", "location": "Valid place", column: value}
    with pytest.raises(DBAPIError):
        await session.execute(
            text("INSERT INTO complaints (text, location) VALUES (:text, :location)"), values
        )
    await session.rollback()


async def test_database_generates_uuid_and_utc_timestamps(session: AsyncSession):
    row = (
        await session.execute(
            text(
                "INSERT INTO complaints (text, location) VALUES ('Paani nahi aa raha', 'G-11') "
                "RETURNING id, status, created_at, updated_at"
            )
        )
    ).one()
    await session.commit()
    assert isinstance(row.id, uuid.UUID)
    assert row.status == "open"
    assert row.created_at.utcoffset().total_seconds() == 0
    assert row.updated_at.tzinfo is not None


async def test_compare_and_set_status_update(session: AsyncSession):
    complaint = await create_complaint(session, text="Transformer kharab hai", location="I-8")
    await session.commit()
    complaint_id = complaint.id

    assert await update_status(
        session, complaint.id, Status.in_progress, expected_status=Status.open
    )
    await session.commit()
    stale = await update_status(session, complaint.id, Status.rejected, expected_status=Status.open)
    await session.commit()
    assert stale is None
    session.expire_all()
    assert (await get_complaint(session, complaint_id)).status == Status.in_progress


async def test_seed_is_idempotent(session: AsyncSession, monkeypatch):
    from scripts.seed_db import COMPLAINTS, run_seed

    monkeypatch.setenv("DATABASE_URL", PG_URL)
    await run_seed()
    first = (await session.execute(text("SELECT count(*) FROM complaints"))).scalar_one()
    await run_seed()
    second = (await session.execute(text("SELECT count(*) FROM complaints"))).scalar_one()
    assert first == second == len(COMPLAINTS) >= 30


async def test_wait_for_schema_returns_once_the_schema_is_at_head():
    """The backend's initContainer: passes immediately against a migrated database."""
    from scripts.wait_for_schema import current_revision, expected_head, wait

    assert await current_revision(PG_URL) == expected_head()
    assert await wait(PG_URL, timeout=0) is True
