# ADR 0003 — Deploy by SHA (Immutable Image References)

**Status:** Accepted (implemented in Phase 14)
**Date:** 2026-09-14, updated 2026-09-28
**Deciders:** CivicPulse team

---

## Context

Deploying `:latest` makes it impossible to say what is running, to reproduce it, or to roll it back: `:latest` moves every time something is pushed, so "roll back to latest" rolls *forward* to the newest push, broken or not.

## Decision

- **Every image is pushed with the full commit SHA as its tag** (`.github/workflows/cd.yml`, `build-push`). `:latest` is pushed alongside for convenience and **never deployed**.
- **The deploy pins both the SHA and the digest**: `ghcr.io/includeduck/scd-civicpulse/backend:<sha>@sha256:<digest>` (`scripts/cd_deploy.sh`). The SHA answers "what is running?" (paste it into `git show`); the digest is what the runtime actually pulls, so even a re-pushed tag can't change it.
- `scripts/cd_deploy.sh` refuses to deploy any reference containing `latest`, and checks after the rollout that the backend is really running the SHA it was given.
- **The committed prod overlay carries a deliberately invalid placeholder tag** (`set-by-cd-to-a-commit-sha`), so applying it unedited fails instead of running something stale.
- `build-push` exposes both digests as job outputs, and publishes an SPDX SBOM (Syft) for exactly those digests.

## Rollback: two ways, and when to use each

Both demonstrated on k3d on 2026-09-28 (`docs/evidence/k8s-rollback.txt`).

| | Declarative | Imperative |
|---|---|---|
| **How** | Re-run the deploy with the previous SHA: `IMAGE_SHA=<previous sha> bash scripts/cd_deploy.sh`, or re-run CD for that commit | `kubectl -n civicpulse rollout undo deployment/backend` |
| **Speed** | A normal deploy (migrations, rollout, smoke test) | Seconds: the previous ReplicaSet is still there |
| **Record** | Git and the CD history say exactly what's running | The cluster diverges from Git. Kubernetes itself warns that `last-applied-configuration` is now stale, so the next `kubectl apply` silently reverts the undo |
| **When** | The normal way, and the way to *finish* any incident | At 3 a.m., when production is on fire and seconds matter. Follow up with a declarative deploy of the intended SHA once it's out |

## Consequences

- **Positive:** any deployment is reproducible from its SHA, auditable in the CD history, and reversible by re-deploying an earlier SHA.
- **Positive:** the image that passed CI's tests and Trivy scan is byte-for-byte the one deployed.
- **Negative:** CD must carry the SHA and the digests correctly through every job (done with job outputs), and old SHA-tagged images must be kept in the registry for as long as we might roll back to them.
