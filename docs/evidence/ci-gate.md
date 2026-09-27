# CI gate and branch protection

**Rubric A** ("main protected: no direct push, PR required, CI required, ≥ 1 approval") and **rubric I** ("evidence of a red pipeline blocking a merge, then green").

## Branch protection

Ruleset **23347090** applies to both `dev` and `main`, and its bypass list is **empty**, so it applies to repository admins too:

- **Pull request required**, with at least **1 approval**; stale approvals are dismissed when new commits are pushed.
- **Status checks required**, all nine CI jobs: `lint-and-type`, `test-backend`, `test-frontend`, `build (backend)`, `build (frontend)`, `scan (backend)`, `scan (frontend)`, `manifests`, `integration`.
- **Force pushes blocked** and **branch deletion restricted**.

Evidence:

- [`branch-protection.png`](branch-protection.png): the ruleset page, showing the targets, the empty bypass list and the pull-request rule.
- [`branch-protection-ruleset.json`](branch-protection-ruleset.json): the ruleset as returned by `gh api repos/includeduck/SCD-civicpulse/rulesets/23347090`, including the required checks.

## Red → blocked → green, on PR #39 (2026-09-27)

1. **Commit `1e19a97`** added `backend/tests/test_ci_gate_demo.py`, a deliberately failing test (`assert 1 + 1 == 3`). `test-backend` failed. The other 266 tests, including the PostgreSQL ones, passed.
   [`ci-gate-red.png`](ci-gate-red.png): "1 failing, 8 successful checks", `test-backend` marked **Required**, **Merging is blocked**.
2. **Commit `18e111c`** removed the test.
   [`ci-gate-green.png`](ci-gate-green.png): "All checks have passed, 9 successful checks", each marked Required. Merging stays blocked by the other gate, the required approving review.

The same pipeline also blocked two *real* problems before this demonstration, both fixed on the same PR:

- **`scan (backend)` failed:** Starlette 0.41.3 had three HIGH CVEs, fixed by upgrading to FastAPI 0.141.1 / Starlette 1.7.0 (`06ffd46`).
- **`test-backend` failed:** random test order exposed Alembic's `fileConfig` muting the app's loggers (`ced199b`).
