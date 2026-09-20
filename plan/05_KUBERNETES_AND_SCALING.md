# 16. Phase 11 — Kubernetes Base and Dev Overlay

## Cluster

Use either:

```text
kind
```

or:

```text
k3d
```

Pick one and standardize it for local development and CI.

## Base

Create:

```text
namespace.yaml
backend.yaml
frontend.yaml
postgres.yaml
redis.yaml
ingress.yaml
configmap.yaml
secret.yaml
hpa.yaml
vpa.yaml
pdb.yaml
kustomization.yaml
```

## PostgreSQL

Use:

```text
StatefulSet
volumeClaimTemplates
```

Never use a Deployment for PostgreSQL.

Delete the PostgreSQL pod:

```bash
kubectl delete pod ...
```

Verify data survives.

## Redis

Deployment + PVC.

## Services

Four ClusterIP Services:

```text
frontend
backend
postgres
redis
```

No DB NodePort.

No DB LoadBalancer.

No Redis public service.

## ConfigMap / Secret

ConfigMap:

- non-sensitive configuration

Secret:

- DB password
- LLM API key

Committed Secret manifests contain placeholders only.

Never commit a real credential, even base64 encoded.

## Ingress

One host.

Routes:

```text
/    -> frontend
/api -> backend
```

Ensure frontend's `/api` calls work through Ingress.

---

# 17. Phase 12 — Probes, HPA, VPA, Load Test

## Probes

### Startup

```yaml
httpGet:
  path: /health
  port: 8000
failureThreshold: 30
periodSeconds: 2
```

### Liveness

```text
/health
```

Must not depend on DB.

### Readiness

```text
/ready
```

Must depend on PostgreSQL + Redis.

## Rolling update

Configure:

```text
maxSurge: 1
maxUnavailable: 0
```

plus:

- termination grace
- preStop delay

## HPA

Backend:

```text
minReplicas: 2
maxReplicas: 10
CPU target: 60%
scaleDown stabilization: 300s
scaleUp stabilization: 0s
```

Set CPU requests.

Without CPU requests, HPA CPU utilization cannot behave as required.

## Metrics server

Install metrics-server appropriate to chosen local cluster.

Verify:

```bash
kubectl top pods -n civicpulse
```

## Load test

Use k6 or hey.

Record:

- offered load
- backend CPU
- replica count
- time
- request failures

Capture:

```bash
kubectl get hpa -w
```

Create replicas-vs-load chart.

Calculate HPA lag:

```text
time replicas begin increasing
-
time offered load increases
```

Explain where lag comes from.

## VPA

Install VPA.

Backend:

```yaml
updatePolicy:
  updateMode: "Off"
```

Run load.

Capture:

```bash
kubectl describe vpa backend-vpa
```

Record:

- Target
- Lower Bound
- Upper Bound

Update CPU/memory requests based on recommendations.

Rerun load.

Compare HPA behavior before and after.

Explain:

- HPA uses CPU utilization relative to request
- VPA Auto changes requests
- changing request changes HPA's utilization denominator
- both controllers can fight
- therefore VPA remains recommender-only in this assignment

---
