# 30. Final End-to-End Verification

Before submission, perform the following from a clean clone.

## Local

```bash
cp .env.example .env
docker compose up -d --build
```

Verify:

```text
frontend loads
backend loads
postgres healthy
redis healthy
complaints seeded
```

Submit a new complaint.

Verify:

```text
201
category
priority
summary
provider
```

Verify stats:

```text
first request -> MISS
second request -> HIT
new complaint -> cache invalidated
next stats -> MISS
```

Trigger rate limit.

Verify:

```text
429
Retry-After
```

Test invalid status transition.

Verify:

```text
409
server message shown in UI
```

Test persistence:

```bash
docker compose down
docker compose up -d
```

Verify rows remain.

Test network isolation:

```bash
docker compose exec frontend ping database
```

Must fail.

## Kubernetes

Create clean cluster.

Deploy dev/prod overlay.

Verify:

```bash
kubectl get pods -n civicpulse
kubectl get svc -n civicpulse
kubectl get ingress -n civicpulse
kubectl get pvc -n civicpulse
kubectl get hpa -n civicpulse
kubectl get vpa -n civicpulse
```

Delete PostgreSQL pod.

Verify data remains.

Run load test.

Capture HPA scaling.

Capture VPA recommendation.

Perform rolling update.

Verify no failed requests if claiming the bonus.

Perform rollback.

## CI

Open a PR.

Verify:

- checks run
- failure blocks merge
- fix passes
- merge requires approval

## CD

Merge to main.

Verify:

- test gates publish
- images pushed with SHA
- SBOM generated
- deploy uses SHA
- rollout succeeds
- smoke test succeeds
- HPA output printed

---

# 31. Automatic-Deduction Audit

Before submission, explicitly check every one.

| Risk | Required prevention |
|---|---|
| `.env`, key, token, password in Git history | audit history; rotate if leaked |
| LLM key in K8s manifest | placeholders only |
| Unpinned base images | pin every required image |
| `localhost` service communication | use service names |
| Frontend can reach DB | two-network architecture |
| DB/cache exposed in prod | no published ports |
| Publish/deploy without `needs` | explicit job dependencies |
| Deploying `latest` | deploy SHA/digest |
| PostgreSQL Deployment | use StatefulSet + PVC |
| Direct main push | protected branch |
| Broken clean-clone README | test from fresh environment |

---

# 32. Rubric Coverage Matrix

| Rubric | Implementation location | Evidence |
|---|---|---|
| A Collaboration | Git/GitHub | PRs, reviews, commits, conflict |
| B Frontend | `frontend/` | UI + Vitest |
| C Backend | `backend/` | API + tests |
| D Data | `backend/models`, Alembic, seed | migrations + persistence |
| E Cache | Redis services | HIT/MISS + limiter |
| F AI | `providers/triage/` | provider/fallback/cache tests |
| G Docker | Dockerfiles + Compose | image/network evidence |
| H Kubernetes | `k8s/` | probes/HPA/VPA/load |
| I CI/CD | `.github/workflows/` | red/green + deployment |
| J Documentation | `README`, `docs/` | ADRs/runbook/video/notes |

---

# 33. Priority If Time Runs Out

If behind schedule, follow the assignment's stated priority:

```text
F — AI layer
>
C — Backend
>
I — CI/CD
>
H — Kubernetes
```

Never skip the fallback test.

Within the implementation itself, preserve this minimum viable order:

```text
Backend contract
>
Database
>
Triage abstraction
>
Fallback
>
Redis
>
Frontend
>
Compose
>
Tests
>
Kubernetes
>
CI/CD
>
Documentation/evidence
```

Do not spend hours polishing UI while core backend/AI resilience is incomplete.

---

# 34. Quality Rules for Agents

Agents must not:

- put SQL in routes
- put state transition logic in React
- call real LLMs from CI
- use sleep-based flaky tests
- hardcode API keys
- commit `.env`
- log API keys
- use `localhost` for container-to-container communication
- use a Python in-memory rate limiter
- create DB schema on startup
- deploy `latest`
- expose DB/Redis in production
- use a PostgreSQL Deployment
- omit CPU requests while claiming HPA support
- use VPA Auto with CPU-based HPA
- claim a requirement is tested when it was not tested
- fabricate evidence
- fabricate provider policies or benchmark results
- add unnecessary architecture solely to make the project look more "production-like"

Agents should prefer:

- interfaces
- dependency injection
- deterministic tests
- explicit configuration
- small services
- observable behavior
- reproducible commands
- evidence-backed documentation

---

# 35. Final Agent Audit Prompt

At the end of implementation, give an agent this task:

```text
Perform a strict CivicPulse compliance audit.

Read:
- ImplementationPlan.md
- entire repository
- tests
- Dockerfiles
- compose.yaml
- compose.prod.yaml
- k8s/base/*
- k8s/overlays/*
- .github/workflows/*
- docs/*

Do NOT modify code yet.

Produce a table with:
1. Requirement
2. Expected behavior
3. Exact implementation file
4. Exact line(s)
5. Test/evidence
6. PASS / PARTIAL / FAIL
7. What must change

Audit especially:
- four-layer backend separation
- all API status codes
- status transition table
- health/readiness distinction
- request IDs
- SIGTERM
- schema constraints
- idempotent seed
- Redis stats cache
- cache invalidation
- distributed rate limiter
- AOF
- all triage providers
- structured output validation
- retry policy
- fallback
- AI cache
- prompt injection
- frontend runtime configuration
- Docker network isolation
- Compose persistence
- production Compose
- StatefulSet
- PVC
- probes
- HPA
- VPA
- CI gating
- SHA deployment
- SBOM
- rollback
- documentation
- evidence
- automatic deductions

Do not mark a requirement PASS based solely on code appearance if it requires runtime evidence.
```

---

# 36. Final Submission Checklist

- [ ] Clean clone works
- [ ] One-command Compose quickstart works
- [ ] >=30 seed complaints
- [ ] Seed is idempotent
- [ ] PostgreSQL persistence demonstrated
- [ ] Redis persistence configured/documented
- [ ] All required API endpoints work
- [ ] OpenAPI available
- [ ] Typed frontend client exists
- [ ] Submit UI works
- [ ] Dashboard works
- [ ] Stats works
- [ ] X-Cache visible
- [ ] 409 displayed verbatim
- [ ] Four-layer architecture preserved
- [ ] State machine is explicit
- [ ] Request IDs work
- [ ] JSON logs work
- [ ] SIGTERM works
- [ ] 4 triage implementations exist
- [ ] Provider selected by environment
- [ ] Structured LLM output validated
- [ ] Timeout 10s
- [ ] One retry with jitter for retryable errors
- [ ] Fallback works
- [ ] AI cache works
- [ ] Prompt injection test exists
- [ ] PII ADR complete
- [ ] Redis stats cache works
- [ ] Redis rate limiter works
- [ ] Retry-After works
- [ ] Docker images are multi-stage
- [ ] Images are non-root
- [ ] Images are pinned
- [ ] `.dockerignore` files exist
- [ ] Frontend cannot reach DB
- [ ] Production Compose has no DB/cache ports
- [ ] Kubernetes namespace exists
- [ ] Backend >=2 replicas
- [ ] Frontend >=2 replicas
- [ ] PostgreSQL StatefulSet + PVC
- [ ] Redis Deployment + PVC
- [ ] ClusterIP services
- [ ] Ingress routes `/` and `/api`
- [ ] ConfigMap/Secret separated
- [ ] No real credentials committed
- [ ] Startup/liveness/readiness probes correct
- [ ] HPA works
- [ ] HPA evidence captured
- [ ] replicas-vs-load chart exists
- [ ] VPA Off
- [ ] VPA recommendations committed
- [ ] HPA/VPA conflict documented
- [ ] CI runs lint/type/tests
- [ ] Coverage >=65%
- [ ] >=5 frontend tests
- [ ] Trivy works
- [ ] kubeconform works
- [ ] Compose integration works
- [ ] CD uses `needs`
- [ ] GHCR SHA images exist
- [ ] SBOM exists
- [ ] Deployment uses SHA
- [ ] Ephemeral cluster deployment works
- [ ] Ingress smoke test works
- [ ] Rollback demonstrated
- [ ] Release workflow exists
- [ ] README complete
- [ ] Four ADRs complete
- [ ] Runbook complete
- [ ] Triage docs complete
- [ ] AI usage disclosed
- [ ] Engineering notes answer all 8 questions
- [ ] Demo video <=5 minutes
- [ ] Both partners speak
- [ ] `scripts/check_submission.py` passes
- [ ] Git history audited for secrets
- [ ] `git shortlog -sn` captured
- [ ] Required submission links ready

---

# 37. Success Criterion

The project is finished when a reviewer can start from the repository and independently verify:

```text
Citizen
  |
  v
React/nginx
  |
  v
FastAPI
  |
  +--> Redis rate limiter
  |
  +--> TriageProvider
  |       |
  |       +--> Hosted LLM
  |       +--> Ollama
  |       +--> Rules
  |       +--> Simulated
  |       |
  |       +--> fallback
  |
  +--> PostgreSQL
  |
  +--> Redis stats/AI cache
  |
  v
Operations dashboard
```

and then verify:

```text
Docker Compose
    ->
network isolation
    ->
persistent data
    ->
Kubernetes
    ->
health/readiness
    ->
HPA
    ->
VPA recommendations
    ->
CI
    ->
image scan
    ->
GHCR
    ->
immutable SHA deployment
    ->
smoke test
    ->
rollback
```

The final implementation should be **simple enough to explain in a 10-minute viva, robust enough to survive the required failure tests, and complete enough to demonstrate every rubric claim.**