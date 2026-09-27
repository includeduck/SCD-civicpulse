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
| **Antigravity** (Google DeepMind) | team | Phase 0, and likely Phases 1–2 (*team to confirm*) | Repository scaffold, docs stubs, initial FastAPI skeleton, model, migration and seed |
| **Claude Code** (Anthropic, Claude Opus model), desktop app | repository owner | 2026-09-26 onwards | Plan review, defect fixes, Phases 3–12 implementation, tests, docs, GitHub Issues and PR descriptions, verification runs |
| *AI assistant used to draft PR reviews* | reviewer | from PR #15 | *Team to name the tool.* The review bodies on #15, #17, #19, #21 are AI-generated reports; they link to local `file:///` paths |

---

## What AI wrote or shaped

| Area | AI contribution | Human direction / review |
|------|-----------------|--------------------------|
| Phase 0 scaffold | `.gitignore`, `.env.example`, README skeleton, docs stubs (Antigravity) | Reviewed for correctness |
| Phases 1–2 (original) | FastAPI skeleton, config, logging, middleware, model, Alembic migration, repositories, seed (*team to confirm tool*) | *Team to fill in* |
| Implementation plan | Claude Code reviewed `CivicPulse_ImplementationPlan.md` and rewrote Phase 3 (§8); fixed several other sections; moved Graphify to `docs/GRAPHIFY.md` | Owner asked for the review, and for gaps to be fixed before implementation |
| Phase 1–2 defect fixes (#9) | Found and fixed: `.env.example` crashing startup, commit-after-response, lost request ids on 500s, racing status updates, unstable pagination, `reporter_contact` exposure | Owner asked for "critical mistakes in the current implementation" to be fixed first |
| Phases 3–7 backend (#11, #17, #19, #21, #23) | Wrote essentially all code and tests: services, state machine, triage providers (rules, simulated, Groq, Ollama), `TriageService` (timeout/retry/fallback/cache), Redis stats cache, distributed rate limiter, observability, graceful shutdown | Owner set the order (sequential phases), approved each Issue/PR, and chose the provider strategy (below). Partner reviewed and merged each PR |
| Phase 8 frontend | Wrote the React app (submit, dashboard, stats views, error boundary), the OpenAPI export and contract test, the typed client, the Vitest tests, the nginx template and the frontend Dockerfile; updated ADR 0002 | Owner asked for Phase 8 after #23/#25 merged. *Team to review the UI wording and the tests, and to be able to explain the runtime-config choice (ADR 0002) at the viva* |
| Phase 9 Docker and Compose | Wrote `compose.yaml` and `compose.prod.yaml` (two networks, three volumes, healthchecks, the one-shot `migrate` and `ollama-pull` services), reworked both Dockerfiles (digest pins, no compiler or curl, root-owned source), removed two unused dependencies, and captured the network-isolation evidence and image and context sizes | Owner asked for Phase 9 after #27 merged, and had earlier chosen Ollama as the practical provider. *Team to review; the live Ollama run surfaced an in-enum prompt-injection weakness for the team to decide on (TRIAGE.md)* |
| Prompt-injection guard | Found the in-enum injection weakness during the live Ollama run, wrote `injection.py` (detection before the model), the service change and `test_triage_injection.py`, and re-verified live | Owner chose to fix it (rather than only document it) after reviewing the Phase 9 findings. *Team to review the pattern list and its false-positive trade-off* |
| Phase 10 test strategy | Audited the suites against the brief and plan, wrote `docs/TESTING.md` (layers, determinism, requirement-to-test traceability), added coverage floors and random test order, replaced the one real-sleep test with an injected sleep, added frontend boundary and error-state tests, and stress-ran both suites | Owner asked for Phase 10. *Team to be ready to explain the determinism table at the viva* |
| Phase 11 Kubernetes | Wrote the Kustomize base and overlays, the k3d cluster config, the Traefik config, `wait_for_schema.py`, `scripts/k8s-up.sh` and `scripts/zero_downtime_check.py`; found and fixed a migrate-Job race and the per-node client-IP rate-limit bug; captured the evidence files | Owner chose k3d and approved installing it. *Team to be able to explain StatefulSet vs Deployment and liveness vs readiness at the viva (ENGINEERING-NOTES, "Kubernetes decisions")* |
| Phase 12 autoscaling | Wrote the k6 script (arrival-rate), the HPA sampler, the run and analysis scripts (lag table and SVG chart), the VPA object and pinned recommender install; ran both load tests, applied the VPA target, and wrote Q5 and Q6 from the measurements | Owner asked for Phase 12. *Team to be able to explain the lag breakdown and the HPA/VPA conflict in their own words at the viva* |
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

*Team to add:* anything you changed in AI output by hand, suggestions you rejected, and why.

---

## Known limitations of the AI-written parts

The team should be able to explain these at the viva:

- Groq and Ollama were tested only against scripted HTTP responses; neither has been run against a live model yet (TRIAGE.md, "Measured hit rate").
- The ADR 0004 data-retention TODO requires a person to read the provider's live policy page; the AI deliberately didn't write it from memory.
- Engineering-notes **Q8 (the failure story)** must be a real incident told in the team's own words.

---

## Reflection

*To be written by the team in Phase 15: what AI helped with most, where it was wrong (e.g. the async interface, the flaky test it wrote and later found), and what you verified yourselves.*
