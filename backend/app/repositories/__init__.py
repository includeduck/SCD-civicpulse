"""Data Access & Persistence Layer (Layer 3).

All SQL queries and database access MUST live in this layer.
Repositories receive an AsyncSession via dependency injection.
"""

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

__all__ = [
    "count_complaints",
    "create_complaint",
    "get_complaint",
    "list_complaints",
    "recent_triage_outcomes",
    "stats_by_category",
    "stats_by_priority",
    "stats_by_status",
    "update_status",
]
