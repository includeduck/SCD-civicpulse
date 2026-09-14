# ADR 0003 — Deploy by SHA (Immutable Image Tags)

**Status:** Accepted  
**Date:** 2026-09-14  
**Deciders:** CivicPulse team

---

## Context

Deploying `:latest` makes it impossible to audit or reproduce what is running. A rollback to `:latest` after a bad push would roll forward to the same broken image. We need reproducible, auditable deployments.

## Decision

Every CD deployment uses the commit SHA as the image tag (e.g., `ghcr.io/includeduck/scd-civicpulse/backend:abc1234`). `:latest` is pushed for convenience but **never deployed**. The CD pipeline exposes the image digest as a workflow output.

## Consequences

- **Positive:** Any deployed version can be exactly reproduced by its SHA.
- **Positive:** Rollback is `kubectl set image ... backend=ghcr.io/.../backend:<previous-sha>`.
- **Negative:** Requires the CD pipeline to correctly pass the SHA through all job steps.
