# ADR 0004 — PII and Data Governance

**Status:** Accepted  
**Date:** 2026-09-14 (updated 2026-09-27, Phase 5)  
**Deciders:** CivicPulse team

---

## Context

Citizens submit free text, a location and an optional contact (`reporter_contact`). Real complaints contain names, house numbers and phone numbers, often typed straight into the text ("pipe burst, call me on 0300-…"). With `TRIAGE_PROVIDER=llm`, that text is sent to a third-party hosted model. The assignment (§2.5) asks us to decide explicitly: redact before sending, send only the complaint body, or accept and document the exposure. The API is also unauthenticated, so anything it returns is public.

## What leaves the machine, and to whom

| Data | Stored in Postgres | Sent to the LLM | Returned by the API | Logged |
|------|:---:|:---:|:---:|:---:|
| Complaint text | yes | **yes, with phone numbers and emails redacted** | yes | no |
| Location | yes | yes, redacted the same way | yes | no |
| `reporter_contact` | yes | **never** | **never** | **never** |
| Complaint id, category, priority, provider, latency | yes | no | yes | yes |
| LLM API key | no | as an `Authorization` header only | never | **never** |

- **`TRIAGE_PROVIDER=llm`:** the redacted text and location go to Groq's OpenAI-compatible API (`GROQ_BASE_URL`), and nothing else does.
- **`TRIAGE_PROVIDER=ollama`:** nothing leaves the Compose network; the model runs in our own container.
- **`simulated` / `rules`:** no external calls at all.

## Decision

1. **Send only what triage needs.** The provider receives the complaint text and location as a JSON data object (`app/providers/triage/prompt.py`). `reporter_contact` is never passed to the triage layer: `ComplaintService.create` calls triage with `payload.text` and `payload.location` only.
2. **Redact contact details in the text.** `redact_pii()` masks email addresses and phone-like digit runs (10+ digits, e.g. `0300-1234567`, `+92 300 1234567`) as `[email]` and `[phone]` before the text is sent. Category and urgency don't depend on a phone number, so classification quality is unaffected. Names and street addresses are **not** redacted: the location is needed for the summary, and name detection would be unreliable. That exposure is accepted, as explained below.
3. **Never return `reporter_contact`.** `ComplaintResponse` omits it, because the endpoints are public.
4. **Never log PII or secrets.** Logs carry ids, categories, providers, latencies and error classes, never complaint text or contact details. `GROQ_API_KEY` is a `SecretStr`, error messages include only status codes, and a test (`tests/test_triage_llm.py::test_9_…`) asserts the key never appears in logs, errors or reprs.
5. **The AI cache stores results, not raw text.** Redis keys are SHA-256 hashes of the normalised text, and values hold only the triage result.

## Why the remaining exposure is acceptable

A complaint describes a public-infrastructure problem at a place, such as a burst main on Street 12. After redaction, what reaches the provider is roughly what a citizen would post on a public noticeboard. Operators still get the full, unredacted text from our own database. Anyone for whom even this is too much can run `TRIAGE_PROVIDER=ollama`, and no complaint data leaves the machine.

> **TODO (team, before submission):** check the hosted provider's current data-retention and training-use terms on its live policy page, and cite what you saw here, with the date. Don't rely on memory or on this document: the assignment requires citing the terms as observed.

## Consequences

- **Positive:** the most sensitive field (`reporter_contact`) and the most common incidental PII (phone numbers and emails in the text) never reach a third party.
- **Positive:** switching to Ollama removes third-party exposure entirely, with no code changes.
- **Negative:** names and addresses inside the free text can still reach the hosted provider.
- **Negative:** regex redaction can miss unusual formats, or occasionally mask a long non-phone number. Triage quality isn't affected, and the stored text is never altered.
- **Operational:** investigating a specific complaint means querying the database, not reading logs. That's intentional.
