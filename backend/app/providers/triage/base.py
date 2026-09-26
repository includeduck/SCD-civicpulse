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


@runtime_checkable
class TriageProvider(Protocol):
    """A replaceable complaint reader.

    ``name`` is the label stored in ``complaints.triaged_by``
    (e.g. ``"rules"``, ``"llm:groq"``).
    """

    name: str

    def triage(self, text: str, location: str) -> TriageResult: ...
