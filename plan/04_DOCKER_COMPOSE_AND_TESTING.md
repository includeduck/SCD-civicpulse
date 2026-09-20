# 14. Phase 9 — Docker and Compose

## 14.1 Backend Dockerfile

Implement multi-stage build.

Important ordering:

```dockerfile
COPY dependency files
RUN install dependencies
COPY source
```

This preserves dependency cache.

Final stage:

- minimal runtime
- non-root user
- exec-form command
- healthcheck

## 14.2 Frontend Dockerfile

Builder:

```text
node:22-alpine
```

Runtime:

```text
nginx:1.27-alpine
```

Final stage must not contain Node toolchain.

Check:

```bash
docker run --rm IMAGE node --version
```

should fail because Node is absent.

Measure image size.

## 14.3 .dockerignore

Both contexts must exclude at minimum:

```text
.git
node_modules
.venv
__pycache__
.env
test fixtures / unnecessary local artifacts
```

Measure build context before and after.

## 14.4 Compose topology

Services:

```text
frontend
backend
postgres
redis
ollama
```

Use healthchecks.

Use:

```yaml
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_healthy
```

Only use dependencies that are actually required by each service.

## 14.5 Hosted LLM network decision

Because `internal: true` blocks outbound access, a hosted LLM request cannot originate from a service that only joins the internal network.

Choose and document one defensible architecture.

A simple option:

- backend joins `edge` and `internal`
- backend can reach hosted LLM
- PostgreSQL/Redis remain internal-only
- frontend remains edge-only

If stronger egress isolation is desired, introduce an explicit AI gateway architecture, but do not add unnecessary complexity unless it can be tested and justified.

## 14.6 Production Compose

`compose.prod.yaml`:

- images only
- `${IMAGE_TAG}`
- no build
- no source bind mount
- no published DB port
- no published Redis port
- resource limits
- pinned dependencies

## 14.7 Network proof

Run:

```bash
docker compose exec frontend ping database
```

Capture the failure as evidence.

Also verify:

```bash
docker compose exec backend ...
```

can reach required internal services.

---

# 15. Phase 10 — Automated Test Strategy

## Backend minimum

Assignment requires >=14 meaningful backend tests and >=65% coverage of `app/`.

Organize by concern:

```text
tests/
├── test_health.py
├── test_complaints.py
├── test_status_machine.py
├── test_triage.py
├── test_fallback.py
├── test_cache.py
├── test_rate_limit.py
├── test_stats.py
├── test_readiness.py
└── test_metrics.py
```

Recommended coverage beyond minimum:

### API

- validation
- CRUD
- pagination
- filters
- 404
- 409
- 429

### State machine

Test every allowed transition.

Test every invalid transition.

### AI

- deterministic simulated provider
- malformed output
- timeout
- retry
- fallback
- cache hit
- injection attempt

### Redis

- stats MISS
- stats HIT
- invalidation
- rate limit

### Observability

- request ID
- fallback warning
- metrics

## Frontend

>=5 meaningful Vitest tests.

Avoid tests that merely assert a component renders a `<div>`.

## Determinism

CI must use:

```text
TRIAGE_PROVIDER=simulated
```

Never make CI depend on:

- live LLM
- internet access
- timing luck
- `sleep()` calls

---
