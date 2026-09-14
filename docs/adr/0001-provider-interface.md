# ADR 0001 — Provider Interface

**Status:** Accepted  
**Date:** 2026-09-14  
**Deciders:** CivicPulse team

---

## Context

The system must support multiple AI triage backends (Groq LLM, Ollama, rule-based, simulated) and switch between them via an environment variable without changing application code. The triage subsystem must be testable in CI without network access.

## Decision

We define a `TriageProvider` Protocol in `backend/app/providers/triage/base.py`. All providers implement this protocol. A factory function reads `TRIAGE_PROVIDER` and returns the correct implementation.

## Consequences

- **Positive:** Providers are interchangeable. CI always uses `SimulatedTriage` (deterministic, no network).
- **Positive:** Adding a new provider requires no changes to routes or services.
- **Positive:** Fallback logic is isolated in the service layer.
- **Negative:** Protocol-based dispatch adds a small indirection cost (negligible).
