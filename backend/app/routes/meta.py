"""Metadata and system introspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/meta", tags=["Metadata"])


class ProviderMeta(BaseModel):
    name: str
    active: bool
    timeout_seconds: int
    fallback_provider: str | None = None
    description: str


class ProvidersResponse(BaseModel):
    active_provider: str
    providers: list[ProviderMeta]


@router.get("/providers", response_model=ProvidersResponse, summary="List AI Triage Providers")
async def get_providers() -> ProvidersResponse:
    """Return available and currently active AI triage providers.

    Surfaces provider status, timeout configuration, and fallback mechanisms.
    """
    settings = get_settings()

    all_providers = [
        ProviderMeta(
            name="simulated",
            active=(settings.triage_provider == "simulated"),
            timeout_seconds=settings.triage_timeout_seconds,
            fallback_provider="rules",
            description="Deterministic simulated provider for CI and testing",
        ),
        ProviderMeta(
            name="rules",
            active=(settings.triage_provider == "rules"),
            timeout_seconds=settings.triage_timeout_seconds,
            fallback_provider=None,
            description="Heuristic keyword/rules-based triage engine",
        ),
        ProviderMeta(
            name="llm:groq",
            active=(settings.triage_provider == "llm:groq"),
            timeout_seconds=settings.triage_timeout_seconds,
            fallback_provider="rules:fallback",
            description="Hosted Groq Cloud LLM triage provider with retry and fallback",
        ),
        ProviderMeta(
            name="llm:ollama",
            active=(settings.triage_provider == "llm:ollama"),
            timeout_seconds=settings.triage_timeout_seconds,
            fallback_provider="rules:fallback",
            description="Local Ollama LLM provider running on municipal edge host",
        ),
    ]

    return ProvidersResponse(
        active_provider=settings.triage_provider,
        providers=all_providers,
    )
