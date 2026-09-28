"""Complaint endpoints — HTTP only: parse, validate, delegate, serialise.

No SQL, sessions or business rules here; see app/services/.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.core.dependencies import ComplaintServiceDep, StatusServiceDep, TriageCorrectionServiceDep
from app.models.complaint import Category, Priority, Status
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintListResponse,
    ComplaintResponse,
    StatusUpdateRequest,
    TriageCorrectionRequest,
)
from app.schemas.errors import INVALID_TRANSITION, NOT_FOUND, RATE_LIMITED, VALIDATION_ERROR

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ComplaintResponse,
    responses={**VALIDATION_ERROR, **RATE_LIMITED},
    summary="Submit a complaint (validated, rate-limited, triaged, persisted)",
)
async def create_complaint(
    payload: ComplaintCreate, request: Request, service: ComplaintServiceDep
) -> ComplaintResponse:
    client_ip = request.client.host if request.client else "unknown"
    return await service.create(payload, client_ip)


@router.get(
    "",
    response_model=ComplaintListResponse,
    responses=VALIDATION_ERROR,
    summary="List complaints with filters and pagination",
)
async def list_complaints(
    service: ComplaintServiceDep,
    category: Category | None = None,
    priority: Priority | None = None,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ComplaintListResponse:
    return await service.list_complaints(
        category=category,
        priority=priority,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    responses={**VALIDATION_ERROR, **NOT_FOUND},
    summary="Get one complaint",
)
async def get_complaint(complaint_id: uuid.UUID, service: ComplaintServiceDep) -> ComplaintResponse:
    return await service.get(complaint_id)


@router.patch(
    "/{complaint_id}/status",
    response_model=ComplaintResponse,
    responses={**VALIDATION_ERROR, **NOT_FOUND, **INVALID_TRANSITION},
    summary="Move a complaint through the status state machine",
)
async def change_status(
    complaint_id: uuid.UUID, body: StatusUpdateRequest, service: StatusServiceDep
) -> ComplaintResponse:
    return await service.change_status(complaint_id, body.status)


@router.patch(
    "/{complaint_id}/triage",
    response_model=ComplaintResponse,
    responses={**VALIDATION_ERROR, **NOT_FOUND},
    summary="Correct a complaint's priority and/or category",
)
async def correct_triage(
    complaint_id: uuid.UUID,
    body: TriageCorrectionRequest,
    service: TriageCorrectionServiceDep,
) -> ComplaintResponse:
    return await service.correct_triage(
        complaint_id,
        category=body.category,
        priority=body.priority,
    )
