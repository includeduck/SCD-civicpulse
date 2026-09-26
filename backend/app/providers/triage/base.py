"""Triage provider contract (assignment §2.5).

Every provider — rules, simulated, hosted LLM, Ollama — returns a validated
``TriageResult``. The service layer depends only on this module, never on a
provider SDK.

The interface is synchronous, exactly as the assignment defines it. The
service runs providers in a worker thread (``run_in_threadpool``), so a slow
network call cannot block the event loop.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models.complaint import Category, Priority


class TriageResult(BaseModel):
    """Validated output of any triage provider."""

    category: Category
    priority: Priority
    summary: str = Field(max_length=140)
    confidence: float = Field(ge=0.0, le=1.0)


# ── Provider errors ──────────────────────────────────────────────────────────
# Providers translate SDK/HTTP failures into these, so the service can decide
# retry and fallback without knowing any provider's internals (assignment §2.5:
# retry once on timeout, 429 and 5xx only; never retry a 400).


class TriageError(Exception):
    """Any triage failure. Not retryable unless a subclass says otherwise."""

    retryable: bool = False


class TriageTimeoutError(TriageError):
    retryable = True


class TriageRateLimitedError(TriageError):
    """Provider returned 429."""

    retryable = True


class TriageServerError(TriageError):
    """Provider returned 5xx."""

    retryable = True


class TriageBadRequestError(TriageError):
    """Provider returned 400: the request was wrong and will be wrong again."""


class TriageUnavailableError(TriageError):
    """Provider could not be reached at all (DNS, connection refused)."""


class TriageInvalidOutputError(TriageError):
    """Provider answered, but the answer failed TriageResult validation."""


@runtime_checkable
class TriageProvider(Protocol):
    """A replaceable complaint reader.

    ``name`` is the label stored in ``complaints.triaged_by``
    (e.g. ``"rules"``, ``"llm:groq"``).
    """

    name: str

    def triage(self, text: str, location: str) -> TriageResult: ...
