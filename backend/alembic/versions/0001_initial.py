"""Initial migration — create complaints table.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-25

Tables created:
- complaints (with DB-level CHECK constraints and composite indexes)

Indexes:
- idx_complaint_status_priority  → serves filtered list queries
- idx_complaint_created_at       → serves time-ordered pagination
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "complaints",
        # ── Primary Key ───────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # ── Core Fields ───────────────────────────────────────────────────
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("reporter_contact", sa.String(length=255), nullable=True),
        # ── Domain Status ─────────────────────────────────────────────────
        sa.Column("category", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        # ── AI Triage ─────────────────────────────────────────────────────
        sa.Column("ai_summary", sa.String(length=140), nullable=True),
        sa.Column("triaged_by", sa.String(length=32), nullable=True),
        sa.Column("triage_latency_ms", sa.Integer(), nullable=True),
        # ── Timestamps ────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # ── Primary Key Constraint ────────────────────────────────────────
        sa.PrimaryKeyConstraint("id"),
        # ── DB-level CHECK Constraints (per §1.2) ─────────────────────────
        sa.CheckConstraint("length(text) >= 10", name="ck_complaint_text_min"),
        sa.CheckConstraint("length(text) <= 2000", name="ck_complaint_text_max"),
        sa.CheckConstraint("length(location) >= 3", name="ck_complaint_location_min"),
        sa.CheckConstraint("length(location) <= 200", name="ck_complaint_location_max"),
        sa.CheckConstraint(
            "ai_summary IS NULL OR length(ai_summary) <= 140",
            name="ck_complaint_summary_max",
        ),
    )

    # ── Indexes (per §1.2) ────────────────────────────────────────────────────
    op.create_index(
        "idx_complaint_status_priority",
        "complaints",
        ["status", "priority"],
        unique=False,
    )
    op.create_index(
        "idx_complaint_created_at",
        "complaints",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_complaint_created_at", table_name="complaints")
    op.drop_index("idx_complaint_status_priority", table_name="complaints")
    op.drop_table("complaints")
