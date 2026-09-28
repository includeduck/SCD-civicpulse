"""Add triage_corrected_at column to complaints table.

Revision ID: 0002_triage_correction
Revises: 0001_initial
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_triage_correction"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("triage_corrected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "triage_corrected_at")
