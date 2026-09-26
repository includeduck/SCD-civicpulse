"""Build the triage provider selected by TRIAGE_PROVIDER.

Called once in ``create_app`` so a bad configuration stops the service at
startup, never on a citizen's first request.
"""

from __future__ import annotations

from app.core.config import Settings
from app.providers.triage.base import TriageProvider
from app.providers.triage.llm import LLMTriage
from app.providers.triage.ollama import OllamaTriage
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage.simulated import SimulatedTriage


class TriageConfigurationError(RuntimeError):
    """TRIAGE_PROVIDER names a provider that cannot be built."""


def build_triage_provider(settings: Settings) -> TriageProvider:
    name = settings.triage_provider
    if name == "rules":
        return RuleBasedTriage()
    if name == "simulated":
        return SimulatedTriage(
            seed=settings.simulated_seed,
            failure_mode=settings.simulated_failure_mode,
            failure_rate=settings.simulated_failure_rate,
        )
    if name == "llm":
        api_key = settings.groq_api_key.get_secret_value()
        if not api_key:
            raise TriageConfigurationError(
                "TRIAGE_PROVIDER=llm requires GROQ_API_KEY (from the environment or a Secret)."
            )
        return LLMTriage(
            api_key=api_key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.triage_timeout_seconds,
        )
    if name == "ollama":
        return OllamaTriage(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.triage_timeout_seconds,
        )
    raise TriageConfigurationError(
        f"Unknown TRIAGE_PROVIDER={name!r}; expected one of: llm, ollama, rules, simulated."
    )
