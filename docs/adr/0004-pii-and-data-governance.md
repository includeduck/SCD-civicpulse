# ADR 0004 — PII and Data Governance

**Status:** Accepted  
**Date:** 2026-09-14  
**Deciders:** CivicPulse team

---

## Context

Complaint submissions may include `reporter_contact` (email/phone) and free-text that could contain personal information. The system must not leak PII through logs or external services carelessly.

## Decision

1. `reporter_contact` is nullable and stored in the database but **never logged**.
2. Complaint text is sent to the triage provider (LLM) but **API keys are never logged**.
3. The system applies a prompt-injection guardrail before sending text to LLMs.
4. Logs use structured JSON and explicitly exclude PII fields.
5. The seed dataset uses invented names and locations — no real person data.

## Consequences

- **Positive:** PII does not appear in log aggregators.
- **Positive:** Audit trail exists in the database, not in logs.
- **Negative:** Debugging complaint-specific issues requires direct DB access (acceptable for an operations team).
