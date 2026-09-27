# Runbook

> Operational procedures for CivicPulse: deploy, check health, read logs, respond when triage fails, shut down safely, roll back.

---

## Deploy (local Docker Compose)

```bash
cp .env.example .env              # first time only; change POSTGRES_PASSWORD
docker compose up --build -d --wait
docker compose ps                 # every long-running service should be "healthy"
```

Start-up order is enforced by healthchecks: `postgres` and `redis` healthy, then `migrate` (migrations plus the idempotent seed) completes, then `backend` becomes healthy, then `frontend` starts. `ollama` starts in parallel after `ollama-pull` finishes. The backend doesn't wait for it; until Ollama is healthy, triage falls back to the rules.

| Symptom | Check |
|---------|-------|
| `backend` never starts | `docker compose logs migrate`: a failed migration stops the backend on purpose |
| `ollama` stays unhealthy | `docker compose logs ollama-pull ollama`; the first download is ~1.3 GB, and the model must fit in the 3 GB limit |
| Complaints show `rules:fallback` | Ollama not ready yet, or see "When triage starts failing" below |
| `429` from every client | The backend must trust X-Forwarded-For from the frontend only: `FORWARDED_ALLOW_IPS` must equal the frontend's `ipv4_address` in the compose file |

Stop, keeping data: `docker compose down`. Stop and **delete all data** (database, Redis, model weights): `docker compose down -v`.

## Deploy (production Compose)

```bash
export IMAGE_TAG=$(git rev-parse HEAD)   # the images CI published for this commit
docker compose -f compose.prod.yaml pull
docker compose -f compose.prod.yaml up -d --wait
```

`compose.prod.yaml` refuses to start without `IMAGE_TAG`. It runs migrations only (no demo seed), publishes only the frontend's port, and has no bind mount.

## Deploy (Kubernetes)

**Local (k3d):** `bash scripts/k8s-up.sh`, which is safe to re-run. To deploy by hand:

```bash
kubectl -n civicpulse delete job migrate --ignore-not-found   # a Job's template is immutable
kubectl apply -k k8s/overlays/dev
kubectl -n civicpulse wait --for=condition=complete job/migrate --timeout=300s
kubectl -n civicpulse rollout status deploy/backend
```

**Production overlay:** CD (Phase 14) creates the Secret from GitHub Secrets, then pins the images to the commit SHA before applying:

```bash
kubectl -n civicpulse create secret generic backend-secrets   --from-literal=POSTGRES_PASSWORD=... --from-literal=GROQ_API_KEY=...   --dry-run=client -o yaml | kubectl apply -f -
(cd k8s/overlays/prod && kustomize edit set image   civicpulse/backend=ghcr.io/includeduck/scd-civicpulse/backend:$SHA   civicpulse/frontend=ghcr.io/includeduck/scd-civicpulse/frontend:$SHA)
kubectl apply -k k8s/overlays/prod
```

| Symptom | Check |
|---------|-------|
| Backend pods stuck in `Init:0/1` | They wait for the schema: `kubectl -n civicpulse logs deploy/backend -c wait-for-schema`, then `kubectl -n civicpulse logs job/migrate` (failed attempts are kept as pods) |
| Backend `0/1` but not restarting | Readiness failing, i.e. PostgreSQL or Redis unreachable; `kubectl -n civicpulse exec deploy/backend -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read())"` names it. This is the designed behaviour: see `docs/evidence/k8s-probes.txt` |
| Everyone gets `429` at once | The limiter keys on the client address Traefik records; see `k8s/k3d/traefik-config.yaml` |

## Rollback

```bash
kubectl -n civicpulse rollout undo deployment/backend     # fast: back to the previous ReplicaSet
kubectl -n civicpulse rollout history deployment/backend  # what's available (revisionHistoryLimit: 5)
```

The declarative rollback, re-applying the previous commit's SHA through the prod overlay, arrives with CD in Phase 14.

---

## Health checks

| Endpoint | Meaning | Healthy | Used by |
|----------|---------|---------|---------|
| `GET /health` | The process is alive. Never touches the DB or Redis | `200 {"status":"ok"}` | Liveness and startup probes, Docker `HEALTHCHECK` |
| `GET /ready` | PostgreSQL **and** Redis reachable (2 s timeout each) | `200 {"status":"ready"}` | Readiness probe; `503` names the failed dependency, e.g. `{"dependencies":{"redis":{"status":"failed","error":"TimeoutError"}}}` |
| `GET /metrics` | Prometheus text format | `200` | Scraping, dashboards |

A failing `/health` means restart the pod. A failing `/ready` means stop sending it traffic until the named dependency recovers. Don't wire them the other way round: a slow database would then restart every pod.

## Read logs

Every line on stdout is one JSON object, including uvicorn's own lifecycle lines. There's no log file.

```bash
docker compose logs -f backend
kubectl -n civicpulse logs -l app=backend --tail=100 -f
```

Useful fields: `event`, `level`, `timestamp`, `request_id`, `logger`, plus event-specific ones.

| `event` | Level | When | Key fields |
|---------|-------|------|------------|
| `request_completed` | info | Every HTTP request | `method`, `endpoint` (route template), `status_code`, `duration_ms` |
| `complaint_created` | info | A complaint is stored | `complaint_id`, `category`, `priority`, `triaged_by`, `triage_latency_ms`, `triage_cache_hit` |
| `triage_retry` | info | A provider call is retried once | `provider`, `error_class`, `delay_seconds` |
| `triage_fallback` | **warning** | The provider failed; rules answered | `complaint_id`, `provider`, `error_class` |
| `rate_limited` | info | A client exceeded the limit (429) | `retry_after` |
| `rate_limiter_unavailable`, `stats_cache_unavailable`, `triage_cache_unavailable` | warning | Redis errors; the service degrades but keeps working | `operation`, `error_class` |
| `shutdown_complete` | info | Graceful shutdown finished | `closed` |

**Follow one request end to end.** Send or read `X-Request-ID`; every line for that request carries the same `request_id`:

```bash
docker compose logs backend | grep '"request_id": "<id from the X-Request-ID response header>"'
```

Logs never contain API keys, complaint text, `reporter_contact` or client IPs (ADR 0004).

## Metrics

```bash
curl -s localhost:8000/metrics | grep ^civicpulse_
```

| Metric | Type | Labels |
|--------|------|--------|
| `civicpulse_requests_total` | counter | `method`, `endpoint` (route template or `unmatched`), `status_code` |
| `civicpulse_request_duration_seconds` | histogram | `method`, `endpoint` |
| `civicpulse_triage_duration_seconds` | histogram | `triaged_by` |
| `civicpulse_triage_fallbacks_total` | counter | `provider`, `error_class` |
| `civicpulse_triage_retries_total` | counter | `provider`, `error_class` |
| `civicpulse_triage_cache_total` | counter | `result` = hit / miss |
| `civicpulse_stats_cache_total` | counter | `result` = hit / miss / error |
| `civicpulse_rate_limit_total` | counter | `outcome` = allowed / rejected / error |

Labels are bounded sets. Complaint ids and request ids are never labels.

---

## When triage starts failing

Citizens are unaffected: every complaint still gets `201`, triaged by the rules and stored as `triaged_by = rules:fallback`. What you'll see:

1. **Spot it.** `/api/meta/providers` shows `"fallback": true` in `recent_outcomes`; `civicpulse_triage_fallbacks_total` rises; the logs show `triage_fallback` warnings.
2. **Find the cause from `error_class`:**

   | `error_class` | Meaning | Action |
   |---------------|---------|--------|
   | `TriageTimeoutError` | The provider is slower than `TRIAGE_TIMEOUT_SECONDS` (retried once) | Check the provider's status; for Ollama, check the model is loaded (cold start) and the container has enough CPU/memory |
   | `TriageRateLimitedError` | HTTP 429, quota exhausted (retried once) | Wait for the quota window; check `civicpulse_rate_limit_total` for abuse; the AI cache hit rate is in `/api/meta/providers` |
   | `TriageServerError` | HTTP 5xx from the provider (retried once) | Provider incident; the fallback covers it |
   | `TriageBadRequestError` | HTTP 4xx (not retried). 401/403 means a bad or revoked `GROQ_API_KEY`; 404 means a wrong `GROQ_MODEL` | Fix the configuration and redeploy; **never paste the key into a ticket or log** |
   | `TriageUnavailableError` | Can't connect (DNS or connection refused) | Check `OLLAMA_BASE_URL` / network; is the Ollama container up? |
   | `TriageInvalidOutputError` | The model answered outside the schema | Occasional instances are normal and already handled; a sustained rate points to a model or prompt problem |

   ```bash
   docker compose logs backend | grep triage_fallback
   curl -s localhost:8000/metrics | grep civicpulse_triage_fallbacks_total
   ```

3. **To take the model out of the path entirely,** set `TRIAGE_PROVIDER=rules` and restart. Triage quality drops, but every call is deterministic and instant.
4. **To rehearse this safely,** run `TRIAGE_PROVIDER=simulated SIMULATED_FAILURE_MODE=server_error` (or `timeout`, `bad_request`, `invalid`…) and watch the steps above happen.

---

## Graceful shutdown (SIGTERM)

On `docker stop` / a Kubernetes rolling update, uvicorn (PID 1, exec-form `CMD`) receives SIGTERM and:

1. **stops accepting** new connections (they're refused; the load balancer should already have removed the pod via readiness and the preStop delay);
2. **drains** in-flight requests, for at most 25 s (`--timeout-graceful-shutdown 25` in `backend/Dockerfile`, inside Kubernetes' default 30 s grace period);
3. runs the app shutdown: **closes the DB pool, the Redis client and the provider's HTTP client**, then logs `shutdown_complete`;
4. exits with code `0`.

Verified on 2026-09-27 with the real image: a complaint that took 4 s was in flight when `docker stop` sent SIGTERM one second in. It completed with `201`, a new request during the drain was refused, and the container exited `0` in 3.5 s. The logs showed `Shutting down` → `Waiting for connections to close` → `request_completed 201` → `shutdown_complete`.

To reproduce:

```bash
# with SIMULATED_LATENCY_MS=4000 set on the backend
curl -X POST localhost:8000/api/complaints -H 'content-type: application/json' \
     -d '{"text":"Pipe burst, paani sarak par beh raha hai","location":"F-8"}' &
sleep 1 && docker stop backend
```
