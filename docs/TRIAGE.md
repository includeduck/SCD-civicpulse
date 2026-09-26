# Triage Design

> How CivicPulse turns free-text complaints into a category, a priority and a one-line summary, and how it stays correct when the provider doing that is slow, rate-limited or wrong.

---

## Provider interface

Defined in [`backend/app/providers/triage/base.py`](../backend/app/providers/triage/base.py), exactly as the assignment specifies:

```python
class TriageResult(BaseModel):
    category: Category
    priority: Priority
    summary: str = Field(max_length=140)
    confidence: float = Field(ge=0.0, le=1.0)

class TriageProvider(Protocol):
    name: str
    def triage(self, text: str, location: str) -> TriageResult: ...
```

`name` is the label stored in `complaints.triaged_by`. The interface is synchronous. `ComplaintService` calls it through `run_in_threadpool`, times it into `triage_latency_ms`, and re-validates the result against `TriageResult`. A provider that returns invalid output raises `TriageInvalidOutputError`; that's a server-side failure, never a `400` for the citizen.

## Providers

| Provider | `TRIAGE_PROVIDER` | `triaged_by` | Status |
|----------|-------------------|--------------|--------|
| `SimulatedTriage` | `simulated` (default, used in CI) | `simulated` | ✅ Phase 4 |
| `RuleBasedTriage` | `rules` | `rules` | ✅ Phase 3 |
| `LLMTriage` (Groq) | `llm` | `llm:groq` | Phase 5 |
| `OllamaTriage` | `ollama` | `llm:ollama` | Phase 5 |

The configuration name and the stored label are separate vocabularies. `simulated` isn't in the assignment's `triaged_by` list; it only appears in CI, tests and demos, and the seed data never uses it.

### Selection

[`factory.py`](../backend/app/providers/triage/factory.py) builds the provider once, in `create_app`. A bad value stops the service at startup, not on the first complaint:

- An unknown value is rejected when settings load (`TRIAGE_PROVIDER` is a closed set).
- `llm` / `ollama` raise `TriageConfigurationError` until Phase 5 implements them.

## RuleBasedTriage

Deterministic keyword matching; the full rule set is documented at the top of [`rules.py`](../backend/app/providers/triage/rules.py).

- **Category:** count whole-word/phrase hits per category (English plus romanised Urdu, e.g. `paani`, `bijli`, `kachra`, `sarak`, `khamba`). Highest count wins; ties go to streetlights > electricity > water > sanitation > roads; no hits → `other`.
- **Priority:** any urgency term (`flooding`, `fire`/`aag`, `danger`/`khatra`, `sparking`, `accident`, `children at risk`, `gas leak`…) → `high`; otherwise a low-urgency term (`minor`, `suggestion`…) → `low`; otherwise `normal`.
- **Summary:** the first sentence, whitespace-collapsed, at most 140 characters.
- **Confidence:** 0.3 with no hits, otherwise 0.5 + 0.1 per hit, capped at 0.9.

## SimulatedTriage

Deterministic fake for CI ([`simulated.py`](../backend/app/providers/triage/simulated.py)): seeded, no network, with failure injection.

- **Outcome:** category and priority come from the rule engine, so tests and the Compose integration job can assert a real category. Confidence comes from a seeded SHA-256 of the input. Summaries start with `[simulated] `.
- **Failure injection:** controlled by settings. Whether an input fails is decided by the same seeded hash, so a given complaint always fails or always succeeds: no randomness, no sleeps.

| Setting | Default | Meaning |
|---------|---------|---------|
| `SIMULATED_SEED` | `42` | Seed for confidence and failure decisions |
| `SIMULATED_FAILURE_MODE` | `none` | `timeout`, `rate_limited`, `server_error`, `bad_request`, `error`, or `invalid` (returns output that fails validation) |
| `SIMULATED_FAILURE_RATE` | `1.0` | Fraction of inputs that fail when a mode is set |

## Provider errors

Providers translate SDK/HTTP failures into typed errors, so retry and fallback logic never inspects provider internals:

| Error | Like | Retryable |
|-------|------|-----------|
| `TriageTimeoutError` | timeout | yes |
| `TriageRateLimitedError` | HTTP 429 | yes |
| `TriageServerError` | HTTP 5xx | yes |
| `TriageBadRequestError` | HTTP 400 | **no**: the request was wrong and will be wrong again |
| `TriageInvalidOutputError` | prose, code fences, out-of-enum values | no |
| `TriageError` | anything else | no |

## Running each mode

```bash
TRIAGE_PROVIDER=simulated uvicorn app.main:app --reload    # default
TRIAGE_PROVIDER=rules uvicorn app.main:app --reload
TRIAGE_PROVIDER=simulated SIMULATED_FAILURE_MODE=timeout uvicorn app.main:app --reload   # demo a failing provider
```

## Coming in Phase 5

- **Timeout:** a 10 s hard cap on every LLM call.
- **Retry:** exactly one retry, with jitter, on retryable errors only.
- **Fallback:** to `RuleBasedTriage`, recording `triaged_by = rules:fallback` and logging one WARNING with the complaint id, provider and error class.
- **AI cache:** Redis, keyed by SHA-256 of `(text, normalised location)`, 24 h TTL. Only real provider results are cached, never fallback results. The hit rate is measured.
- **Prompt-injection guardrail and test.**

**Resilience contract:** if the provider always raises, `POST /api/complaints` still returns `201` with `triaged_by == "rules:fallback"`. Until Phase 5 lands, a provider failure returns `500` and stores nothing (tested in `tests/test_triage_simulated.py`).
