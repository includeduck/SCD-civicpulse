"""GET /api/meta/providers — active triage provider and recent triage outcomes."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import MetaServiceDep
from app.schemas.meta import ProvidersResponse

router = APIRouter(prefix="/meta", tags=["Metadata"])


@router.get("/providers", response_model=ProvidersResponse, summary="List AI Triage Providers")
async def get_providers(service: MetaServiceDep) -> ProvidersResponse:
    """Active provider, all known providers, and the last 20 triage outcomes
    (provider, latency, fallback y/n)."""
    return await service.providers()
