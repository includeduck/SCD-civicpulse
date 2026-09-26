"""Complaint intake and queries: validate -> rate-limit -> triage -> persist."""

from __future__ import annotations

import math
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.complaint import Category, Priority, Status
from app.providers.cache import StatsCache
from app.providers.rate_limit import RateLimiter
from app.providers.triage.base import TriageProvider, TriageResult
from app.repositories import complaint as complaint_repo
from app.schemas.complaint import ComplaintCreate, ComplaintListResponse, ComplaintResponse
from app.services.status import to_response

logger = get_logger(__name__)


class ComplaintService:
    def __init__(
        self,
        session: AsyncSession,
        triage_provider: TriageProvider,
        stats_cache: StatsCache,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._triage = triage_provider
        self._stats_cache = stats_cache
        self._rate_limiter = rate_limiter

    async def create(self, payload: ComplaintCreate, client_ip: str) -> ComplaintResponse:
        await self._rate_limiter.check(client_ip)

        result, latency_ms = await self._run_triage(payload.text, payload.location)

        complaint = await complaint_repo.create_complaint(
            self._session,
            text=payload.text,
            location=payload.location,
            reporter_contact=payload.reporter_contact,
            category=result.category,
            priority=result.priority,
            ai_summary=result.summary,
            triaged_by=self._triage.name,
            triage_latency_ms=latency_ms,
        )
        response = to_response(complaint)
        # Commit before responding; a failed commit must surface as an error,
        # never as a 201 for a row that does not exist.
        await self._session.commit()
        await self._stats_cache.invalidate()

        logger.info(
            "complaint_created",
            complaint_id=str(complaint.id),
            category=str(result.category),
            priority=str(result.priority),
            triaged_by=self._triage.name,
            triage_latency_ms=latency_ms,
        )
        return response

    async def _run_triage(self, text: str, location: str) -> tuple[TriageResult, int]:
        """Run the (synchronous) provider off the event loop and time it."""
        started = time.perf_counter()
        result = await run_in_threadpool(self._triage.triage, text, location)
        latency_ms = round((time.perf_counter() - started) * 1000)
        # Re-validate: providers are untrusted, whatever they claim to return.
        return TriageResult.model_validate(result.model_dump()), latency_ms

    async def get(self, complaint_id: uuid.UUID) -> ComplaintResponse:
        complaint = await complaint_repo.get_complaint(self._session, complaint_id)
        if complaint is None:
            raise NotFoundError(f"Complaint {complaint_id} not found.")
        return to_response(complaint)

    async def list_complaints(
        self,
        *,
        category: Category | None,
        priority: Priority | None,
        status: Status | None,
        page: int,
        page_size: int,
    ) -> ComplaintListResponse:
        filters = {"category": category, "priority": priority, "status": status}
        total = await complaint_repo.count_complaints(self._session, **filters)
        rows = await complaint_repo.list_complaints(
            self._session, **filters, page=page, page_size=page_size
        )
        return ComplaintListResponse(
            complaints=[to_response(c) for c in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )
