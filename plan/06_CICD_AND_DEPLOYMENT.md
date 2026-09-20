# 18. Phase 13 — CI

Create `.github/workflows/ci.yml`.

## Trigger

```yaml
pull_request:
  branches: [main]

push:
  branches: [dev]
```

## Jobs

Suggested:

```text
lint-and-type
test-backend
test-frontend
build
scan
manifests
integration
```

Jobs may be combined where sensible, but publishing/deployment must remain separately gated in CD.

## Backend checks

```bash
ruff check .
mypy .
pytest --cov=app --cov-fail-under=65
```

Use deterministic simulated provider.

## Frontend

```bash
npm run lint
npm run typecheck
npm test
```

## Build

Build both images.

Do not push from PR CI.

## Trivy

Scan both images.

Fail on:

```text
HIGH
CRITICAL
```

Use a fixed scanner version where possible.

## Kubeconform

Run:

```bash
kustomize build k8s/overlays/prod | kubeconform ...
```

The exact kubeconform arguments should match the installed schema/version.

## Compose integration

The test should verify a real end-to-end path.

Pseudo-sequence:

```bash
docker compose up -d
wait until /ready
POST /api/complaints
GET complaint
GET /api/stats -> MISS
GET /api/stats -> HIT
docker compose down -v
```

Do not merely test that containers are running.

---

# 19. Phase 14 — CD, GHCR, Deployment, Rollback

Create `.github/workflows/cd.yml`.

## Pipeline

```text
test
  |
  v
build-push
  |
  v
deploy
```

Explicit `needs`.

## Build/push

Tags:

```text
${GITHUB_SHA}
latest
```

Generate SBOM with Syft.

Capture image digest.

## Deployment

Create ephemeral kind/k3d cluster.

Apply:

```text
k8s/overlays/prod
```

with immutable SHA image reference.

Never deploy:

```text
latest
```

Wait:

```bash
kubectl rollout status ...
```

Smoke test the Ingress.

Print:

```bash
kubectl get hpa -n civicpulse
```

## Permissions

Use least privilege.

Example conceptual block:

```yaml
permissions:
  contents: read
  packages: write
```

Do not grant broad write permissions by default.

## Secrets

Use GitHub Secrets.

Never:

- account password
- hardcoded token
- committed registry credential

## Rollback demonstration

### Fast imperative rollback

```bash
kubectl rollout undo deployment/backend -n civicpulse
```

### Declarative rollback

Reapply previous Kustomize overlay with previous immutable SHA.

Document when each is appropriate.

---
