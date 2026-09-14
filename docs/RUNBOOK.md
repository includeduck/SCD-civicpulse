# Runbook

> Operational procedures for CivicPulse.

---

## Deploy (local Docker Compose)

```bash
cp .env.example .env   # first time only
docker compose up --build -d
```

## Deploy (Kubernetes)

```bash
# TODO: Phase 11
```

## Rollback

```bash
# TODO: Phase 14
# kubectl -n civicpulse rollout undo deployment/backend
```

## Read Logs

```bash
docker compose logs -f backend
# or
kubectl -n civicpulse logs -l app=backend --tail=100 -f
```

## Triage Failure Response

If triage fails, the system falls back to `RuleBasedTriage` and sets `triaged_by = rules:fallback`.
Check the backend log for a WARNING line containing the complaint ID, provider name, and error class.

```bash
docker compose logs backend | grep "triage_fallback"
```
