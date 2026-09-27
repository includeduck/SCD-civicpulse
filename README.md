# CivicPulse

> **CS4032 Software Construction and Design — Assignment 01**

<!-- CI/CD badges are added in Phases 13–14, once .github/workflows/ci.yml and cd.yml exist. -->
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

> **Not available yet.** `compose.yaml` arrives in Phase 9. Until then, run the backend directly — see [Backend Development](#backend-development). The steps below are the target workflow.

```bash
# 1. Clone
git clone https://github.com/includeduck/SCD-civicpulse.git
cd SCD-civicpulse

# 2. Configure
cp .env.example .env
# Edit .env as needed (defaults work for local dev with simulated triage)

# 3. Start everything
docker compose up --build

# 4. Open
#   Frontend  → http://localhost:80
#   API docs  → http://localhost:8000/docs
#   Metrics   → http://localhost:8000/metrics
```

---

## Backend Development

Run the backend outside Docker for faster iteration (Python 3.12, matching the image).

`DATABASE_URL` and `REDIS_URL` are required: there are no built-in defaults, so no credentials live in source. They're read from the environment or from the repository-root `.env`. `.env.example` uses the Compose service names (`postgres`, `redis`), which only resolve inside Docker. When running the backend directly on your machine, point them at `localhost` in your `.env`, e.g. `DATABASE_URL=postgresql+asyncpg://civicpulse:<password>@localhost:5432/civicpulse`.

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
| 9 | Docker Compose, networks, volumes | ⏳ Next |
| 10–15 | Tests, Kubernetes, CI/CD, documentation | 🔜 Planned |

See [CivicPulse_ImplementationPlan.md](CivicPulse_ImplementationPlan.md) for the full plan.

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

> **Not available yet** — manifests and `scripts/k8s-up.sh` arrive in Phases 11–12.

```bash
# Requires k3d or kind installed
./scripts/k8s-up.sh          # create cluster + deploy
kubectl -n civicpulse get all
```

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
- [ADR 0001 — Provider Interface](docs/adr/0001-provider-interface.md)
- [ADR 0002 — Frontend Runtime Config](docs/adr/0002-frontend-runtime-config.md)
- [ADR 0003 — Deploy by SHA](docs/adr/0003-deploy-by-sha.md)
- [ADR 0004 — PII and Data Governance](docs/adr/0004-pii-and-data-governance.md)
