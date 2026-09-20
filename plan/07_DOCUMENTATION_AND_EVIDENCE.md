# 20. Phase 15 — Documentation and Evidence

Documentation is part of the implementation, not an afterthought.

## ADR 0001 — Provider Interface

Must explain:

- why provider abstraction exists
- interface contract
- implementations
- why business logic should not know provider SDK details
- how replacement works

## ADR 0002 — Frontend Runtime Configuration

Must explain:

- Vite build-time environment problem
- chosen solution
- why it enables build-once-deploy-many
- exact implementation

## ADR 0003 — Deploy by SHA

Must explain:

- why `latest` is unsafe for deployment
- how SHA tags identify code
- how rollback identifies previous version
- where immutable reference is configured

## ADR 0004 — PII and Data Governance

Must answer:

- what complaint data leaves machine
- which provider receives it
- whether contact/name/location is sent
- whether data is redacted
- why the chosen exposure is acceptable
- what Ollama changes
- operational implications

Do not invent provider policy claims. Verify the provider's current policy/limits if documenting them.

## TRIAGE.md

Document:

- provider configuration
- expected structured output
- fallback behavior
- timeout/retry
- cache
- prompt injection defense
- how to run simulated mode
- how to run rules mode
- how to run Ollama
- how to configure hosted provider

## RUNBOOK.md

Include:

### Start

```text
one-command quickstart
```

### Logs

How to read Compose logs and Kubernetes logs.

### Health

How to check:

```text
/health
/ready
/metrics
```

### Triage failure

What happens if hosted provider:

- times out
- returns 429
- returns malformed output
- is unavailable

### Deployment

How to deploy.

### Rollback

Both rollback mechanisms.

### Persistence

How to prove DB persistence.

### Scaling

How to inspect HPA/VPA.

## ENGINEERING-NOTES.md

Answer all eight required questions.

Do not write generic textbook answers.

Each answer must contain exact references to your own code, for example:

```text
backend/Dockerfile:18
k8s/base/backend.yaml:42
.github/workflows/cd.yml:71
```

If line numbers change, update the notes before submission.

---

# 21. Required Engineering Notes Questions

Write answers for:

## Q1

Three differences between laptop and CI runner.

For each:

- difference
- exact Dockerfile/manifest/workflow line that freezes or controls it

## Q2

Where the pipeline sits on the CI/CD maturity ladder.

Explain:

- current rung
- evidence
- next rung
- benefit of next rung

## Q3

Exact line guaranteeing build-once-deploy-many.

Explain what breaks without it.

## Q4

LLM is probabilistic.

Define what "correct" means for the component.

Explain:

- schema correctness
- deterministic CI
- provider abstraction
- fallback

## Q5

Measure HPA lag.

Report:

- offered load time
- replica increase time
- lag in seconds
- where the lag came from
- what could reduce it

## Q6

Why VPA is Off.

Explain HPA/VPA feedback conflict.

## Q7

`internal: true` blocks outbound traffic.

Explain exactly where hosted LLM traffic originates and why that architecture is safe.

## Q8

The failure story.

Document one real failure:

- symptom
- first incorrect hypothesis
- investigation
- exact command/log
- root cause
- fix
- lesson

Do not fabricate a failure. Record an actual engineering problem encountered by the team.

---

# 22. Submission Checker

Implement:

```text
scripts/check_submission.py
```

It should be a mechanical lint, not a replacement for tests.

Check as many deterministic requirements as practical, including:

- required files exist
- `.env` absent from tracked files
- obvious secret patterns
- required Dockerfiles
- required workflows
- required Kustomize overlays
- no `latest` in deployment references
- production Compose has no DB/cache published ports
- Postgres uses StatefulSet
- required probes exist
- HPA exists
- VPA Off exists
- required docs exist
- required ADR files exist

Run from repository root:

```bash
python scripts/check_submission.py
```

A clean result does not mean the assignment is fully correct; it only catches mechanical failures.

---

# 23. Evidence Checklist

Create `docs/evidence/`.

Capture evidence for:

## Git

- protected main
- required checks
- approval
- merged PRs
- substantive partner review
- commit distribution
- deliberate merge conflict

## Frontend

- submission page
- loading state
- successful AI result
- dashboard filters
- 409 message
- stats
- X-Cache

## Backend

- OpenAPI
- health
- readiness
- metrics
- JSON logs
- request ID
- fallback warning

## Data

- migration
- seed
- seed idempotency
- persistence after Compose restart
- persistence after PostgreSQL pod deletion

## AI

- provider selection
- structured result
- fallback
- retry
- malformed output
- cache hit
- prompt injection

## Docker

- image sizes
- build contexts
- network topology
- frontend cannot ping DB
- named volumes
- production image-only Compose

## Kubernetes

- pods
- services
- ingress
- probes
- StatefulSet
- PVC
- HPA
- HPA `-w`
- replicas-vs-load chart
- VPA recommendations

## CI/CD

- red blocked PR
- green fixed PR
- Trivy
- kubeconform
- GHCR SHA tag
- SBOM
- deployment
- rollout
- smoke test
- rollback

---
