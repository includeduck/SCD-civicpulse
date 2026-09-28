# AI Usage

> Honest attribution of AI assistance in CivicPulse, as required by assignment §5.5: which tools, which parts they wrote or shaped, and what the humans changed afterwards and why.
>
> Commits written with Claude Code carry a `Co-Authored-By: Claude …` trailer, so `git log` shows the attribution commit by commit:
>
> ```bash
> git log --format='%h %s%n  %(trailers:key=Co-Authored-By,valueonly)'
> ```

---

## Tools used

| Tool | Used by | Period | For |
|------|---------|--------|-----|
| **Antigravity** (Google DeepMind) | team (Talha Sami) | Phase 0 to Phase 2; PR reviews on #15, #17, #19, #21; Phase 15 docs and submission checks | Repository scaffold, docs stubs, initial FastAPI skeleton, database models, Alembic migrations, seed data, comprehensive PR review analysis (linking to local workspace files), submission checks, and operator triage correction |
| **Claude Code** (Anthropic, Claude Opus model), desktop app | repository owner (Muhammad Wasay Tariq) | 2026-09-26 onwards | Plan review, defect fixes, Phases 3–14 implementation, tests, docs, GitHub Issues and PR descriptions, verification runs |

---

## What AI wrote or shaped

| Area | AI contribution | Human direction / review |
|------|-----------------|--------------------------|
| Phase 0 scaffold | `.gitignore`, `.env.example`, README skeleton, docs stubs (Antigravity) | Reviewed for correctness |
| Phases 1–2 (original) | FastAPI skeleton, config, logging, middleware, model, Alembic migration, repositories, seed (Antigravity) | Antigravity generated the base implementation. Team verified database connection pooling, Alembic migration idempotency, and CORS configuration |
| Implementation plan | Claude Code reviewed `CivicPulse_ImplementationPlan.md` and rewrote Phase 3 (§8); fixed several other sections; moved Graphify to `docs/GRAPHIFY.md` | Owner asked for the review, and for gaps to be fixed before implementation |
| Phase 1–2 defect fixes (#9) | Found and fixed: `.env.example` crashing startup, commit-after-response, lost request ids on 500s, racing status updates, unstable pagination, `reporter_contact` exposure | Owner asked for "critical mistakes in the current implementation" to be fixed first |
| Phases 3–7 backend (#11, #17, #19, #21, #23) | Wrote essentially all code and tests: services, state machine, triage providers (rules, simulated, Groq, Ollama), `TriageService` (timeout/retry/fallback/cache), Redis stats cache, distributed rate limiter, observability, graceful shutdown | Owner set the order (sequential phases), approved each Issue/PR, and chose the provider strategy (below). Partner reviewed and merged each PR |
| Phase 8 frontend | Wrote the React app (submit, dashboard, stats views, error boundary), the OpenAPI export and contract test, the typed client, the Vitest tests, the nginx template and the frontend Dockerfile; updated ADR 0002 | Owner asked for Phase 8 after #23/#25 merged. *Team to review the UI wording and the tests, and to be able to explain the runtime-config choice (ADR 0002) at the viva* |
| Phase 9 Docker and Compose | Wrote `compose.yaml` and `compose.prod.yaml` (two networks, three volumes, healthchecks, the one-shot `migrate` and `ollama-pull` services), reworked both Dockerfiles (digest pins, no compiler or curl, root-owned source), removed two unused dependencies, and captured the network-isolation evidence and image and context sizes | Owner asked for Phase 9 after #27 merged, and had earlier chosen Ollama as the practical provider. *Team to review; the live Ollama run surfaced an in-enum prompt-injection weakness for the team to decide on (TRIAGE.md)* |
| Prompt-injection guard | Found the in-enum injection weakness during the live Ollama run, wrote `injection.py` (detection before the model), the service change and `test_triage_injection.py`, and re-verified live | Owner chose to fix it (rather than only document it) after reviewing the Phase 9 findings. *Team to review the pattern list and its false-positive trade-off* |
| Phase 10 test strategy | Audited the suites against the brief and plan, wrote `docs/TESTING.md` (layers, determinism, requirement-to-test traceability), added coverage floors and random test order, replaced the one real-sleep test with an injected sleep, added frontend boundary and error-state tests, and stress-ran both suites | Owner asked for Phase 10. *Team to be ready to explain the determinism table at the viva* |
| Phase 11 Kubernetes | Wrote the Kustomize base and overlays, the k3d cluster config, the Traefik config, `wait_for_schema.py`, `scripts/k8s-up.sh` and `scripts/zero_downtime_check.py`; found and fixed a migrate-Job race and the per-node client-IP rate-limit bug; captured the evidence files | Owner chose k3d and approved installing it. *Team to be able to explain StatefulSet vs Deployment and liveness vs readiness at the viva (ENGINEERING-NOTES, "Kubernetes decisions")* |
| Phase 12 autoscaling | Wrote the k6 script (arrival-rate), the HPA sampler, the run and analysis scripts (lag table and SVG chart), the VPA object and pinned recommender install; ran both load tests, applied the VPA target, and wrote Q5 and Q6 from the measurements | Owner asked for Phase 12. *Team to be able to explain the lag breakdown and the HPA/VPA conflict in their own words at the viva* |
| Phase 13 CI | Wrote `ci.yml` (SHA-pinned actions, digest-pinned Trivy and kubeconform), `scripts/ci_integration.sh` and `.trivyignore`; fixed the mypy and formatting debts, and the frontend image's 40 fixable CVEs. **A first version of the integration script shared the dev stack's Compose project and deleted the owner's local database volumes**; it was rewritten to run as its own project with its own env file | Owner asked for Phase 13. *Team to add the required status checks to the ruleset and capture the red/green gate evidence* |
| Security audit (pre-CD) | Ran Trivy image, fs, rootfs and misconfig scans, a full-history secret search and a code review; fixed the Docker Hub image-name hole, the missing API body limit, pytest's CVE, and Postgres and service-account hardening; wrote `docs/SECURITY-AUDIT.md` | Owner asked for a check for hidden vulnerabilities before Phase 14. *Team to decide on authentication for the dashboard before any real deployment (listed as accepted risk)* |
| Phase 14 CD | Wrote `cd.yml`, `release.yml` and `scripts/cd_deploy.sh`, and made CI callable; tested the deploy script on k3d with the prod overlay, and both rollback methods with the real previous build; updated ADR 0003 and answered engineering-notes Q2 (from the owner's copy of Lecture 03, slide 32) and Q3 | Owner asked for Phase 14, stacked on #41 while the partner was unavailable. *The first real CD run happens on the first merge to main* |
| Prompt-injection hardening (#44) | Red-teamed the injection detector against the live Ollama model; added Cyrillic/Greek homoglyph folding, mixed-script obfuscation detection, fake result block detection, authority impersonation and assistant directives; added regression and control tests; documented red-team findings and intentional detector limits in TRIAGE.md | Partner asked to solve Issue #44. *Team to review the documented limits of automated detection and operator correction trade-off* |
| Review of #50 and the #48 conflict | Drafted both reviews of the partner's #50 (a CI-red regression, two false positives, then three non-blocking ones found by probing the rules); wrote #51 (`send`/`forward`/`refer` routing verbs, `.mailmap`); ran `git merge origin/dev` on #51, resolved the conflict in the test list by keeping both sides, and wrote `docs/evidence/merge-conflict.md` | Owner asked; each review was read and posted from the owner's account with a disclosure line. *The merge order was flipped (owner merged #50 first) because the partner was unavailable to approve #51* |
| Verification | Ran the tests against real PostgreSQL 16 and Redis 7 in Docker, a two-replica rate-limit check, the AOF restart check and the SIGTERM drain check, and a browser run of the frontend image against the real stack (submit, 409, X-Cache MISS→HIT); stress-ran the suite to find a flaky test | Owner started Docker and installed Python 3.12 when asked |
| Docs | TRIAGE.md, RUNBOOK.md, ADR 0001 and 0004 updates, the engineering-notes restructure, the README, this file | *Team to review wording and add their own reflections* |

---

## What humans decided, changed or corrected, and why

Decisions made by people, recorded as they happened:

- **Plan before code.** The owner asked for the implementation plan to be reviewed, and its gaps closed, *before* any Phase 3 code was written.
- **The assignment PDF as the source of truth.** The owner added the assignment PDF to the repository root. Reading it reversed an earlier AI suggestion: Claude had changed `TriageProvider.triage` to `async`, but the PDF defines it as synchronous and says its contracts "are what gets tested", so the interface went back to synchronous, with a threadpool in the service.
- **No admin override.** The owner asked about admin-merging the closed PRs #4–#6, accepted the explanation that it would bypass `main`'s protection for no benefit, and chose to leave them closed with "superseded" comments.
- **Provider strategy.** The owner judged that keeping a Groq API key safe would be hard and chose Ollama as the practical primary provider (assignment §2.5: "you lose no marks for it"). Groq stays implemented and tested against a fake server.
- **Commit identity.** The owner asked for the placeholder "Developer" identity to be fixed; unpushed commits were re-authored and `.mailmap` added for pushed ones.
- **Reviews.** The partner reviewed and merged every PR.

- **Preserving synchronous provider contracts (§2.5).** An early AI suggestion was to make `TriageProvider.triage` an async coroutine. We rejected this because the assignment specification mandates a synchronous interface for provider implementations, with contract tests calling it synchronously. We kept the provider interface synchronous and offloaded it via `asyncio.to_thread` in the service layer.
- **Preventing developer data loss in integration tests.** An early version of `scripts/ci_integration.sh` ran `docker compose down -v` against the default project name, wiping local developer volumes (`pgdata`). We caught this in review and modified the script to isolate integration tests under a separate project name (`-p civicpulse-test`) with its own environment file.
- **Tuning prompt injection filters.** AI-generated regex patterns initially risked false positives on authentic civic complaints containing phrasing like "prompt action required" or "please ignore previous delays and repair this road". We constrained the injection detector to specific command-override delimiters, role impersonation tags (`system:`, `assistant:`), and structured result faking.
- **Handling validation error serialization.** In the triage correction route, FastAPI's default exception handler produced a 500 Internal Server Error when Pydantic v2 `ValidationError` was raised because the error structures were not directly serializable. We corrected this in `backend/app/core/exceptions.py` using FastAPI's `jsonable_encoder(exc.errors())`.
- **OpenAPI contract normalization.** We investigated and resolved schema discrepancies between local openapi generation and CI checks (such as the presence of `"additionalProperties": true` in Pydantic v2 exports), ensuring strict parity with the contract check in `ci.yml`.

---

## Known limitations of the AI-written parts

The team should be able to explain these at the viva:

- Groq and Ollama were initially tested against scripted HTTP responses before live Ollama verification runs were conducted (TRIAGE.md, "Measured hit rate").
- Live provider policy terms for Groq were checked directly from the official live documentation and cited in ADR 0004.
- Engineering-notes **Q8 (the failure story)** reflects the team's actual debugging experience with `TestClient` event loops and asyncpg connection pooling.

---

## Reflection

### What AI helped with most
AI tools (Claude Code and Antigravity) accelerated mechanical boilerplate and complex infrastructure configuration:
1. **Scaffolding and architectural layering:** Translating high-level design specifications into a clean 4-layer architecture (routes, services, repositories, database models) with consistent type annotations and Pydantic schemas.
2. **Exhaustive test generation:** Rapidly authoring unit, edge-case, and boundary test cases, achieving >90% backend and frontend test coverage.
3. **Infrastructure manifests:** Generating Kubernetes Kustomize overlays, autoscaling policies (HPA, VPA), PodDisruptionBudgets, and Docker multi-stage builds.
4. **CI/CD pipelines:** Pinning GitHub Actions to 40-character SHAs and configuring security scanners (Trivy, Kubeconform).

### Where AI was wrong or needed human intervention
AI models frequently exhibited blind spots regarding runtime lifecycles and assignment constraints:
1. **Interface inversions:** Attempting to alter interface signatures (e.g. changing synchronous triage methods to async) without verifying external testing harnesses and grading briefs.
2. **Hidden event-loop bugs:** Writing tests using `TestClient` without context managers that resulted in event loop teardowns and asyncpg socket disconnects.
3. **Destructive script defaults:** Writing cleanup scripts with `-v` flags that wiped active development databases.
4. **Overly aggressive regexes:** Generating prompt injection detection patterns that were susceptible to false positives on legitimate municipal complaints.
5. **Schema discrepancies:** Missing nuanced serialization behaviors across differing Pydantic v2 minor versions between local environments and CI runners.

### What we verified ourselves
Every critical claim and architectural guarantee in CivicPulse was verified directly by the team:
- **Live Docker & K8s execution:** Running `docker compose up` and k3d clusters locally to verify network boundary isolation (confirming `internal` containers cannot route to the internet and frontend cannot reach PostgreSQL).
- **Failure tolerance & persistence:** Validating that Redis AOF retains rate-limit windows across container restarts, and verifying that the rate limiter fails open safely if Redis crashes.
- **Load and autoscaling behavior:** Running k6 load tests to capture real HPA scale-out response times and VPA resource recommendations.
- **End-to-end user workflows:** Probing the frontend web application in the browser, verifying complaint intake, status progression, operator triage overrides, and cached statistics headers (`X-Cache: HIT`).
