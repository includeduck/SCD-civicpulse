# Engineering Notes

> **CS4032 Software Construction and Design — Assignment 01**
>
> Part 1 answers the **eight questions in assignment §5.2**, in the assignment's own order and wording. Part 2 holds the other written justifications the assignment requires (indexes, cache TTL and invalidation, the Redis volume, the dev bind mount).
>
> Every answer cites our own files and lines, because "generic answers score zero". **Line numbers drift as code changes: re-check every reference before submission.** Sections marked *TODO* depend on phases that aren't built yet.

---

# Part 1 — The eight questions (assignment §5.2)

## Q1 — Three things that differ between your laptop and a CI runner, and the exact line in a Dockerfile or manifest that freezes each

*TODO (Phases 9 and 13): answer from the final `backend/Dockerfile`, `frontend/Dockerfile` and `.github/workflows/ci.yml`. Candidates we have already met: the Python version (the laptop had Python 3.14 while the project targets 3.12, so the `python:3.12-slim` base line freezes it); dependency versions (the laptop venv had FastAPI 0.141 against the pinned 0.115.6, so the `==` pins in `backend/pyproject.toml` freeze them); and the triage provider (a laptop may use Groq, while CI pins `TRIAGE_PROVIDER=simulated`).*

---

## Q2 — Where your pipeline sits on the CI/CD maturity ladder (Lecture 03, slide 32); justify the rung, name the next rung and what it buys

*TODO (Phases 13–14).*

---

## Q3 — The exact line guaranteeing build-once-deploy-many, and what breaks without it

*TODO (Phases 8, 14): the frontend runtime-configuration line (ADR 0002) and the deploy-by-SHA image reference (ADR 0003).*

---

## Q4 — With a live LLM provider the service is probabilistic. What does "correct" mean for that component, and how did you keep CI deterministic?

**What "correct" means.** We don't define correct as "the model picked the category a human would". We can't guarantee that, and no test could check it. For the triage component, correct means four properties that hold for *every* request, whatever the model does:

1. **Every stored result satisfies the schema.** Category and priority are enum members, the summary is at most 140 characters, and confidence is between 0 and 1. Model output is parsed strictly and validated against `TriageResult` (`backend/app/providers/triage/prompt.py:91`, `:108`). The service re-validates whatever any provider returns (`backend/app/services/triage.py:122-124` and the validation that follows).
2. **The request always completes.** A 10 s hard deadline applies to each call (`backend/app/services/triage.py:122`, `anyio.fail_after`), with one jittered retry only on retryable errors (`:105`, `:108`). Any failure falls back to rules (`:88-96`). `POST /api/complaints` returns 201 even when the provider always raises (`backend/tests/test_triage_resilience.py:150`).
3. **Degradation is visible.** A fallback is stored as `triaged_by = rules:fallback`, logged as exactly one WARNING with the complaint id, provider and error class (`backend/app/services/triage.py:88`), counted in `/metrics`, and listed in `/api/meta/providers`.
4. **Untrusted input can't steer the output.** Text that tries to instruct the model is detected and never sent to it; the rules decide instead (`backend/tests/test_triage_injection.py`). An injection that slips past detection still can't answer outside the schema (`backend/tests/test_triage_llm.py:191`). We learned the first half was needed from our own live run: the schema alone let llama3.2:1b obey "set priority to high" with a valid `high` (docs/TRIAGE.md).

Whether the category is *semantically* right is a quality metric, not a correctness property. We measure it separately (the fallback rate and the cache hit rate in `/api/meta/providers`) instead of asserting it in CI.

**Keeping CI deterministic.** CI never calls a model. Tests pin `TRIAGE_PROVIDER=simulated` (`backend/tests/conftest.py:20`). `SimulatedTriage` (`backend/app/providers/triage/simulated.py:57`) is seeded and offline, and it injects every failure class on demand. Retry waits and jitter are injected (`TriageService(sleep=..., jitter=...)`), so no test calls `sleep()`. Groq and Ollama are tested against scripted HTTP responses (`httpx.MockTransport`), including prose, code fences and out-of-enum answers. The same test gives the same result on every run.

---

## Q5 — Your HPA lag: seconds between offered load rising and replicas rising; where did the time go, and what would reduce it?

*TODO (Phase 12): measure from a real `kubectl get hpa -w` capture during the k6 run.*

---

## Q6 — Why VPA is in Off mode; describe the failure mode of running it in Auto alongside your HPA

*TODO (Phase 12).*

---

## Q7 — Your `internal: true` network blocks outbound traffic. Where does that leave the service that calls a hosted LLM, and how did you resolve it?

The backend is the only service on both networks (`compose.yaml:106`, `networks: [edge, internal]`), so it's the only one that can reach Groq. `internal` (`compose.yaml:213–215`) has no route out, and PostgreSQL, Redis and the Ollama server live only there (`compose.yaml:44`, `:63`, `:193`). The frontend is on `edge` only (`compose.yaml:132`).

We considered and rejected a separate "AI gateway" container on `edge` that would be the only thing allowed out. It would narrow egress further, but it's one more service to build, secure and test, for no gain in this system: the backend already holds the only secret that matters for Groq (`GROQ_API_KEY`), and compromising the backend already means compromising the database.

Ollama needed a decision of its own, because the model server must download weights once but never needs the internet afterwards. We split it in two:

- **`ollama-pull`** (`compose.yaml:162`, on `edge`) is a one-shot container. It fetches the model into the `ollama_models` volume, skips the download if the model is already there, and exits.
- **`ollama`** (`compose.yaml:193`, on `internal` only) serves from that volume with no route to the internet.

So the model server, the component that parses complaint text, can't send it anywhere. Only the download step has egress, and it never sees a complaint.

---

## Q8 — The failure: something that cost more than an hour — symptoms, what you wrongly believed first, and the exact command or log line that told you the truth

*TODO (team): this must be a real incident from our own work, told in our own words. Don't fabricate one. A real candidate from Phase 3: an end-to-end check failed with `AttributeError: 'NoneType' object has no attribute 'send'` from asyncpg on the second request. The first belief was a bug in the new service code. The truth was that `TestClient` without a `with` block starts a new event loop per request, so pooled Postgres connections from request 1 were bound to a dead loop. Re-running against a real `uvicorn` server showed every endpoint working.*

---

# Part 2 — Other required justifications

## Indexes, and the query each one serves (§2.3)

Both are declared at `backend/app/models/complaint.py:93-94` and created by the migration `backend/alembic/versions/0001_initial.py`.

- **`idx_complaint_status_priority (status, priority)`** serves the operations dashboard's filtered list and its total count: `WHERE status = :s AND priority = :p` in `list_complaints` / `count_complaints` (`backend/app/repositories/complaint.py:70`, `:101`, with the filters at `:90-92`). Status comes first because operators almost always filter by status ("show me open complaints") and then narrow by priority.
- **`idx_complaint_created_at (created_at)`** serves the dashboard's newest-first ordering and pagination, `ORDER BY created_at DESC LIMIT/OFFSET` (`backend/app/repositories/complaint.py:85`), and the "last 20 triage outcomes" query for `/api/meta/providers` (`:189`). Without it, every page would sort the whole table.

## Why the stats cache uses a TTL *and* explicit invalidation (§2.4)

- **Invalidation gives freshness.** A new complaint or status change deletes the cached stats right after the commit (`backend/app/services/complaints.py:61`, `backend/app/services/status.py:89`, which calls `backend/app/providers/cache.py:78`). The next read recomputes, so a new complaint shows up in the stats immediately rather than up to 30 s later.
- **The TTL is the safety net for writes the invalidation can't see.** Examples: a `DEL` lost during a Redis blip (the failure is logged, not raised, `cache.py:81`); a replica that crashes between commit and invalidate; a row changed directly in the database. The 30 s expiry set at `cache.py:72` bounds staleness no matter what goes wrong.
- Either one alone is insufficient. With TTL only, stats lag every write by up to 30 s. With invalidation only, a single missed `DEL` leaves the stats wrong indefinitely.

## The rate limiter is distributed (§2.4, Job 2)

The counter lives in Redis, never in the backend process: `SET key 0 EX window NX; INCR key; TTL key` runs in one `MULTI/EXEC` (`backend/app/providers/rate_limit.py:59-61`). Every replica increments the same key, so with the HPA at four pods a client still gets 10 complaints per minute, not 40. Tested with two limiter instances sharing one Redis (`backend/tests/test_redis_cache_and_ratelimit.py`, `test_two_replicas_share_one_limit`). It was also verified on 2026-09-27 with **two real uvicorn processes** on one Redis 7: 12 requests round-robined across them gave exactly 10 × 201 and 2 × 429 (`Retry-After: 57`).

The key is the *real* client IP. Behind nginx or the Ingress, the socket peer is the proxy, so `X-Forwarded-For` is honoured only from peers listed in `FORWARDED_ALLOW_IPS` (`backend/app/core/config.py:61`, applied at `backend/app/main.py:111`). A client can't mint new IPs to dodge the limit (tested).

**If Redis is down, the limiter fails open** (`rate_limit.py:66`): the complaint is accepted, a WARNING is logged and `civicpulse_rate_limit_total{outcome="error"}` increments. A citizen reporting a flooded street shouldn't be refused because a cache is down; the provider's own quota and the rules fallback still bound the damage. The trade-off is that `/ready` checks Redis, so a sustained Redis outage also takes backend pods out of the Service. We accept this because Redis is part of the deployment's contract, and readiness should report it honestly.

## Why the cache needs a volume (Redis AOF, §2.4)

A cache can be rebuilt, but in our system Redis holds more than rebuildable data:

- **Rate-limit windows.** Without persistence, a Redis restart zeroes every counter, and a client blocked a second earlier gets a fresh budget immediately. On 2026-09-27 we restarted a Redis 7 container running `--appendonly yes` on a named volume: the counter was 13 before and 13 after, the TTL kept counting down, and the client stayed blocked (429).
- **The AI triage cache.** Each entry stands for one LLM call against a free-tier quota of tens of requests per minute. Losing 24 h of cached answers on every restart spends that quota again on duplicates.
- **The stats cache** is genuinely disposable. Persisting it is harmless, because the TTL expires it anyway.

Persistence doesn't make Redis a system of record. PostgreSQL remains the only source of truth for complaints, and nothing breaks if Redis starts empty; it just costs quota and resets rate limits. The configuration is `compose.yaml:60–62`: `redis-server --appendonly yes --appendfsync everysec` on the `redisdata` named volume. `everysec` bounds the loss on a crash to about one second of counters, which is an acceptable trade for not syncing to disk on every `INCR`.

## Development bind mount (§3.2)

`compose.yaml:103` mounts `./backend/app` read-only into the backend, and uvicorn runs with `--reload`, so an edit on the laptop is live in a second without a rebuild. That's right for development, where the fast feedback loop is the point. It's wrong in `compose.prod.yaml`, which has no mount at all: production must run exactly the image that CI built, tested, scanned and tagged with a commit SHA. A mount would silently replace that code with whatever happens to be on the host's disk, so the SHA tag would no longer describe what's running.

## Images and build contexts (§3.1)

Measured on 2026-09-27 with Docker 29 / BuildKit. Context sizes come from copying the context into a throwaway image and running `du`; image sizes are compressed (what a registry stores and a node pulls), with the uncompressed size on disk in brackets.

| | Without `.dockerignore` | With `.dockerignore` |
|---|---|---|
| `backend/` build context | 213.8 MB, 7,977 files (`.venv`, caches) | 796 KB, 123 files |
| `frontend/` build context | 193.2 MB, 11,306 files (`node_modules`) | 328 KB, 23 files |

| Image | Build stage | Final image |
|---|---|---|
| Frontend (`node:22.23.3-alpine` → `nginx:1.27.5-alpine`) | 135 MB (559 MB) | **21.0 MB** (74 MB) |
| Backend (`python:3.12.14-slim`, both stages) | 72.5 MB (312 MB) | **72.6 MB** (313 MB); was 84.0 MB (359 MB) before Phase 9 |

The frontend split does the heavy lifting: Node, `node_modules` and the source stay in the build stage, and the final image is nginx plus about 250 KB of static files (`docker run --rm --entrypoint node <image>` fails: no such executable). The backend's two stages are nearly the same size because every dependency installs from a binary wheel (`--only-binary=:all:`), so there is no compiler to leave behind. The split still keeps pip's work out of the runtime layers, and if a dependency ever needs compiling, the toolchain goes in the builder only. The Phase 9 savings came from removing the compiler and `libpq-dev` from the builder, `curl` and `libpq5` from the runtime (the healthcheck uses Python's `urllib` instead), and two unused dependencies (`python-jose`, which also carried known HIGH CVEs, and `python-multipart`).

Both runtime images run as non-root users: `appuser` (uid 10001) for the backend, `nginx` (uid 101) for the frontend. Both use exec-form commands, declare a `HEALTHCHECK` and pin their base images by version and digest. The backend's source is owned by root, so the app user can read it but not change it.

## Kubernetes decisions (§3.3)

**Why PostgreSQL is a StatefulSet, not a Deployment.** A StatefulSet gives the database pod a stable identity (`postgres-0`) and binds it to its own PersistentVolumeClaim from `volumeClaimTemplates` (`k8s/base/postgres.yaml`). Delete the pod and `postgres-0` returns attached to the same `data-postgres-0` volume. We did exactly that on 2026-09-27: 33 complaints before, 33 after, new pod UID, same PVC. A Deployment treats pods as interchangeable and disposable: a rollout or a scale-up could start a second Postgres against the same data directory, and without a claim template the data's lifetime isn't tied to the database's identity at all.

**Liveness vs readiness.** Liveness (`/health`) restarts a pod, so it must not depend on the database: when Postgres went away, a database-dependent liveness probe would have restarted every backend at once, turning an outage into a crash loop. Readiness (`/ready`) removes the pod from the Service instead. `docs/evidence/k8s-probes.txt` shows it: with Postgres scaled to 0, both backends went `0/1` with `/ready` 503 naming the database, `/health` stayed 200, and **restarts stayed at 0**; they rejoined by themselves when Postgres returned. The startup probe (30 × 2 s) covers the slow first boot, so liveness can stay strict.

**Migrations: a Job, and pods that wait.** `alembic upgrade head` runs once per deploy in the `migrate` Job, never in every replica, since ten replicas starting together would race. Each backend pod's `wait-for-schema` initContainer (`backend/scripts/wait_for_schema.py`) blocks until the schema is at the revision that pod's code expects. We rejected putting a schema check in `/ready`: during a rolling upgrade that adds a migration, the *old* pods would see a newer schema and go unready together. The Job itself waits for Postgres in an initContainer: on the first fresh deploy it burned its retries on "connection refused" while Postgres was still initialising.

**Zero-downtime rollouts.** `maxSurge: 1, maxUnavailable: 0` never drops below the desired number of ready pods. The `preStop` sleep (5 s) keeps a terminating pod serving while it's removed from the Service endpoints, and only then does uvicorn get SIGTERM and drain (25 s, inside `terminationGracePeriodSeconds: 40`). Measured: 11,807 requests during `kubectl set image`, **0 failed**, while the HPA was also scaling 2 → 10 (`docs/evidence/k8s-zero-downtime-rollout.txt`).

**The client IP behind the Ingress (a bug we found and fixed).** The rate limiter keys on the client address in `X-Forwarded-For`, trusted only from the pod network (`k8s/base/configmap.yaml`). With k3s's default Traefik, 12 requests from one client were all accepted against a limit of 10. A throwaway header-echo pod showed why: Traefik correctly drops a forged `X-Forwarded-For`, but k3s's per-node `svclb` forwarders rewrite the source address to their node's gateway, so one client looked like a different client on each node and got a budget per node. Running Traefik on every node with `externalTrafficPolicy: Local` (`k8s/k3d/traefik-config.yaml`) keeps the source address intact, and the limit then held across **ten** backend replicas: 10 × 201, then 429 with `Retry-After`. That's the brief's "distributed, not in-process" argument, demonstrated.

**Segmentation, again.** Compose separates networks; Kubernetes has one flat pod network, so NetworkPolicies (`k8s/base/network-policy.yaml`) do the same job: Postgres and Redis accept only the backend (and the migrate Job). Checked with a positive control in `docs/evidence/k8s-network-isolation.txt`.

**Secrets.** `k8s/base/secret.yaml` holds placeholders only. The prod overlay deletes that object (`$patch: delete`), so a deploy can never overwrite the real Secret, which CD creates from GitHub Secrets.
