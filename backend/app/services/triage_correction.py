"""Service for operator triage corrections (assignment §2.2 / issue #46).

Allows human operators to correct a complaint's category and/or priority
when AI triage was inaccurate or manipulated by adversarial prompt injection.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.complaint import Category, Priority
from app.providers.cache import StatsCache
from app.repositories import complaint as complaint_repo
from app.schemas.complaint import ComplaintResponse
from app.services.status import to_response

logger = get_logger(__name__)


class TriageCorrectionService:
    def __init__(self, session: AsyncSession, stats_cache: StatsCache) -> None:
        self._session = session
        self._stats_cache = stats_cache

    async def correct_triage(
        self,
        complaint_id: uuid.UUID,
        *,
        category: Category | None = None,
        priority: Priority | None = None,
    ) -> ComplaintResponse:
        """Update category and/or priority for a complaint, recording operator correction."""
        complaint = await complaint_repo.get_complaint(self._session, complaint_id)
        if complaint is None:
            raise NotFoundError(f"Complaint {complaint_id} not found.")

        updated = await complaint_repo.update_triage(
            self._session,
            complaint_id,
            category=category.value if category else None,
            priority=priority.value if priority else None,
        )
        if updated is None:
            raise NotFoundError(f"Complaint {complaint_id} not found.")

        response = to_response(updated)
        # Commit before responding, then invalidate cache so stats reads reflect the update.
        await self._session.commit()
        await self._stats_cache.invalidate()

        logger.info(
            "complaint_triage_corrected",
            complaint_id=str(complaint_id),
            category=str(category) if category else None,
            priority=str(priority) if priority else None,
        )
        return response
