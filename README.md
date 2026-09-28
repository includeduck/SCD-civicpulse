# CivicPulse

> **CS4032 Software Construction and Design — Assignment 01**

[![CI](https://github.com/includeduck/SCD-civicpulse/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/includeduck/SCD-civicpulse/actions/workflows/ci.yml)
[![CD](https://github.com/includeduck/SCD-civicpulse/actions/workflows/cd.yml/badge.svg?branch=main)](https://github.com/includeduck/SCD-civicpulse/actions/workflows/cd.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Problem Statement

Municipal residents have no simple, accessible channel to report infrastructure issues (potholes, power outages, broken streetlights, sanitation problems). CivicPulse provides a public complaint-intake portal with AI-powered triage that categorises and prioritises complaints, routes them to the right departments, and gives operations staff a real-time dashboard.

---

## Architecture

```mermaid
graph TD
    Browser -->|HTTP| FE[Frontend\nReact 18 + Nginx]
    FE -->|/api/*| BE[Backend\nFastAPI]
    BE -->|SQL| PG[(PostgreSQL 16)]
    BE -->|cache / rate-limit| RD[(Redis 7)]
    BE -->|triage| AI[AI Provider\nGroq / Ollama / Rules]
```

---

## Quick Start (local)

Needs Docker with Compose v2 (Docker Desktop on Windows or macOS). Nothing else.

```bash
git clone https://github.com/includeduck/SCD-civicpulse.git
cd SCD-civicpulse
cp .env.example .env          # then change POSTGRES_PASSWORD
docker compose up --build
```

| What | Where |
|------|-------|
| App (report, dashboard, stats) | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Metrics | http://localhost:8000/metrics |

A one-shot `migrate` service applies the migrations and loads 32 sample complaints before the backend starts, so the dashboard has data straight away. The first run also downloads the Ollama model (about 1.3 GB) into a volume. Complaints sent before it's ready are triaged by the keyword rules, and after that by the model. For a light stack without the model, set `COMPOSE_PROFILES=` and `TRIAGE_PROVIDER=rules` in `.env`.

| Service | Networks | Published port | Volume |
|---------|----------|----------------|--------|
| `frontend` (nginx) | `edge` | 8080 | |
| `backend` (FastAPI) | `edge`, `internal` | 8000 (dev only) | `./backend/app` bind mount (dev only) |
| `postgres` (alias `database`) | `internal` | none | `pgdata` |
| `redis` (AOF on) | `internal` | none | `redisdata` |
| `ollama` | `internal` | none | `ollama_models` |
| `migrate`, `ollama-pull` (one-shot) | `internal`, `edge` | none | |

`internal` has no route to the internet, and the frontend has no route to the database: see [docs/evidence/network-isolation.txt](docs/evidence/network-isolation.txt). Production runs `compose.prod.yaml`: images tagged by commit SHA, no `build:`, no bind mount, and only the frontend's port published:

```bash
IMAGE_TAG=<commit-sha> docker compose -f compose.prod.yaml up -d
```

### Submission Lint (brief §5.8)

Catch mechanical requirements, secret leaks, probe configurations, and attribution floors before submitting:

```bash
python scripts/check_submission.py
```

---

## Backend Development

**Inside Compose (recommended).** `docker compose up` mounts `backend/app` into the backend with hot reload, so an edit on your machine is live about a second later. Logs: `docker compose logs -f backend`.

**Outside Docker** (Python 3.12, matching the image). The unit tests need no database or Redis: they use in-memory SQLite and fakeredis. To run the server itself, `DATABASE_URL` and `REDIS_URL` are required, with no built-in defaults, so no credentials live in source. They're read from the environment or the repository-root `.env`, where `.env.example` points them at `localhost`. Compose's PostgreSQL and Redis are deliberately not published to the host, so start your own for this (as in the `docker run` example below).

```bash
cd backend
pip install -e ".[dev]"

# Apply database migrations (uses DATABASE_URL from .env)
alembic upgrade head

# Seed ~32 sample complaints (idempotent — safe to re-run)
python -m scripts.seed_db

# Run the API with hot reload
uvicorn app.main:app --reload

# Lint, type-check and test (coverage report included)
ruff check .
mypy app
pytest
```

PostgreSQL-specific tests (migrations, CHECK constraints, seed idempotency) are skipped unless `TEST_DATABASE_URL` points at a disposable database:

```bash
docker run -d --rm --name civicpulse-pg-test -e POSTGRES_USER=civicpulse -e POSTGRES_PASSWORD=civicpulse -e POSTGRES_DB=civicpulse_test -p 55432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql+asyncpg://civicpulse:civicpulse@localhost:55432/civicpulse_test pytest tests/test_postgres.py
```

The backend follows a 4-layer architecture: **routes → services → repositories → models**, with AI triage behind a provider interface in `app/providers/triage/`.

---

## Frontend Development

React 18 + Vite + TypeScript (Node 22). Three views: **Report** (`/`), **Dashboard** (`/dashboard`) and **Stats** (`/stats`).

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to the backend on :8000
npm run lint       # ESLint
npm run typecheck  # tsc --noEmit
npm test           # Vitest component tests
npm run build      # production bundle in dist/
```

The app only calls relative `/api/...` paths. In production nginx proxies them to `BACKEND_URL`, read when the container starts, so one image runs in every environment ([ADR 0002](docs/adr/0002-frontend-runtime-config.md)). In development Vite's dev server does the proxying (`DEV_BACKEND_URL` overrides the default `http://localhost:8000`).

```bash
docker build -t civicpulse-frontend ./frontend
docker run -p 8080:8080 -e BACKEND_URL=http://<backend-host>:8000 civicpulse-frontend
```

**Typed API client.** Request and response types are generated from the backend's OpenAPI schema, never written by hand. When the API changes:

```bash
cd backend && python -m scripts.export_openapi   # writes frontend/openapi.json
cd ../frontend && npm run gen:api                # regenerates src/api/schema.d.ts
```

`backend/tests/test_openapi_contract.py` fails if `frontend/openapi.json` is stale, and `tsc` then fails wherever the frontend no longer matches the contract.

**No business rules in the UI.** Status buttons are the complaint's `allowed_transitions` from the server, and input limits and enum values are read from the OpenAPI schema. To see the server's `409` in the dashboard, open it in two tabs, change a complaint's status in one, then try a now-stale action in the other: the server's message is shown word for word.

---

## Project Status

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repository and team workflow | ✅ Done |
| 1 | Backend foundation (FastAPI, config, logging, health probes) | ✅ Done |
| 2 | Database models, Alembic migrations, repositories, seed | ✅ Done |
| 3 | Complaint domain and API, rule-based triage | ✅ Done |
| 4 | Simulated triage provider and provider factory | ✅ Done |
| 5 | LLM/Ollama providers, timeout, retry, fallback, AI cache, injection guardrail | ✅ Done |
| 6 | Redis stats cache and distributed rate limiter | ✅ Done |
| 7 | Observability (JSON logs, request metrics) and graceful shutdown | ✅ Done |
| 8 | Frontend (React + Vite + TypeScript), typed API client, nginx `/api` proxy | ✅ Done |
| 9 | Docker Compose, networks, volumes, image hardening | ✅ Done |
| 10 | Automated test strategy: coverage floors, random order, traceability ([TESTING.md](docs/TESTING.md)) | ✅ Done |
| 11 | Kubernetes: Kustomize base and overlays, k3d, probes, zero-downtime rollouts | ✅ Done |
| 12 | HPA under load, VPA recommender loop, k6 load test ([results](docs/evidence/load/README.md)) | ✅ Done |
| 13 | CI: lint and types, tests with PostgreSQL, image build, Trivy, kubeconform, Compose integration | ✅ Done |
| 14 | CD: GHCR by SHA and digest, SBOM, deploy to an ephemeral cluster, rollback, releases | ✅ Done (first live run on the next merge to `main`) |
| 15 | Documentation, submission checker, video | ⏳ Next |

See [CivicPulse_ImplementationPlan.md](CivicPulse_ImplementationPlan.md) for the full plan.

---

## Continuous Integration

`.github/workflows/ci.yml` runs on every pull request to `main` or `dev` and on every push to `dev`. It builds, but it never publishes anything.

| Job | What it proves |
|-----|----------------|
| `lint-and-type` | ruff (lint and format), mypy, eslint, `tsc --noEmit`, and the OpenAPI contract: `frontend/openapi.json` and the generated TypeScript types match the backend |
| `test-backend` | pytest with a real PostgreSQL 16 service (so the migration and constraint tests run too), `TRIAGE_PROVIDER=simulated`, random order, fails under 90 % coverage |
| `test-frontend` | Vitest, shuffled, with coverage thresholds |
| `build (backend / frontend)` | Both images build; not pushed |
| `scan (backend / frontend)` | Trivy fails on any HIGH/CRITICAL with a fix available (`.trivyignore` for reasoned exceptions) |
| `manifests` | `kustomize build` of both overlays through kubeconform, strict |
| `integration` | `scripts/ci_integration.sh`: Compose up, `/ready`, POST a complaint and GET it back, `X-Cache` MISS → HIT, the frontend can't reach the database, `down -v` |

Every action is pinned to a commit SHA, and Trivy and kubeconform run from images pinned by digest. The workflow has read-only permissions.

---

## Continuous Delivery

`.github/workflows/cd.yml` runs on every push to `main`: **test → build-push → deploy-k8s**, each stage gated on the one before by `needs:`.

| Job | What it does |
|-----|--------------|
| `test` | The whole CI workflow again, on the merged code |
| `build-push` | Pushes both images to GHCR as `:<commit sha>` (and `:latest`, never deployed), with `GITHUB_TOKEN` only; an SPDX SBOM per image (Syft); the digests as job outputs |
| `deploy-k8s` | A throwaway k3d cluster; the prod overlay pinned to `<image>:<sha>@<digest>`; migrations; `rollout status`; a smoke test through the Ingress (`/`, `/api/stats`, POST then GET a complaint); `kubectl get hpa` |

`release.yml` publishes semantic-version tags and a GitHub Release when a `v*` tag is pushed. Rollback, both ways, is in the [runbook](docs/RUNBOOK.md#rollback) and [ADR 0003](docs/adr/0003-deploy-by-sha.md).

---

## API Reference

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/complaints` | Submit a new complaint (rate-limited, AI-triaged) | ✅ |
| `GET` | `/api/complaints` | List complaints (filterable, paginated) | ✅ |
| `GET` | `/api/complaints/{id}` | Get a single complaint | ✅ |
| `PATCH` | `/api/complaints/{id}/status` | Transition complaint status | ✅ |
| `GET` | `/api/stats` | Aggregate stats, Redis read-through cache (30 s TTL, invalidated on write), `X-Cache: HIT\|MISS` | ✅ |
| `GET` | `/api/meta/providers` | Active triage provider, last 20 triage outcomes, AI-cache hit rate | ✅ |
| `GET` | `/health` | Liveness probe (no DB) | ✅ |
| `GET` | `/ready` | Readiness probe (checks PG + Redis) | ✅ |
| `GET` | `/metrics` | Prometheus metrics | ✅ |

Invalid input returns `400` with field-level errors. Invalid status transitions return `409` naming the transition, e.g. `Cannot transition complaint from 'resolved' to 'open'.` Every complaint response includes `allowed_transitions`, so clients never hardcode the state machine. `POST /api/complaints` is rate-limited per client IP (10 per 60 s by default, shared across replicas via Redis) and returns `429` with `Retry-After` when exceeded.

---

## Kubernetes (local)

Needs Docker, [k3d](https://k3d.io) v5 and `kubectl`. One command creates a three-node cluster, builds and imports both images, runs the migrations and deploys everything:

```bash
bash scripts/k8s-up.sh                 # about 4 minutes from nothing
# open http://civicpulse.localhost:8081
kubectl -n civicpulse get pods
k3d cluster delete civicpulse          # remove it all
```

Manifests use Kustomize: `k8s/base/` plus `k8s/overlays/dev` (local images, simulated triage, sample data) and `k8s/overlays/prod` (GHCR images pinned to a commit SHA, Groq, no committed Secret).

| Object | What and why |
|--------|--------------|
| `Namespace` | Everything in `civicpulse`; Pod Security `baseline` enforced, `restricted` warned (all our pods meet `restricted`) |
| `StatefulSet` postgres | `volumeClaimTemplates` → its own PVC; deleting `postgres-0` loses nothing |
| `Deployment` + `PVC` redis | AOF on the volume; `Recreate` strategy because the volume is ReadWriteOnce |
| `Deployment` backend ×2, frontend ×2 | Rolling updates with `maxSurge: 1`, `maxUnavailable: 0`, a preStop sleep and a grace period; spread across nodes |
| `Job` migrate | Migrations once per deploy; backend pods wait for the schema in an initContainer |
| `Service` ×4 | All `ClusterIP`; nothing exposed on a node port |
| `Ingress` | One host: `/api/` → backend, `/` → frontend |
| `ConfigMap` / `Secret` | Configuration vs credentials; the committed Secret holds placeholders only |
| `NetworkPolicy` | Postgres and Redis accept only the backend (and the migrate Job) |
| `PodDisruptionBudget` | `minAvailable: 1` on the backend |
| `HorizontalPodAutoscaler` | Backend, 2–10 replicas at 60 % CPU; scale up at once, scale down after 5 min |
| `VerticalPodAutoscaler` | Backend, `updateMode: "Off"`: recommends requests, never changes them |

**Autoscaling under load.** `bash load/run-load-test.sh <name>` runs a k6 step load (5 → 120 req/s) and captures `kubectl get hpa -w`, the lag and a replicas-vs-load chart. Measured: the HPA reacts in about 40 s and new capacity is Ready in about 55 s. The backend's requests (`182m` / `250Mi`) come from the VPA's recommendation, not from a guess: see [the before and after comparison](docs/evidence/load/README.md).

Evidence captured on the running cluster: [network isolation](docs/evidence/k8s-network-isolation.txt), [liveness vs readiness with the database down](docs/evidence/k8s-probes.txt), and a [zero-downtime rollout under load](docs/evidence/k8s-zero-downtime-rollout.txt) (11,807 requests, 0 failed).

---

## Screenshots

> *Screenshots will be added as part of Phase 15 documentation.*

---

## Team

| Member | GitHub |
|--------|--------|
| Muhammad Wasay Tariq | [@includeduck](https://github.com/includeduck) |
| Talha Sami | [@tlhaasami](https://github.com/tlhaasami) |

---

## Docs

- [Engineering Notes](docs/ENGINEERING-NOTES.md)
- [Runbook](docs/RUNBOOK.md)
- [AI Usage](docs/AI-USAGE.md)
- [Triage Design](docs/TRIAGE.md)
- [Test Strategy](docs/TESTING.md)
- [Security Audit](docs/SECURITY-AUDIT.md)
- [ADR 0001 — Provider Interface](docs/adr/0001-provider-interface.md)
- [ADR 0002 — Frontend Runtime Config](docs/adr/0002-frontend-runtime-config.md)
- [ADR 0003 — Deploy by SHA](docs/adr/0003-deploy-by-sha.md)
- [ADR 0004 — PII and Data Governance](docs/adr/0004-pii-and-data-governance.md)
