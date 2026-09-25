# Contributing to CivicPulse

> CS4032 Software Construction and Design — Assignment 01

---

## Branch model

```
main          ← protected, merged via PR only, requires 1 approval + CI
dev           ← integration branch
feature/*     ← one branch per feature / phase
```

**Never push directly to `main`.**  
Open a PR from your feature branch → `dev`, then `dev` → `main`.

---

## Commit convention

Every commit message must start with one of:

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature or endpoint |
| `fix:` | Bug fix |
| `test:` | Tests only, no production code |
| `docs:` | Documentation only |
| `refactor:` | Code change with no behaviour change |
| `chore:` | Build, config, tooling, deps |
| `ci:` | GitHub Actions / pipeline changes |
| `build:` | Dockerfile, Compose, image changes |

Examples:
```
feat: add POST /api/complaints endpoint
fix: return 409 on invalid status transition
test: add resilience test for triage fallback
chore: pin postgres image to 16.3
```

---

## Architecture rules (non-negotiable)

- **Routes:** HTTP only. No DB sessions, no business logic.
- **Services:** Business rules only. No HTTP, no SQL.
- **Repositories:** All SQL. No business logic.
- **Providers:** External integrations behind Protocol interfaces.

---

## Before opening a PR

1. `git diff --check` — no trailing whitespace
2. Run phase-specific tests
3. Link a GitHub Issue in the PR body (`Closes #N`)
4. Request a review from your partner

---

## Secrets

**Never** commit `.env`, API keys, passwords, or tokens.  
Use `.env.example` for templates. Real values go in `.env` (gitignored).
