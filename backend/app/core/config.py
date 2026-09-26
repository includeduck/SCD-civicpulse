"""CivicPulse Backend — Application settings.

All configuration is loaded from environment variables (or .env in development).
Never hard-code secrets. Use .env.example as the template.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        # Repo-root .env when running from backend/, or a local one.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────
    app_name: str = "CivicPulse"
    app_version: str = "0.1.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    # JSON is required on stdout (plan §1.1); "console" is a local-only convenience.
    log_format: Literal["json", "console"] = "json"

    # ── API ────────────────────────────────────────────────────────
    api_prefix: str = "/api"
    # Read as a plain string: pydantic-settings JSON-decodes list fields from env,
    # which rejects the comma-separated form used in .env.example.
    allowed_origins_csv: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        validation_alias="ALLOWED_ORIGINS",
    )

    # ── Database ───────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://civicpulse:civicpulse@localhost:5432/civicpulse"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis ──────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_stats_ttl: int = 30           # seconds, per §1.3
    redis_ai_cache_ttl: int = 86400     # 24 hours, per §1.4

    # ── Rate Limiting ──────────────────────────────────────────────
    rate_limit_requests: int = 10       # requests per window
    rate_limit_window: int = 60         # seconds

    # ── Triage ────────────────────────────────────────────────────
    # Values follow plan §9 (factory). Provider *labels* stored in
    # complaints.triaged_by (e.g. "llm:groq") are a separate vocabulary.
    triage_provider: Literal["llm", "ollama", "rules", "simulated"] = "simulated"
    triage_timeout_seconds: int = 10
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    @property
    def allowed_origins(self) -> list[str]:
        """Comma-separated ALLOWED_ORIGINS as a list."""
        return [o.strip() for o in self.allowed_origins_csv.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache ensures environment is read once per process. Tests can
    override by calling get_settings.cache_clear() before patching env vars.
    """
    return Settings()
