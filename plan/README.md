# CivicPulse — Project Implementation Plan Index

> **Source of Truth:** [Software Construction and Design -  Assignment 1.pdf](Software%20Construction%20and%20Design%20-%20%20Assignment%201.pdf)  
> **Course:** CS4032 — Software Construction and Design  
> **Team:** 2 Members | **Total Marks:** 150 Marks | **Duration:** 2 Weeks

---

## Overview

To make navigation easy and allow parallel collaboration between team members, the full implementation plan has been modularized into domain-specific guidebooks. The original, unedited single document is also preserved in this directory.

---

## Plan Directory Structure

```text
plan/
├── Software Construction and Design -  Assignment 1.pdf   # Official course assignment brief (26 pages)
├── README.md                                              # This index & navigation guide
├── FULL_CivicPulse_ImplementationPlan.md                  # Complete single-document source of truth (3,783 lines)
│
├── 00_MISSION_ARCHITECTURE_AND_WORKFLOW.md               # Mission, Non-negotiable requirements, Target layout, Phases 0
├── 01_BACKEND_AND_DATABASE.md                             # Phase 1 (Foundation), Phase 2 (DB & Repos), Phase 3 (API & Domain)
├── 02_AI_TRIAGE_AND_REDIS.md                              # Phase 4 (Triage Abstraction), Phase 5 (LLM/Ollama/Fallback), Phase 6 (Redis Cache & Rate Limit)
├── 03_OBSERVABILITY_AND_FRONTEND.md                       # Phase 7 (Observability/Metrics/Shutdown), Phase 8 (React 18 + Vite UI)
├── 04_DOCKER_COMPOSE_AND_TESTING.md                       # Phase 9 (Multi-stage Docker & Compose Isolation), Phase 10 (Automated Tests)
├── 05_KUBERNETES_AND_SCALING.md                           # Phase 11 (K8s Base & Dev Overlay), Phase 12 (Probes, HPA, VPA, k6 Load Tests)
├── 06_CICD_AND_DEPLOYMENT.md                              # Phase 13 (GitHub Actions CI), Phase 14 (CD, GHCR, SHA deploy, Rollback)
├── 07_DOCUMENTATION_AND_EVIDENCE.md                       # Phase 15 (ADRs, Runbook, Engineering Notes Q1-Q8, Evidence Checklist)
├── 08_AGENT_AND_TEAM_EXECUTION.md                         # Team roles, Agent Task Format, Agent Breakdown, Graphify Knowledge Graph
└── 09_VERIFICATION_AUDIT_AND_RUBRIC.md                    # End-to-end verification, Deduction audit, Rubric matrix, Final audit prompt
```

---

## Detailed File Guide

| File | Focus / Contents | Primary Owner |
|---|---|---|
| [**`00_MISSION_ARCHITECTURE_AND_WORKFLOW.md`**](00_MISSION_ARCHITECTURE_AND_WORKFLOW.md) | High-level mission, Section 1 hard requirements, 4-layer backend layout, Phase 0 Git workflow, Dependency order graph. | Both Members |
| [**`01_BACKEND_AND_DATABASE.md`**](01_BACKEND_AND_DATABASE.md) | **Phases 1–3:** FastAPI skeleton, Pydantic v2, PostgreSQL 16 + Alembic, 30+ Urdu-English seed rows, CRUD repositories, status machine 409 errors. | Member 1 |
| [**`02_AI_TRIAGE_AND_REDIS.md`**](02_AI_TRIAGE_AND_REDIS.md) | **Phases 4–6:** `TriageProvider` protocol, Groq/Ollama/Rules/Simulated, 10s timeout, fallback to `rules:fallback`, Redis 24h AI cache, Redis 30s stats cache, IP distributed rate limiter. | Member 1 |
| [**`03_OBSERVABILITY_AND_FRONTEND.md`**](03_OBSERVABILITY_AND_FRONTEND.md) | **Phases 7–8:** JSON stdout logging, `X-Request-ID`, `/metrics`, graceful SIGTERM; React 18 frontend (Submit, Dashboard, Stats), Nginx reverse proxy. | Member 2 |
| [**`04_DOCKER_COMPOSE_AND_TESTING.md`**](04_DOCKER_COMPOSE_AND_TESTING.md) | **Phases 9–10:** Multi-stage Dockerfiles (`python:3.12-slim`, `node:22-alpine` + `nginx:1.27-alpine`), Compose two-network isolation (`edge` vs `internal`), Pytest & Vitest test suites. | Member 2 |
| [**`05_KUBERNETES_AND_SCALING.md`**](05_KUBERNETES_AND_SCALING.md) | **Phases 11–12:** Kustomize `base` & `dev`, Deployments (>=2 replicas), StatefulSet, Redis PVC, Ingress, HPA (60% CPU), k6 load testing, VPA recommendations. | Member 2 |
| [**`06_CICD_AND_DEPLOYMENT.md`**](06_CICD_AND_DEPLOYMENT.md) | **Phases 13–14:** `ci.yml` (lints, types, tests, Trivy, kubeconform, integration), `cd.yml` (GHCR push, Syft SBOM, immutable commit SHA deploy, rollback). | Member 2 |
| [**`07_DOCUMENTATION_AND_EVIDENCE.md`**](07_DOCUMENTATION_AND_EVIDENCE.md) | **Phase 15:** ADRs 0001–0004, `TRIAGE.md`, `RUNBOOK.md`, `ENGINEERING-NOTES.md` (exact answers for Q1–Q8), submission checker, evidence checklist. | Both Members |
| [**`08_AGENT_AND_TEAM_EXECUTION.md`**](08_AGENT_AND_TEAM_EXECUTION.md) | Agent task prompt patterns, work breakdown (Agents A–F), merge conflict procedure, Graphify knowledge graph instructions. | Both Members |
| [**`09_VERIFICATION_AUDIT_AND_RUBRIC.md`**](09_VERIFICATION_AUDIT_AND_RUBRIC.md) | Final local & K8s verification commands, deduction audit checklist, 150-mark rubric mapping, emergency triage priorities. | Both Members |

---

## 2-Person Team Division of Responsibilities

Per **Section 28** of the implementation plan:

### Member 1: Backend, AI, Data & Persistences
- **Focus:** Backend service, database models & repositories, AI triage providers & fallbacks, Redis caching & distributed rate limiter.
- **Key Modules:** [`01_BACKEND_AND_DATABASE.md`](01_BACKEND_AND_DATABASE.md), [`02_AI_TRIAGE_AND_REDIS.md`](02_AI_TRIAGE_AND_REDIS.md), ADR 0001, ADR 0004.
- **Target Branches:** `feature/backend-foundation`, `feature/ai-triage`.

### Member 2: Frontend, DevOps, Kubernetes & CI/CD
- **Focus:** React frontend & Nginx proxy, Docker images & Compose networks, Kubernetes manifests & Kustomize, HPA/VPA autoscaling, GitHub Actions CI/CD pipelines.
- **Key Modules:** [`03_OBSERVABILITY_AND_FRONTEND.md`](03_OBSERVABILITY_AND_FRONTEND.md), [`04_DOCKER_COMPOSE_AND_TESTING.md`](04_DOCKER_COMPOSE_AND_TESTING.md), [`05_KUBERNETES_AND_SCALING.md`](05_KUBERNETES_AND_SCALING.md), [`06_CICD_AND_DEPLOYMENT.md`](06_CICD_AND_DEPLOYMENT.md), ADR 0002, ADR 0003.
- **Target Branches:** `feature/frontend`, `feature/docker`, `feature/kubernetes`, `feature/cicd`.
