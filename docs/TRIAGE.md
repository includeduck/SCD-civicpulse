# Triage Design

> Design documentation for the AI triage subsystem.

---

## Provider Interface

All triage providers implement:

```python
class TriageProvider(Protocol):
    name: str

    def triage(self, text: str, location: str) -> TriageResult:
        ...
```

## Providers

| Name | `TRIAGE_PROVIDER` value | Description |
|------|------------------------|-------------|
| `LLMTriage` | `llm:groq` | Groq-hosted LLM |
| `OllamaTriage` | `llm:ollama` | Local Ollama model |
| `RuleBasedTriage` | `rules` | Keyword-based rules, no external calls |
| `SimulatedTriage` | `simulated` | Deterministic, used in CI |

## Fallback Chain

```
Primary provider → (on timeout/5xx/429 with one jittered retry) → RuleBasedTriage
```

Fallback sets `triaged_by = rules:fallback`.

## Caching

Triage results are cached in Redis by SHA-256 of `(text, location)` for 24 hours.

## Resilience Contract

If the primary provider always raises, `POST /api/complaints` still returns `201` with `triaged_by == "rules:fallback"`.

*Detailed implementation notes and test references to be added in Phases 4–5.*
