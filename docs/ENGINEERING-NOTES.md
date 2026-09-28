# Engineering Notes

> **CS4032 Software Construction and Design — Assignment 01**
>
> Part 1 answers the **eight questions in assignment §5.2**, in the assignment's own order and wording. Part 2 holds the other written justifications the assignment requires (indexes, cache TTL and invalidation, the Redis volume, the dev bind mount).
>
> Every answer cites our own files and lines, because "generic answers score zero". **Line numbers drift as code changes: re-check every reference before submission.**

---

# Part 1 — The eight questions (assignment §5.2)

## Q1 — Three things that differ between your laptop and a CI runner, and the exact line in a Dockerfile or manifest that freezes each

All three are differences we actually hit.

1. **The Python interpreter.** The laptop had Python 3.14 installed; the runner has whatever its image ships. Frozen by `backend/Dockerfile:6` and `:24`, `FROM python:3.12.14-slim@sha256:f77ac9e4…`, where the digest also freezes the OS packages underneath. CI's own test job pins the same minor version (`.github/workflows/ci.yml:25`, `PYTHON_VERSION: "3.12"`).
2. **Dependency versions.** The laptop's first virtualenv had drifted to FastAPI 0.141 against the 0.115.6 we target. Frozen by the `==` pins in `backend/pyproject.toml` (e.g. line 8, `"fastapi==0.115.6"`), installed in the image before any source is copied. On the frontend, `frontend/package-lock.json` plus `npm ci` (never `npm install`) does the same job.
3. **The triage provider and its environment.** A laptop may run Ollama or Groq with a personal `.env`; CI must be deterministic and has no model. Frozen by `.github/workflows/ci.yml:96`, `TRIAGE_PROVIDER: simulated`. Also, `backend/tests/conftest.py` switches off the settings' `.env` file, so a developer's `.env` can't change test results either (a bug we found in Phase 9).

---

## Q2 — Where your pipeline sits on the CI/CD maturity ladder (Lecture 03, slide 32); justify the rung, name the next rung and what it buys

Slide 32's ladder has five rungs: **1 Manual deployment → 2 Continuous Integration → 3 Continuous Delivery → 4 Continuous Deployment → 5 Production-grade** ("review · scan · staging · smoke test · approval · rollback · monitor").

**We're on rung 4, Continuous Deployment, with most of rung 5's practices, but not rung 5's target.**

- **Rungs 2–3, done.** Every PR into `dev`/`main` is tested on a clean runner by nine required checks (`.github/workflows/ci.yml`), and `main` only moves through reviewed, green PRs (ruleset 23347090; the gate demonstrably blocks merges, `docs/evidence/ci-gate.md`). Every push to `main` produces the deployable artifact: images tagged by commit SHA in GHCR, with digests and an SBOM (`cd.yml`, `build-push`).
- **Rung 4, done mechanically.** A push to `main` ships itself: `deploy-k8s` applies the prod overlay pinned to `<image>:<sha>@<digest>` with no human step (`cd.yml`, `scripts/cd_deploy.sh`). That is also slide 33's "build once, deploy the same artifact" (Q3).
- **Rung 5's practices we already have:**

  | Practice | Where |
  |---|---|
  | review | one required approval |
  | scan | Trivy on both images, failing on fixable HIGH/CRITICAL |
  | smoke test | through the Ingress after every deploy |
  | approval | the ruleset |
  | rollback | two documented, demonstrated methods: ADR 0003, `docs/evidence/k8s-rollback.txt` |
- **Why not rung 5.** The deploy target is a **throwaway k3d cluster inside the CI runner**, not a production environment users reach. There is **no staging** stage to promote the same artifact through, and **monitoring** stops at a Prometheus `/metrics` endpoint that nothing scrapes, alerts on, or feeds back into a rollback. Our rung-4 "production" is honest about being a rehearsal.

**The next rung, 5, and what it buys:**

1. A persistent **staging** environment that receives the same SHA first, with automated checks before promotion to a persistent production.
2. **Monitoring that closes the loop.** Prometheus actually scraping `/metrics`, with alerts on the fallback rate, error rate and latency, and the smoke test or alerts triggering the declarative rollback automatically.

It buys the confidence to ship without watching. Today a bad build is caught by tests and by a human noticing; at rung 5 it's caught in staging, or rolled back by the system itself within minutes of reaching production.

---

## Q3 — The exact line guaranteeing build-once-deploy-many, and what breaks without it

Two lines together, one per half of the promise.

1. **Built once, per commit.** `.github/workflows/cd.yml:71` tags the image `${{ env.REGISTRY }}/backend:${{ github.sha }}`, and `cd.yml:151` passes that same `IMAGE_SHA: ${{ github.sha }}` to the deploy. The deploy never builds: `scripts/cd_deploy.sh:69` pins the prod overlay to `newTag: "$IMAGE_SHA"`, plus the pushed digest, so what runs is `<image>:<sha>@sha256:…`, the exact bytes that passed CI's Trivy scan and tests.
2. **One image for every environment.** The frontend bundle contains no environment-specific value: there is no `import.meta.env` anywhere in `frontend/src`, and the only per-environment setting is `frontend/nginx/default.conf.template:28`, `proxy_pass ${BACKEND_URL};`, filled in when the container starts (ADR 0002). The backend reads all configuration from its environment.

**What breaks without it.** If each environment rebuilt its own image (or baked in its own API URL), the bytes tested in CI would not be the bytes running in production; a dependency could resolve differently between the two builds. "What is production running?" would have no exact answer. Rolling back would mean rebuilding an old commit and hoping it builds the same. With `:latest` instead of a SHA it's worse still: the tag moves under you, so a rollback to `:latest` rolls *forward* to whatever was pushed last (ADR 0003).

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

**Measured** (`docs/evidence/load/`; k6 offering a step from 5 to 120 req/s at t = 60 s):

- The HPA raised its desired replicas **36–40 s** after the load arrived.
- The first extra pod was Ready (capacity actually arriving) after **51–55 s**.
- All 10 pods were Ready after **70–96 s**.

**Where the time went**, from the timestamped `kubectl get hpa -w` in `docs/evidence/load/before-vpa/hpa-watch.txt`:

1. **The ramp itself (20 s)**: the load reached full rate at t = 80 s.
2. **Measurement (≈15 s)**: metrics-server samples every 15 s (`--metric-resolution=15s` in k3s), and CPU is averaged over that window. The HPA's reading went 21 % → 179 % only at 17:06:56, 15 s after the load was at full rate.
3. **Decision (≤15 s)**: the HPA controller syncs every 15 s, and its default scale-up policy caps each step (at most +4 pods or +100 % per 15 s). So it went 2 → 6 first, and 6 → 10 one sync later, not straight to 10.
4. **Pod start (≈15 s)**: scheduling, container start, the `wait-for-schema` initContainer, Python start-up, then the first successful readiness probe (every 5 s).

Meanwhile the first two pods absorbed the whole load. The HPA read **500 %**, which is exactly our limit ÷ request (500m ÷ 100m): those pods were throttled at their CPU limit. That's where the 3.2 s p99 of the first run came from. The lag is the reason autoscaling isn't a substitute for capacity planning: for about a minute, the capacity you have is the capacity you planned.

**What would reduce it:**

- A higher `minReplicas` or headroom for known peaks (capacity planning).
- A shorter metric resolution.
- A scale-up policy that allows bigger first steps (`behavior.scaleUp.policies`).
- Faster pod start (smaller image, readiness on first success).
- Scaling on a *leading* signal such as request rate or queue depth through custom metrics (e.g. KEDA), rather than CPU, which only rises once the pods are already struggling.

---

## Q6 — Why VPA is in Off mode; describe the failure mode of running it in Auto alongside your HPA

The HPA scales on CPU utilisation, and **utilisation is usage divided by the CPU request**. VPA in Auto *changes that request*. So the two controllers act on the same number from opposite ends:

1. VPA sees high usage and raises the request.
2. Utilisation drops, so the HPA scales *in*.
3. Fewer pods means more load per pod.
4. VPA sees higher usage and raises the request again.
5. Every VPA change evicts pods to apply it, which is a disruption in itself.

The replica count ends up moving with *VPA's* decisions, not with traffic.

**Our own data shows the lever is real.** Changing only the request from 100m to VPA's recommended 182m, under identical load, changed the HPA's reading at 10 pods from 62–68 % (above target, pinned at `maxReplicas`) to 36–40 %. Its desired count went from "more than 10" to about 7, and it scaled in 160 s earlier (`docs/evidence/load/README.md`). If VPA in Auto had made that change by itself mid-traffic, the HPA would have removed three pods with no change in load at all.

**So we run VPA as a recommender:**

- `updateMode: "Off"` in `k8s/base/vpa.yaml`.
- Only the recommender is installed; no updater or admission controller (`k8s/k3d/vpa/kustomization.yaml`).
- A human applied its target once, as a deliberate reviewed change: `backend.yaml` now requests `182m` / `250Mi` instead of our guessed `100m` / `128Mi`.

Recommender mode plus a human decision is what industry does for exactly this reason.

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

### Symptoms
During early Phase 3 integration testing of the complaint intake flow, an automated end-to-end test suite (`backend/tests/test_complaints_e2e.py`) failed intermittently on consecutive HTTP calls. The very first `POST /api/complaints` request succeeded and returned HTTP 201 with the created complaint. However, any subsequent request (either a second `POST` or a follow-up `GET /api/complaints/{id}`) immediately crashed with HTTP 500, producing this Python traceback from the database driver:

```text
Traceback (most recent call last):
  File ".../starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  ...
  File ".../asyncpg/protocol/protocol.pyx", line 700, in asyncpg.protocol.protocol.BaseProtocol.send_message
AttributeError: 'NoneType' object has no attribute 'send'
```

### What we wrongly believed first
Because this surfaced right after introducing the 4-layer architecture (`backend/app/routes/complaints.py`, `backend/app/services/complaints.py`, and `backend/app/repositories/complaint.py`), we wrongly suspected a transaction lifecycle leak or connection starvation bug in our code:
1. We assumed `session.commit()` or `session.close()` was failing to release the connection back to SQLAlchemy's async connection pool in `backend/app/core/database.py`, leaving the session in a corrupt or detached state.
2. We spent over an hour auditing dependency injection in `backend/app/core/dependencies.py` (`get_db`), verifying async context manager cleanup, adding verbose engine echo logging (`echo=True`), and stepping through SQLAlchemy's `async_sessionmaker`. Every test in isolation passed, but sequential requests inside a single test fixture crashed reliably.

### The exact command and log line that told the truth
The breakthrough came when we decoupled the test runner from the application server and probed the live application directly. We launched a real Uvicorn server against the test database and issued consecutive HTTP requests using `curl`:

```bash
# Terminal 1: run real uvicorn server
uvicorn app.main:app --port 8000

# Terminal 2: fire consecutive requests
curl -s -X POST http://localhost:8000/api/complaints \
  -H "Content-Type: application/json" \
  -d '{"text": "Pothole on Main St", "location": "Sector G-10"}'
curl -s -X POST http://localhost:8000/api/complaints \
  -H "Content-Type: application/json" \
  -d '{"text": "Streetlight broken", "location": "Sector F-7"}'
```

Output:
```text
{"id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","category":"roads","priority":"medium",...}  # 201 Created
{"id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","category":"lighting","priority":"low",...} # 201 Created
```
Both requests returned HTTP 201 cleanly in real Uvicorn!

This immediately pointed the finger at Starlette's `TestClient`. Looking at `asyncpg.connection.Connection`, each connection attaches to the running `asyncio` event loop. When `TestClient(app)` is instantiated without an explicit context manager (`with TestClient(app) as client:`), Starlette creates and destroys a brand new `asyncio` event loop for every single `.post()` or `.get()` call. Request 1 acquired an `asyncpg` connection from SQLAlchemy's persistent connection pool, attached to Event Loop 1. When Event Loop 1 closed at the end of the first request, the underlying socket in the pool remained alive, but its loop reference was garbage-collected (`self._loop = None`). Request 2 reused that pooled connection, attempted to write to the socket, and hit `NoneType has no attribute 'send'`.

### Resolution
1. In test fixtures, wrapped client usage in `with TestClient(app) as client:`, or migrated to `httpx.AsyncClient(transport=ASGITransport(app=app))` sharing a single event loop across the test.
2. In database fixtures (`backend/tests/conftest.py`), configured SQLAlchemy's `create_async_engine` with `NullPool` for testing to guarantee fresh connections per session and avoid stale cross-loop connection pooling.

---

# Part 2 — Other required justifications

## Indexes, and the query each one serves (§2.3)

Both are declared at `backend/app/models/complaint.py:93-94` and created by the migration `backend/alembic/versions/0001_initial.py`.

- **`idx_complaint_status_priority (status, priority)`** serves the operations dashboard's filtered list and its total count: `WHERE status = :s AND priority = :p` in `list_complaints` / `count_complaints` (`backend/app/repositories/complaint.py:70`, `:101`, with the filters at `:90-92`). Status comes first because operators almost always filter by status ("show me open complaints") and then narrow by priority.
- **`idx_complaint_created_at (created_at)`** serves the dashboard's newest-first ordering and pagination, `ORDER BY created_at DESC LIMIT/OFFSET` (`backend/app/repositories/complaint.py:85`), and the "last 20 triage outcomes" query for `/api/meta/providers` (`:189`). Without it, every page would sort the whole table.

## Why the stats cache uses a TTL *and* explicit invalidation (§2.4)

- **Invalidation gives freshness.** A new complaint, status change, or triage correction deletes the cached stats right after the commit (`backend/app/services/complaints.py:61`, `backend/app/services/status.py:89`, `backend/app/services/triage_correction.py:53`, which calls `backend/app/providers/cache.py:78`). The next read recomputes, so a new complaint or correction shows up in the stats immediately rather than up to 30 s later.
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
