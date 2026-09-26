"""GET /api/stats — aggregates, with the cache outcome in X-Cache."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.dependencies import StatsServiceDep
from app.schemas.complaint import StatsResponse

router = APIRouter(tags=["Stats"])


@router.get("/stats", response_model=StatsResponse, summary="Aggregate complaint statistics")
async def get_stats(response: Response, service: StatsServiceDep) -> StatsResponse:
    stats, cache_hit = await service.get_stats()
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return stats
