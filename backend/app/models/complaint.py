"""SQLAlchemy data model for the Complaint entity.

Constraints:
- text:     10–2000 chars (DB-level CHECK + application validation)
- location: 3–200 chars   (DB-level CHECK + application validation)
- ai_summary: <=140 chars

Enums are stored as VARCHAR in Postgres (not native PG ENUM) so that Alembic
migrations can add/rename values without complex ALTER TYPE migrations.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ── Enum Types ───────────────────────────────────────────────────────────────


class Category(enum.StrEnum):
    water = "water"
    electricity = "electricity"
    sanitation = "sanitation"
    roads = "roads"
    streetlights = "streetlights"
    other = "other"


class Priority(enum.StrEnum):
    high = "high"
    normal = "normal"
    low = "low"


class Status(enum.StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    rejected = "rejected"


class TriagedBy(enum.StrEnum):
    llm_groq = "llm:groq"
    llm_ollama = "llm:ollama"
    rules = "rules"
    rules_fallback = "rules:fallback"
    simulated = "simulated"


# ── ORM Base ─────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── Complaint Model ───────────────────────────────────────────────────────────


class Complaint(Base):
    """Central entity representing a single municipal complaint submission.

    Indexes:
    - idx_complaint_status_priority → serves list_complaints filtered by status+priority
    - idx_complaint_created_at     → serves list_complaints sorted by creation time
    """

    __tablename__ = "complaints"

    # Constraints live in __table_args__ so Alembic generates proper DDL.
    __table_args__ = (
        CheckConstraint("length(text) >= 10", name="ck_complaint_text_min"),
        CheckConstraint("length(text) <= 2000", name="ck_complaint_text_max"),
        CheckConstraint("length(location) >= 3", name="ck_complaint_location_min"),
        CheckConstraint("length(location) <= 200", name="ck_complaint_location_max"),
        CheckConstraint(
            "ai_summary IS NULL OR length(ai_summary) <= 140",
            name="ck_complaint_summary_max",
        ),
        Index("idx_complaint_status_priority", "status", "priority"),
        Index("idx_complaint_created_at", "created_at"),
    )

    # ── Primary Key ──────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Core Fields ──────────────────────────────────────────────────────────
    text: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    reporter_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Domain Status ────────────────────────────────────────────────────────
    # Stored as VARCHAR; enum validation happens in the application layer.
    category: Mapped[str] = mapped_column(String(32), nullable=False, default=Category.other)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default=Priority.normal)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=Status.open)

    # ── AI Triage Fields ─────────────────────────────────────────────────────
    ai_summary: Mapped[str | None] = mapped_column(String(140), nullable=True)
    triaged_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Complaint id={self.id} status={self.status} "
            f"category={self.category} priority={self.priority}>"
        )
