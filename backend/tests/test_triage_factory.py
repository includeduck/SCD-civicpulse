"""The factory picks the provider from TRIAGE_PROVIDER and fails fast on bad config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.triage.factory import TriageConfigurationError, build_triage_provider
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage.simulated import SimulatedTriage


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_selects_rules():
    assert isinstance(build_triage_provider(_settings(triage_provider="rules")), RuleBasedTriage)


def test_selects_simulated_with_its_settings():
    provider = build_triage_provider(
        _settings(
            triage_provider="simulated",
            simulated_seed="9",
            simulated_failure_mode="timeout",
            simulated_failure_rate="0.25",
        )
    )
    assert isinstance(provider, SimulatedTriage)
    assert (provider.seed, provider.failure_mode, provider.failure_rate) == (9, "timeout", 0.25)


@pytest.mark.parametrize("name", ["llm", "ollama"])
def test_unimplemented_providers_fail_clearly(name: str):
    with pytest.raises(TriageConfigurationError, match="Phase 5"):
        build_triage_provider(_settings(triage_provider=name))


def test_unknown_provider_rejected_by_settings(monkeypatch):
    monkeypatch.setenv("TRIAGE_PROVIDER", "gpt-5")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_misconfiguration_fails_at_startup_not_on_first_request(monkeypatch):
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("TRIAGE_PROVIDER", "ollama")
    get_settings.cache_clear()
    try:
        with pytest.raises(TriageConfigurationError):
            create_app()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_app_uses_the_configured_provider(app):
    """conftest sets TRIAGE_PROVIDER=simulated, as CI must (assignment §2.5)."""
    assert isinstance(app.state.triage_provider, SimulatedTriage)
