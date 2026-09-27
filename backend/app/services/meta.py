"""Triage provider introspection for GET /api/meta/providers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.complaint import TriagedBy
from app.providers.triage_cache import TriageCache
from app.repositories import complaint as complaint_repo
from app.schemas.meta import ProviderMeta, ProvidersResponse, TriageCacheStats, TriageOutcome

RECENT_OUTCOMES_LIMIT = 20  # assignment §2.2: "the last 20 triage outcomes"

# (TRIAGE_PROVIDER value, triaged_by label, fallback label, description)
_PROVIDERS: tuple[tuple[str, str, str | None, str], ...] = (
    (
        "simulated",
        TriagedBy.simulated,
        TriagedBy.rules_fallback,
        "Deterministic simulated provider for CI and testing",
    ),
    ("rules", TriagedBy.rules, None, "Heuristic keyword/rules-based triage engine"),
    (
        "llm",
        TriagedBy.llm_groq,
        TriagedBy.rules_fallback,
        "Hosted Groq Cloud LLM triage provider with retry and fallback",
    ),
    (
        "ollama",
        TriagedBy.llm_ollama,
        TriagedBy.rules_fallback,
        "Local Ollama LLM provider running in the Compose stack",
    ),
)


class MetaService:
    def __init__(self, session: AsyncSession, settings: Settings, cache: TriageCache) -> None:
        self._session = session
        self._settings = settings
        self._cache = cache

    async def providers(self) -> ProvidersResponse:
        recent = await complaint_repo.recent_triage_outcomes(
            self._session, limit=RECENT_OUTCOMES_LIMIT
        )
        stats = await self._cache.stats()
        return ProvidersResponse(
            active_provider=self._settings.triage_provider,
            providers=[
                ProviderMeta(
                    name=name,
                    triaged_by=label,
                    active=self._settings.triage_provider == name,
                    timeout_seconds=self._settings.triage_timeout_seconds,
                    fallback_provider=fallback,
                    description=description,
                )
                for name, label, fallback, description in _PROVIDERS
            ],
            recent_outcomes=[
                TriageOutcome(
                    complaint_id=c.id,
                    provider=c.triaged_by or "unknown",  # query excludes NULLs
                    latency_ms=c.triage_latency_ms,
                    fallback=c.triaged_by == TriagedBy.rules_fallback,
                    created_at=c.created_at,
                )
                for c in recent
            ],
            cache=TriageCacheStats(hits=stats.hits, misses=stats.misses, hit_rate=stats.hit_rate),
        )
