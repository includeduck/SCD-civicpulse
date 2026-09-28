"""Tests for environment-driven settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _load_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            monkeypatch.setenv(key, value)


def test_env_example_loads(monkeypatch: pytest.MonkeyPatch):
    """`cp .env.example .env` must produce a valid configuration."""
    _load_env_example(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == ["http://localhost:5173"]
    assert settings.triage_provider == "ollama"
    assert settings.ollama_model == "llama3.2:1b"
    assert settings.log_format == "json"


def test_env_example_names_match_settings(monkeypatch: pytest.MonkeyPatch):
    """Backend variables in .env.example must map to real settings, not be silently ignored."""
    _load_env_example(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_WINDOW", "17")
    monkeypatch.setenv("REDIS_STATS_TTL", "11")
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings(_env_file=None)
    assert settings.rate_limit_window == 17
    assert settings.redis_stats_ttl == 11
    assert settings.environment == "production"


def test_unknown_triage_provider_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRIAGE_PROVIDER", "llm:groq")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
