"""Aggregate statistics, read through the stats cache."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Category, Priority, Status
from app.providers.cache import StatsCache
from app.repositories import complaint as complaint_repo
from app.schemas.complaint import CategoryCount, PriorityCount, StatsResponse


class StatsService:
    def __init__(self, session: AsyncSession, stats_cache: StatsCache) -> None:
        self._session = session
        self._cache = stats_cache

    async def get_stats(self) -> tuple[StatsResponse, bool]:
        """Return ``(stats, cache_hit)``."""
        cached = await self._cache.get()
        if cached is not None:
            return StatsResponse.model_validate(cached), True

        stats = await self._compute()
        await self._cache.set(stats.model_dump(mode="json"))
        return stats, False

    async def _compute(self) -> StatsResponse:
        by_category = {row["category"]: row["count"] for row in
                       await complaint_repo.stats_by_category(self._session)}
        by_priority = {row["priority"]: row["count"] for row in
                       await complaint_repo.stats_by_priority(self._session)}
        by_status = await complaint_repo.stats_by_status(self._session)

        # Every enum value appears, with zero counts, so clients get a stable shape.
        return StatsResponse(
            total_complaints=sum(by_status.values()),
            by_category=[CategoryCount(category=c, count=by_category.get(c, 0)) for c in Category],
            by_priority=[PriorityCount(priority=p, count=by_priority.get(p, 0)) for p in Priority],
            open_count=by_status.get(Status.open, 0),
            in_progress_count=by_status.get(Status.in_progress, 0),
            resolved_count=by_status.get(Status.resolved, 0),
            rejected_count=by_status.get(Status.rejected, 0),
        )
