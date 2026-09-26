"""Build the triage provider selected by TRIAGE_PROVIDER.

Called once in ``create_app`` so a bad configuration stops the service at
startup, never on a citizen's first request.
"""

from __future__ import annotations

from app.core.config import Settings
from app.providers.triage.base import TriageProvider
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
    if name in ("llm", "ollama"):
        raise TriageConfigurationError(
            f"TRIAGE_PROVIDER={name} is not implemented yet (Phase 5). "
            "Use 'simulated' or 'rules'."
        )
    raise TriageConfigurationError(
        f"Unknown TRIAGE_PROVIDER={name!r}; expected one of: llm, ollama, rules, simulated."
    )
