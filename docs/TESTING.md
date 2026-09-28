# Test Strategy

> How CivicPulse is tested, why the suite is deterministic although part of the system is an LLM, and which test proves which requirement.

**At a glance (2026-09-27):**

| Suite | Tests | Coverage | Enforced floor |
|---|---|---|---|
| Backend (pytest) | 250, plus 8 PostgreSQL tests | 98 % of `app/` | 90 % (`[tool.coverage.report] fail_under`); the brief's minimum is 65 % |
| Frontend (Vitest) | 22 component and unit tests | 96 % of lines | lines/statements 85 %, functions 80 %, branches 70 % (`vite.config.ts`) |

Both suites run in a **random order** on every run (pytest-randomly; Vitest `sequence.shuffle`). Before this was switched on, the backend passed 28 random orders in a row and the frontend 5.

---

## Running the tests

```bash
# Backend: unit, service and API integration tests (no database or Redis needed)
cd backend
pytest                        # prints the random seed; coverage report included
pytest -p randomly --randomly-seed=<seed>   # replay a specific order

# Backend: the PostgreSQL-only tests, against a disposable database
docker run -d --rm --name civicpulse-pg-test -e POSTGRES_USER=civicpulse \
  -e POSTGRES_PASSWORD=civicpulse -e POSTGRES_DB=civicpulse_test -p 55432:5432 postgres:16.15-alpine
TEST_DATABASE_URL=postgresql+asyncpg://civicpulse:civicpulse@localhost:55432/civicpulse_test pytest tests/test_postgres.py

# Frontend
cd frontend
npm test                      # or: npm run test:coverage

# Submission lint (brief §5.8: catches mechanical failures across files, Docker, K8s, Git)
cd ..
python scripts/check_submission.py
```

Tests never read your `.env`: `tests/conftest.py` switches the settings' env file off, so the quickstart's `cp .env.example .env` can't change results.

---

## Layers

| Layer | What it runs against | Files |
|---|---|---|
| **Unit** | Pure functions and classes, no I/O | `test_triage_rules`, `test_triage_simulated`, `test_triage_injection` (detection), `test_schemas`, `test_triage_cache` (key), `test_config` |
| **Service** | `TriageService` with fake providers, fakeredis and an injected sleep/jitter | `test_triage_resilience`, `test_triage_injection` (service), `test_observability` (thread budget) |
| **Provider (HTTP)** | Groq and Ollama clients against scripted responses (`httpx.MockTransport`) | `test_triage_llm` |
| **API integration** | The real FastAPI app via `TestClient`, SQLite in memory and fakeredis | `test_complaints_api`, `test_status_machine`, `test_stats_and_meta`, `test_redis_cache_and_ratelimit`, `test_health`, `test_middleware`, `test_exceptions`, `test_observability` |
| **Database integration** | Real PostgreSQL 16 and the real Alembic migration | `test_postgres`: indexes, CHECK constraints, server-generated UUID and UTC timestamps, compare-and-set update, seed idempotency |
| **Contract** | The committed `frontend/openapi.json` against the live app | `test_openapi_contract`; plus `tsc` against the generated types |
| **Frontend components** | React views with `fetch` mocked, driven through the UI | `frontend/tests/*.test.tsx` |
| **Whole system** | The Compose stack, by hand for now | Phase 9 and injection-fix PRs; CI integration job in Phase 13 |

SQLite stands in for PostgreSQL in the fast tests because it needs no server. The places where the two differ (CHECK constraints, `gen_random_uuid()`, `timestamptz`, row-level compare-and-set) are exactly what `test_postgres.py` covers against the real database.

---

## Determinism: how a suite with an LLM in it stays green on every run

The brief: *"Resolve it by design, not by luck."* Each source of nondeterminism is removed where it enters:

| Source | How it's removed |
|---|---|
| The model's answers | Tests never call a model. `conftest.py` pins `TRIAGE_PROVIDER=simulated`, which is seeded and offline. Provider behaviour is tested with fakes that raise, hang or return malformed output on demand |
| The network | Groq and Ollama are tested against `httpx.MockTransport`; `test_never_touches_the_network` fails if the simulated provider opens a socket |
| Redis and PostgreSQL | fakeredis and per-test in-memory SQLite, created fresh for each test; real Postgres only in `test_postgres.py`, with its own disposable database |
| Time | Retry waits and jitter are injected into `TriageService`; the simulated provider's latency uses an injected `sleep`. **No test calls `time.sleep()`.** The only real waits are the 50 ms deadlines in the two timeout tests, where the deadline itself is what's under test and the provider blocks on an event until the test releases it, so the outcome can't depend on scheduling luck |
| Randomness | The simulated provider decides failures from a hash of the seed and the input: the same complaint always fails or always succeeds |
| Test order | Random on every run, with the seed printed, so hidden coupling shows up as a reproducible failure. One real case was found and fixed in Phase 8: the OpenAPI contract test saw throwaway routes other tests had added to the shared app |
| The developer's machine | Tests ignore `.env`; pinned dependencies; Python 3.12 in both the image and CI |

---

## Traceability: requirement → test

Backend test names are in `backend/tests/`; frontend ones in `frontend/tests/`.

### API contract (brief §2.2)

| Requirement | Tests |
|---|---|
| `POST` validates, triages, persists: 201 | `test_complaints_api::test_create_complaint_triages_and_persists` |
| 400 with field-level errors | `test_invalid_input_returns_400_with_field_errors`, `test_missing_fields_return_400`, `test_invalid_list_parameters_return_400`, `test_exceptions::test_request_validation_returns_400_with_field_errors` |
| 404 | `test_get_missing_complaint_returns_404`, `test_status_machine::test_unknown_complaint_is_404` |
| Filters, pagination (`page_size` ≤ 100), total | `test_list_filters`, `test_list_status_filter`, `test_pagination_is_complete_and_stable`, `test_page_size_100_is_allowed` |
| 409 naming the transition | `test_status_machine::test_every_invalid_transition_is_409_naming_it` |
| 429 with `Retry-After` | `test_redis_cache_and_ratelimit::test_limit_then_429_with_retry_after` |
| `reporter_contact` never exposed | `test_response_never_contains_reporter_contact`, `test_schemas::test_complaint_response_never_exposes_reporter_contact` |

### State machine

| Requirement | Tests |
|---|---|
| Every allowed transition | `test_status_machine::test_every_valid_transition` (parametrised over the whole table) |
| Every invalid transition → 409 | `test_every_invalid_transition_is_409_naming_it` (parametrised) |
| Terminal states, races | `test_terminal_states_offer_no_transitions`, `test_concurrent_transition_loses_with_409`, `test_postgres::test_compare_and_set_status_update` |

### AI layer (brief §2.5)

| Requirement | Tests |
|---|---|
| ≥ 3 providers selected by environment | `test_triage_factory` (all 8) |
| Structured output validated; malformed output rejected | `test_triage_llm::test_malformed_model_output_is_rejected`, `test_missing_choices_is_invalid_output`, `test_triage_resilience::test_6b_output_that_fails_the_schema_is_rejected` |
| 10 s hard timeout | `test_triage_resilience::test_hard_timeout_caps_a_hung_provider`, `test_observability::test_saturated_triage_pool_degrades_to_fallback_not_a_hang` |
| Retry once with jitter, only on timeout/429/5xx | `test_retryable_error_retries_once_with_jitter_then_succeeds`, `test_4_server_error_twice_retries_once_then_falls_back`, `test_non_retryable_errors_fall_back_without_retry` |
| **"A provider that always raises: POST still returns 201 and `rules:fallback`"** | `test_triage_resilience::test_7_provider_that_always_raises_still_returns_201` |
| One WARNING per fallback with id, provider, error class | `test_7b_fallback_logs_exactly_one_warning_with_id_provider_and_error` |
| Cache by content hash, 24 h; fallbacks never cached | `test_8_duplicate_complaint_is_a_cache_hit`, `test_8a_fallback_results_are_never_cached`, `test_triage_cache::test_round_trip_with_24h_ttl_and_counters` |
| API key never logged | `test_triage_llm::test_9_api_key_absent_from_logs_errors_and_reprs` |
| **Prompt injection: the category is still decided by the schema** | `test_triage_llm::test_10_injection_that_hijacks_the_model_cannot_escape_the_schema`, plus `test_triage_injection` (detected before the model; 11 genuine complaints not flagged) |
| PII not sent to the provider | `test_contact_details_are_redacted_before_sending`, `test_reporter_contact_is_never_sent_to_the_provider` |
| Deterministic simulated provider for CI | `test_triage_simulated` (all 12) |

### Cache and rate limiter (brief §2.4)

| Requirement | Tests |
|---|---|
| Stats MISS → HIT, 30 s TTL | `test_stats_miss_then_hit_then_miss_after_write`, `test_stats_entry_has_30s_ttl` |
| Invalidated on write | `test_status_change_invalidates_stats`, `test_stats_and_meta::test_rejected_transition_does_not_invalidate` |
| Distributed limiter shared by replicas | `test_two_replicas_share_one_limit`, `test_clients_have_separate_budgets` |
| Real client IP behind the proxy; spoofing ignored | `test_clients_behind_a_trusted_proxy_get_separate_buckets`, `test_spoofed_forwarded_for_from_untrusted_peer_is_ignored` |
| Redis outage degrades, doesn't fail | `test_whole_request_path_survives_redis_outage`, `test_triage_cache::test_triage_still_works_when_redis_is_down` |

### Data layer (brief §2.3)

| Requirement | Tests |
|---|---|
| Migrations create the indexes | `test_postgres::test_migration_creates_required_indexes` |
| Length rules enforced in the database too | `test_postgres::test_length_checks_are_enforced_by_the_database` |
| UUID and UTC timestamps from the server | `test_postgres::test_database_generates_uuid_and_utc_timestamps` |
| Idempotent seed | `test_postgres::test_seed_is_idempotent`, `test_repository::test_seed_idempotency` |

### Operations and observability

| Requirement | Tests |
|---|---|
| `/health` never touches the database; `/ready` names the failed dependency | `test_health` (all 5) |
| `request_id` propagated and on every log line | `test_middleware::test_request_id_preserved_when_provided`, `test_unhandled_error_keeps_request_id`, `test_observability::test_every_request_logs_one_json_line_with_request_id` |
| JSON logs only, including uvicorn's | `test_uvicorn_lifecycle_logs_are_json`, `test_uvicorn_access_log_is_disabled` |
| Metrics: bounded labels, 500s counted | `test_request_metrics_use_route_templates_not_ids`, `test_unmatched_paths_share_one_label`, `test_server_errors_are_counted_as_500` |
| Shutdown closes the DB pool, Redis and the provider | `test_shutdown_closes_db_pool_redis_and_provider` |

### Frontend (brief §2.1; rubric B)

| Requirement | Tests |
|---|---|
| Validation that mirrors the server | `SubmitPage.test::blocks input that breaks the server's limits…`, `validation.test` (exact boundaries, trimming) |
| Honest loading state | `SubmitPage.test::shows an honest loading state and locks the form…` |
| Renders category, priority, summary, provider | `SubmitPage.test::renders the category, priority, AI summary and provider…`, `…says so when the rules answered…` |
| Server errors shown verbatim (400, 429) | `SubmitPage.test::shows the server's field errors from a 400…`, `…explains a 429…` |
| Status actions come from the server; 409 verbatim | `DashboardPage.test::offers exactly the transitions the server allows…`, `…shows the server's 409 message verbatim…` |
| Pagination and filters | `DashboardPage.test::sends filters to the server and goes back to page 1…` |
| `X-Cache` shown | `StatsPage.test::shows whether Redis served the numbers…` |
| Error boundary | `app.test::replaces a crashed view with a recovery screen` |
| Typed client matches OpenAPI | `app.test::takes validation limits and enum values from the backend's OpenAPI schema`; `backend/tests/test_openapi_contract.py`; `tsc` |

---

## What is *not* covered by automated tests, and why

| Behaviour | Why not automated | How it was verified instead |
|---|---|---|
| A live LLM's answers | Nondeterministic by nature; putting a model in CI would make the pipeline flaky, which the brief warns against | The first live run is recorded in TRIAGE.md ("Measured"): latency, accuracy, cache and the injection finding, later re-verified after the fix |
| SIGTERM drains in-flight requests | Needs a real process and signal | Run by hand against the real image; RUNBOOK.md "Graceful shutdown" (201 during drain, exit 0) |
| Network segmentation | Needs the Compose networks | `docs/evidence/network-isolation.txt`, with positive controls; the CI integration job (Phase 13) can re-run it |
| The whole stack together | Belongs in CI with Docker | Verified by hand in Phase 9; the Phase 13 integration job will `compose up`, POST, GET, and check `X-Cache` MISS → HIT |
| Visual layout and dark mode | Component tests check behaviour, not pixels | Checked by eye in the browser; not a rubric item |
