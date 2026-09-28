# ADR 0001 — Provider Interface

**Status:** Accepted  
**Date:** 2026-09-14 (updated 2026-09-27, Phase 4)  
**Deciders:** CivicPulse team

---

## Context

The system must support multiple AI triage backends (hosted LLM, Ollama, rule-based, simulated) and switch between them through an environment variable, without changing application code. CI must be deterministic and must not need network access. The assignment's point is that "the reader must be replaceable": the system around the model must not care which one is running, and must not fall over when it's slow, rate-limited or wrong.

## Decision

1. **One protocol.** `TriageProvider` in `backend/app/providers/triage/base.py`: a `name` plus `triage(text, location) -> TriageResult`, exactly as the assignment defines it. Services depend only on this module, never on a provider SDK.
2. **Synchronous interface, run off the event loop.** We kept the assignment's synchronous signature rather than making it `async`. `ComplaintService` calls providers through `run_in_threadpool`, so a slow HTTP call ties up a worker thread, not the event loop that serves every other request.
3. **Typed errors instead of SDK exceptions.** Providers raise `TriageTimeoutError`, `TriageRateLimitedError`, `TriageServerError` (retryable), or `TriageBadRequestError`, `TriageInvalidOutputError`, `TriageError` (not retryable). Retry and fallback decisions read `error.retryable`, never an HTTP status code.
4. **Untrusted output.** The service re-validates every result against `TriageResult`, whatever the provider claims to return. Invalid output is a provider failure (`TriageInvalidOutputError`), never a `400` to the citizen.
5. **Selected once, at startup.** `build_triage_provider(settings)` in `factory.py` runs in `create_app`. `TRIAGE_PROVIDER` is a closed set (`llm | ollama | rules | simulated`), and misconfiguration stops the service at startup.
6. **Deterministic CI provider.** `SimulatedTriage` is seeded and offline, with configurable failure injection covering every error class above, so fallback, retry and validation paths can be tested without a network or `sleep()`.

## Consequences

- **Positive:** Adding a provider is one class plus one factory branch; routes and services don't change.
- **Positive:** CI is deterministic (`TRIAGE_PROVIDER=simulated`), and every failure path is reproducible on demand.
- **Positive:** Retry and fallback (Phase 5) live in the service layer and are testable with fake providers.
- **Negative:** Blocking providers use threadpool workers, so very high concurrency with a slow LLM is bounded by the pool size. That's acceptable at this scale, and the 10 s timeout caps how long a worker can be held.
- **Negative:** `simulated` is a `triaged_by` label outside the assignment's list. It's confined to CI, tests and demos, and it's documented in `docs/TRIAGE.md`.
