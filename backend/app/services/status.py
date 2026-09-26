"""Complaint status state machine (assignment §2.2, "Domain rules").

The transition table below is the single source of truth. Routes never
inspect statuses, and the frontend receives ``allowed_transitions`` instead of
keeping its own copy.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.complaint import Complaint, Status
from app.providers.cache import StatsCache
from app.repositories import complaint as complaint_repo
from app.schemas.complaint import ComplaintResponse

logger = get_logger(__name__)

ALLOWED_TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.open: frozenset({Status.in_progress, Status.rejected}),
    Status.in_progress: frozenset({Status.resolved, Status.rejected}),
    Status.resolved: frozenset(),
    Status.rejected: frozenset(),
}

# Stable display order for allowed_transitions in API responses.
_STATUS_ORDER: list[Status] = list(Status)


def allowed_transitions(current: Status | str) -> list[Status]:
    """Statuses reachable from ``current``, in a stable order."""
    reachable = ALLOWED_TRANSITIONS[Status(current)]
    return [s for s in _STATUS_ORDER if s in reachable]


def is_allowed(current: Status | str, target: Status | str) -> bool:
    return Status(target) in ALLOWED_TRANSITIONS[Status(current)]


def transition_error(current: Status | str, target: Status | str) -> ConflictError:
    """The 409 body names the attempted transition; the frontend shows it verbatim."""
    return ConflictError(
        f"Cannot transition complaint from '{Status(current)}' to '{Status(target)}'."
    )


def to_response(complaint: Complaint) -> ComplaintResponse:
    """Serialise a complaint together with its state-machine options."""
    fields = {
        name: getattr(complaint, name)
        for name in ComplaintResponse.model_fields
        if name != "allowed_transitions"
    }
    return ComplaintResponse(**fields, allowed_transitions=allowed_transitions(complaint.status))


class StatusService:
    def __init__(self, session: AsyncSession, stats_cache: StatsCache) -> None:
        self._session = session
        self._stats_cache = stats_cache

    async def change_status(self, complaint_id: uuid.UUID, target: Status) -> ComplaintResponse:
        complaint = await complaint_repo.get_complaint(self._session, complaint_id)
        if complaint is None:
            raise NotFoundError(f"Complaint {complaint_id} not found.")

        current = Status(complaint.status)
        if not is_allowed(current, target):
            raise transition_error(current, target)

        updated = await complaint_repo.update_status(
            self._session, complaint_id, target, expected_status=current
        )
        if updated is None:
            # Another request changed or removed the row between our read and write.
            latest = await complaint_repo.get_complaint(self._session, complaint_id)
            if latest is None:
                raise NotFoundError(f"Complaint {complaint_id} not found.")
            raise transition_error(latest.status, target)

        response = to_response(updated)
        # Commit before responding, then invalidate: a stats read that races the
        # invalidation can only re-cache committed data.
        await self._session.commit()
        await self._stats_cache.invalidate()

        logger.info(
            "complaint_status_changed",
            complaint_id=str(complaint_id),
            from_status=str(current),
            to_status=str(target),
        )
        return response
