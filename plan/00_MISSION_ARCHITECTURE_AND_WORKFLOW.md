# CivicPulse — Agent-Executable Implementation Plan

> **Purpose:** This document is the single implementation plan for building the CivicPulse assignment from a clean repository. It is written so that a coding agent can execute the work phase-by-phase, while a human team can review, test, commit, and demonstrate each phase.
>
> **Source of truth:** CS4032 Software Construction and Design — Assignment 01: CivicPulse. The implementation must satisfy the assignment contracts; do not silently weaken requirements for convenience.
>
> **Team:** 2 members  
> **Primary stack:** React 18 + Vite + TypeScript, FastAPI + Pydantic v2, PostgreSQL 16, Redis 7, Docker Compose, Kubernetes + Kustomize, GitHub Actions.

---

## 0. Mission

Build an end-to-end municipal complaint intake, AI triage, persistence, operations dashboard, caching, rate-limiting, containerization, Kubernetes deployment, autoscaling, and CI/CD system.

The final repository must allow:

1. A stranger to clone the repository and start the complete local system with one command.
2. Seeded data to appear without manual SQL.
3. A second command to deploy the system to a local Kubernetes cluster.
4. A push to `main` to run tests, build and scan images, publish them, deploy an immutable SHA-tagged image, and smoke-test the deployment.
5. A rollback to be demonstrable.
6. Every README claim to be backed by executable evidence.

Do not optimize for "code that looks complete." Optimize for **contracts, deterministic tests, observable behavior, security, and demonstrable evidence**.

---

# 1. Non-Negotiable Requirements

Treat these as hard acceptance criteria.

## 1.1 Backend

- FastAPI + Pydantic v2.
- Four layers:
  - `routes/`: HTTP only.
  - `services/`: business rules/orchestration.
  - `repositories/`: all SQL.
  - `providers/`: outbound integrations behind interfaces.
- Routes must not open DB sessions.
- No SQL outside repositories.
- No business rules in routes.
- Required endpoints:
  - `POST /api/complaints`
  - `GET /api/complaints/{id}`
  - `GET /api/complaints`
  - `PATCH /api/complaints/{id}/status`
  - `GET /api/stats`
  - `GET /api/meta/providers`
  - `GET /health`
  - `GET /ready`
  - `GET /metrics`
- `POST`:
  - validate input
  - rate-limit
  - triage
  - persist
  - return `201`
  - return `400` for validation
  - return `429` with `Retry-After` when rate limited
- List endpoint:
  - category filter
  - priority filter
  - status filter
  - pagination
  - `page_size <= 100`
  - total count
- Status transitions:
  - `open -> in_progress`
  - `in_progress -> resolved`
  - `open -> rejected`
  - `in_progress -> rejected`
  - `resolved` terminal
  - `rejected` terminal
- Invalid transition must return `409` and name the attempted transition.
- `/health` must not touch DB.
- `/ready` must verify PostgreSQL and Redis and return `503` naming failed dependency.
- JSON logs to stdout.
- Every request has `request_id`, propagated from `X-Request-ID` or generated.
- Triage fallback emits one WARNING containing complaint ID, provider, and error class.
- Graceful SIGTERM handling.

## 1.2 Data

PostgreSQL 16 with Alembic migrations.

Complaint fields:

- `id`: UUID, server generated
- `text`: 10–2000 chars
- `location`: 3–200 chars
- `reporter_contact`: nullable
- `category`: `water | electricity | sanitation | roads | streetlights | other`
- `priority`: `high | normal | low`
- `status`: `open | in_progress | resolved | rejected`
- `ai_summary`: nullable, <= 140 chars
- `triaged_by`: `llm:groq | llm:ollama | rules | rules:fallback`
- `triage_latency_ms`: integer
- `created_at`: timestamptz UTC
- `updated_at`: timestamptz UTC

Required indexes:

- `(status, priority)`
- `created_at`

Required:

- DB-level text length constraints in addition to application validation.
- Idempotent seed with >=30 realistic Urdu-influenced English complaints.
- Running seed twice must not duplicate rows.
- Compose restart preserves rows.
- PostgreSQL pod deletion preserves rows.

## 1.3 Redis

Redis 7 must perform two jobs:

### Stats cache

- `/api/stats`
- read-through
- TTL 30 seconds
- `X-Cache: HIT|MISS`
- invalidate after writes

### Distributed rate limiter

- Redis-backed
- keyed by client IP
- fixed-window or token-bucket implementation
- protects `POST /api/complaints`
- `429`
- `Retry-After`
- must work correctly across multiple backend replicas

Redis AOF must be enabled on a named volume and justified in engineering notes.

## 1.4 AI

Define:

```python
class TriageResult(BaseModel):
    category: Category
    priority: Priority
    summary: str = Field(max_length=140)
    confidence: float = Field(ge=0.0, le=1.0)
```

Define a provider interface/protocol:

```python
class TriageProvider(Protocol):
    name: str

    def triage(self, text: str, location: str) -> TriageResult:
        ...
```

Implement:

1. `LLMTriage`
2. `OllamaTriage`
3. `RuleBasedTriage`
4. `SimulatedTriage`

Provider selected by `TRIAGE_PROVIDER`.

AI requirements:

- structured JSON requested from LLM
- Pydantic validation always performed
- 10-second timeout
- one jittered retry only for timeout / 429 / 5xx
- never retry 400
- fallback to `RuleBasedTriage`
- fallback records `triaged_by = rules:fallback`
- triage result cached by content hash in Redis for 24h
- measured cache hit rate
- API keys never logged
- prompt-injection guardrail
- injection test
- `triage_latency_ms` measured
- provider/latency/fallback surfaced by `/api/meta/providers`
- CI uses deterministic `SimulatedTriage`

Mandatory resilience test:

> If the provider always raises, `POST /api/complaints` still returns `201` and `triaged_by == "rules:fallback"`.

## 1.5 Frontend

React 18 + Vite + TypeScript.

Views:

### Submit

- complaint text
- location
- optional contact
- client validation mirroring server rules
- honest loading state
- display:
  - category
  - priority
  - AI summary
  - provider

### Dashboard

- pagination
- filters:
  - category
  - priority
  - status
- status update
- display server's 409 message verbatim

### Stats

- aggregate counts by category and priority
- show `X-Cache`

Hard rule:

> Frontend must not contain the backend's status transition table or duplicate business rules.

Runtime API configuration must NOT be baked into the Vite build.

Choose one:

- `/config.js` generated at container startup, OR
- nginx `/api` reverse proxy.

Prefer nginx proxy if it cleanly satisfies the architecture and removes the need for an absolute backend URL.

Required:

- typed API client generated from or checked against OpenAPI
- error boundary
- no secrets in frontend
- >=5 meaningful Vitest component tests

## 1.6 Docker

Two multi-stage, pinned, non-root images.

### Backend

- `python:3.12-slim`
- dependency installation in builder
- requirements copied before source
- non-root
- exec-form `CMD`
- `HEALTHCHECK`
- pinned image tag; digest is bonus

### Frontend

- `node:22-alpine` builder
- `nginx:1.27-alpine` runtime
- final image has:
  - no Node
  - no `node_modules`
  - no source
- target roughly <=60 MB
- `.dockerignore`

## 1.7 Compose

Two networks:

```text
edge
internal (internal: true)
```

Topology:

```text
frontend -> edge -> backend
backend -> internal -> postgres
backend -> internal -> redis
```

Frontend must not reach DB.

Required proof:

```bash
docker compose exec frontend ping database
```

must fail.

Important architecture constraint:

`internal: true` prevents outbound internet access from DB/cache/internal-only services. A hosted LLM caller therefore cannot be an internal-only service. Resolve and document this explicitly.

Three named volumes:

- `pgdata`
- `redisdata`
- `ollama_models`

Development-only backend bind mount for hot reload.

Production must not use the bind mount.

All services:

- healthcheck
- `depends_on: condition: service_healthy`
- credentials from `.env`
- `.env.example` committed
- `.env` gitignored
- pinned images
- `restart: unless-stopped`
- resource limits

Production:

- `compose.prod.yaml`
- `image: ${IMAGE_TAG}`
- no `build:`
- no DB/cache published ports

## 1.8 Kubernetes

Use k3d or kind.

Use Kustomize:

```text
k8s/base/
k8s/overlays/dev/
k8s/overlays/prod/
```

Everything in namespace:

```text
civicpulse
```

Required:

- backend Deployment >=2 replicas
- frontend Deployment >=2 replicas
- PostgreSQL StatefulSet
- PostgreSQL `volumeClaimTemplates`
- Redis Deployment + PVC
- four ClusterIP Services
- Ingress:
  - `/` -> frontend
  - `/api` -> backend
- ConfigMap
- Secret
- HPA backend
- PDB backend, `minAvailable: 1`

Probes:

- startup -> `/health`
- liveness -> `/health`
- readiness -> `/ready`

Backend startup probe:

- failure threshold 30
- period 2 seconds

Rolling update:

- `maxSurge: 1`
- `maxUnavailable: 0`
- termination grace period
- preStop delay

HPA:

- autoscaling/v2
- min 2
- max 10
- CPU target 60%
- scale-down stabilization 300s
- scale-up stabilization 0s
- CPU requests mandatory

VPA:

- backend only
- `updateMode: Off`
- record Target / Lower Bound / Upper Bound
- update requests based on recommendation
- rerun load test
- explain HPA/VPA conflict

## 1.9 CI/CD

Branches:

```text
main
dev
feature/*
```

`main` protected:

- PR required
- CI required
- one approval

### ci.yml

Runs on:

- PR to `main`
- push to `dev`

Must run:

- backend Ruff
- backend mypy
- frontend ESLint
- frontend `tsc --noEmit`
- pytest
- backend coverage >=65% on `app/`
- frontend Vitest >=5 meaningful tests
- build both images without push
- Trivy HIGH/CRITICAL failure
- Kustomize build + kubeconform
- Compose integration test

Integration test must:

1. start Compose
2. wait for `/ready`
3. POST complaint
4. GET complaint
5. assert category
6. assert `/api/stats` MISS
7. assert next `/api/stats` HIT
8. shut down with `docker compose down -v`

### cd.yml

Runs on push to `main`.

Must:

1. run full tests
2. build images
3. push to GHCR
4. tag with commit SHA and `latest`
5. generate SBOM using Syft
6. expose image digest as output
7. create kind/k3d cluster
8. deploy with immutable SHA
9. wait for rollout
10. smoke-test Ingress
11. print HPA

Every publishing/deploying job must use `needs`.

`:latest` may be pushed but must NEVER be deployed.

### release.yml

On `v*` tag:

- build
- push semver tags
- generate release notes

## 1.10 Documentation

Required:

```text
README.md
docs/ENGINEERING-NOTES.md
docs/RUNBOOK.md
docs/AI-USAGE.md
docs/TRIAGE.md
docs/adr/0001-provider-interface.md
docs/adr/0002-frontend-runtime-config.md
docs/adr/0003-deploy-by-sha.md
docs/adr/0004-pii-and-data-governance.md
docs/evidence/*
```

README:

- problem statement
- badges
- Mermaid architecture
- one-command quickstart
- API table
- screenshots

Runbook:

- deploy
- rollback
- read logs
- triage failure response

AI usage:

- tools used
- what AI wrote/shaped
- what humans changed
- why

Engineering notes must answer all 8 assignment questions with exact file + line references.

---

# 2. Repository Target Structure

Create this structure early and preserve it:

```text
civicpulse/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── providers/
│   │   │   └── triage/
│   │   │       ├── base.py
│   │   │       ├── llm.py
│   │   │       ├── ollama.py
│   │   │       ├── rules.py
│   │   │       ├── simulated.py
│   │   │       └── factory.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── core/
│   │   └── main.py
│   ├── alembic/
│   │   └── versions/
│   ├── tests/
│   ├── Dockerfile
│   ├── .dockerignore
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── ...
│   ├── tests/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── nginx.conf
│   └── package.json
│
├── k8s/
│   ├── base/
│   │   ├── namespace.yaml
│   │   ├── backend.yaml
│   │   ├── frontend.yaml
│   │   ├── postgres.yaml
│   │   ├── redis.yaml
│   │   ├── ingress.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   ├── hpa.yaml
│   │   ├── vpa.yaml
│   │   ├── pdb.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── dev/
│       │   └── kustomization.yaml
│       └── prod/
│           └── kustomization.yaml
│
├── load/
│   └── k6-script.js
│
├── docs/
│   ├── ENGINEERING-NOTES.md
│   ├── RUNBOOK.md
│   ├── AI-USAGE.md
│   ├── TRIAGE.md
│   ├── adr/
│   │   ├── 0001-provider-interface.md
│   │   ├── 0002-frontend-runtime-config.md
│   │   ├── 0003-deploy-by-sha.md
│   │   └── 0004-pii-and-data-governance.md
│   └── evidence/
│
├── scripts/
│   └── check_submission.py
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── cd.yml
│       └── release.yml
│
├── compose.yaml
├── compose.prod.yaml
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

Agents may add sensible files, but must not remove required assignment structure without documenting why.

---

# 3. Implementation Order

Use this order. Do not begin Kubernetes or polished UI before the backend contract is stable.

```text
Phase 0  Repository + team workflow
Phase 1  Backend skeleton + configuration
Phase 2  Database + migrations + repositories
Phase 3  Domain services + complaint API
Phase 4  Triage abstraction + rules + simulated
Phase 5  LLM/Ollama + resilience + AI cache
Phase 6  Redis stats cache + rate limiter
Phase 7  Observability + graceful shutdown
Phase 8  Frontend + typed API + runtime configuration
Phase 9  Docker + Compose + network isolation
Phase 10 Automated tests + integration suite
Phase 11 Kubernetes base + dev overlay
Phase 12 HPA + VPA + load testing
Phase 13 CI
Phase 14 CD + GHCR + ephemeral deployment
Phase 15 Documentation + evidence + demo
Phase 16 Final audit + submission
```

Do not skip directly from local code to "final CI." Each phase must produce a runnable checkpoint.

---

# 4. Agent Operating Protocol

Every coding agent working on this repository must follow this protocol.

## Before editing

1. Read this `ImplementationPlan.md`.
2. Inspect the existing repository.
3. Identify the current phase.
4. Inspect relevant existing tests and contracts.
5. Do not rewrite unrelated files.
6. Do not introduce dependencies without justification.
7. Do not change an assignment requirement merely because it is inconvenient.

## While editing

1. Prefer small, coherent changes.
2. Preserve the four-layer backend architecture.
3. Keep business rules testable outside HTTP routes.
4. Keep external providers behind interfaces.
5. Keep tests deterministic.
6. Never hardcode secrets.
7. Never use `localhost` for service-to-service communication.
8. Never expose PostgreSQL/Redis in production.
9. Never deploy `latest`.
10. Never place credentials in manifests or source.

## After editing

Run the relevant checks.

At minimum:

```bash
git diff --check
```

Then the phase-specific tests.

Report:

- files changed
- behavior added
- tests run
- test result
- unresolved issues
- next recommended task

Do not claim a requirement is complete unless it has been tested or there is explicit evidence.

---

# 5. Phase 0 — Repository and Team Workflow

## Goal

Establish a safe repository before application code.

## Tasks

### 0.1 Initialize Git

- create repository
- create `main`
- create `dev`
- create feature branch
- add `.gitignore`
- add `.env.example`
- add README skeleton
- add LICENSE
- add this implementation plan

### 0.2 Branch rules

Use:

```text
main
dev
feature/backend-foundation
feature/ai-triage
feature/frontend
feature/docker
feature/kubernetes
feature/cicd
```

No direct pushes to `main`.

### 0.3 Commit convention

Use:

```text
feat:
fix:
test:
docs:
refactor:
chore:
ci:
build:
```

### 0.4 Collaboration evidence

Plan for at least:

- 5 merged PRs
- every PR linked to an Issue
- partner review comment on each
- >=35 commits
- neither partner below 35% of commits
- one deliberate real merge conflict

Do not manufacture meaningless commits. Each commit should represent real work.

## Exit criteria

- clean clone exists
- `.env` ignored
- no secrets in history
- branch model exists
- first PR merged
- repository structure created

---


---

# 28. Suggested Human Ownership for a 2-Person Team

A practical split:

## Member 1 — Backend / AI / Data

Own:

- backend
- PostgreSQL
- Redis
- AI providers
- backend tests
- triage docs
- AI ADR

## Member 2 — Frontend / DevOps

Own:

- frontend
- Docker
- Compose
- Kubernetes
- CI/CD
- frontend tests
- runtime config ADR

Both members must understand the whole repository because viva questions can cover partner-written code.

Review each other's major PRs.

---

# 29. Dependency Order Graph

```text
Repository
   |
   +--> Backend foundation
   |       |
   |       +--> Database
   |       |
   |       +--> Domain/API
   |               |
   |               +--> Triage interface
   |                       |
   |                       +--> Rules
   |                       +--> Simulated
   |                       +--> LLM
   |                       +--> Ollama
   |                       |
   |                       +--> Fallback
   |                       +--> AI cache
   |
   +--> Redis
   |       |
   |       +--> Stats cache
   |       +--> Rate limiter
   |
   +--> Frontend
   |       |
   |       +--> Typed API
   |       +--> Submit
   |       +--> Dashboard
   |       +--> Stats
   |
   +--> Docker/Compose
   |       |
   |       +--> Runtime integration
   |       +--> Network isolation
   |
   +--> Kubernetes
   |       |
   |       +--> Deployment
   |       +--> Persistence
   |       +--> Probes
   |       +--> Ingress
   |       +--> HPA
   |       +--> VPA
   |
   +--> CI
   |       |
   |       +--> Tests
   |       +--> Builds
   |       +--> Scan
   |       +--> Manifest validation
   |       +--> Integration
   |
   +--> CD
           |
           +--> GHCR
           +--> SBOM
           +--> Deploy SHA
           +--> Smoke
           +--> Rollback
```

---
