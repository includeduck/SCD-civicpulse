# Security Audit (before CD, 2026-09-28)

A deliberate pause before Phase 14 (CD), the step where mistakes start reaching real deployments. The previous day had shown that the worst problems were the ones that *looked* green, so this audit used tools and checked what they actually did, rather than trusting colours.

## Method

| Area | Tool / method | Scope |
|---|---|---|
| Dependency CVEs, images | Trivy 0.74.0 `image` (also CI's `scan` job) | Both runtime images |
| Dependency CVEs, tracked tree | Trivy `fs` (vuln, secret, misconfig) | Everything in Git (`git archive`), incl. `package-lock.json` |
| Dependency CVEs, dev tools | Trivy **`rootfs`** on the backend virtualenv | pytest & co., which never reach the image. (`fs` mode reported "not scanned" here; its exit 0 was meaningless.) |
| Secrets, full history | Pattern search over `git log --all -p` (89 commits) | Groq/OpenAI/AWS/GitHub tokens, private keys, password assignments |
| Misconfiguration | Trivy `misconfig` | Dockerfiles, Compose, Kubernetes manifests |
| "Green but wrong" | Ignored-file audit, doc references, exec bits, a clean clone | What's in Git vs. what the code expects |
| Application | Code review of the request path | Body size, auth, XSS, what the Ingress exposes |

Everything was verified on the running k3d cluster and the Compose stack after the fixes.

## Findings and what was done

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | **Image names meant Docker Hub, where the `civicpulse` account belongs to someone else.** `civicpulse/backend:dev` resolves to `docker.io/civicpulse/backend`. The account exists (repositories don't, yet), so a missing k3d import or a `docker compose pull` would have pulled a stranger's image (dependency confusion). | High | **Fixed.** All our images are named under our own namespace, `ghcr.io/includeduck/scd-civicpulse/*`. Compose uses `pull_policy: build`; the dev overlay uses `imagePullPolicy: Never`. Verified on the cluster: `pull=Never`, pods healthy. |
| 2 | **No request-size limit on the API in Kubernetes.** nginx caps bodies at 64 KB, but the Ingress sends `/api/` straight to the backend, and FastAPI buffers a whole body before validating it. One large POST could OOM-kill a pod. | High | **Fixed.** `BodySizeLimitMiddleware` (64 KiB, `MAX_REQUEST_BODY_BYTES`) rejects a declared oversize body before reading it, and cuts off streamed (chunked) bodies as they arrive; tests cover both. Verified through the Ingress: a 1 MB POST was rejected with 413 in **0.2 ms** (backend log), while normal complaints return 201. |
| 3 | **pytest 8.3.4** (CVE-2025-71176). | Medium (dev only) | **Fixed.** pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0, pytest-randomly 5.0.0; the full suite passes. |
| 4 | **Postgres without a read-only root filesystem** (Trivy KSV-0014). | High (hardening) | **Fixed.** `readOnlyRootFilesystem: true`, with `emptyDir`s for the socket directory and `/tmp`. Verified: `touch /probe` → "Read-only file system"; Postgres serving; all 43 complaints intact after the restart. |
| 5 | **A Kubernetes API token was mounted into every pod**, and none of them use the API. | Medium (hardening) | **Fixed.** `automountServiceAccountToken: false` on all five pod specs. Verified: no token in the Postgres or backend pods. |
| 6 | **Leftover packages in the local virtualenv** (python-jose, python-multipart, ecdsa, msgpack): removed from `pyproject.toml` in Phase 9, but `pip install` never uninstalls. | Info (local only) | **Cleaned.** CI and the images build from scratch and never had them. |
| 7 | *(From the CI work the day before.)* The placeholder Secret was never committed; the `manifests` job passed without `pipefail`; Starlette CVEs; Alembic muting the app's loggers. | High | **Fixed on PR #39**; see `docs/evidence/ci-gate.md`. |

## Accepted, with reasons

| Finding | Why it's accepted |
|---|---|
| **The API has no authentication.** Anyone who can reach it can list complaints, **change a complaint's status** (`PATCH /api/complaints/{id}/status`), or **correct triage** (`PATCH /api/complaints/{id}/triage`). | Out of scope for the assignment, which specifies a public intake and an operations dashboard but no user model. Mitigations in place: `reporter_contact` is never returned (ADR 0004). Complaint *submission* is rate-limited per client; operator mutations are **not**. Before any real deployment, the dashboard and the PATCH routes need authentication, e.g. an OIDC-authenticating proxy or Ingress middleware in front of `/api/complaints/*/{status,triage}`. |
| **Oversized bodies through the Ingress get a dropped connection, not a 413 body.** | Uvicorn closes the connection when it answers before reading the body, and Traefik passes that on. The protection itself works (0.2 ms, nothing buffered). The Compose/nginx path returns a clean 413. Fixing the cosmetics would tie the manifests to Traefik-only resources. |
| Trivy KSV-0125 "untrusted registry" on `ghcr.io/includeduck/...` | Trivy only trusts a built-in list of cloud registries. Our images now come from our own namespace (finding 1), and prod pins them to a commit SHA. |
| Trivy KSV-01010 "`LOG_LEVEL` is sensitive" | False positive: a keyword match on a log level. |
| Trivy KSV-0037 HelmChartConfig in `kube-system` | Required by k3s: Traefik's configuration object must live there. |
| Redis has no password | It's reachable only from the backend: `internal: true` in Compose, a NetworkPolicy in Kubernetes. Both verified in `docs/evidence/`. |
| pip's vendored msgpack and the venv's setuptools (local toolchain) | Part of the Python tooling itself, not project dependencies; never in the image. |

## Clean

- **Secrets:** none in the tree, and none in any of the 89 commits of history. The only key-like string is the deliberate fake `gsk_test_SECRET_do_not_log_7f3a`, used to prove keys never reach logs.
- **Images:** 0 fixable HIGH/CRITICAL in both (CI enforces this on every PR).
- **Frontend:** no `dangerouslySetInnerHTML`, `innerHTML` or `eval`; React escapes all rendered text; nginx sends a strict CSP, `X-Frame-Options: DENY` and `nosniff`.
- **Exposure:** the Ingress routes only `/api/` and `/`. `/docs`, `/openapi.json`, `/metrics`, `/health` and `/ready` are not reachable from outside the cluster; `compose.prod.yaml` publishes only the frontend.
- **CI:** `pull_request` (never `pull_request_target`), read-only token, SHA-pinned actions, digest-pinned tools, `pipefail`.
- **npm:** `npm audit` reports 0 vulnerabilities.

## Recommended before a real deployment (not done)

1. Authentication for the dashboard and operator mutation routes (`status` and `triage`).
2. Rate-limit or cache GET endpoints, or rely on the HPA plus an Ingress-level rate limit. Today only `POST /api/complaints` is limited.
3. A dependency-update bot (Dependabot or Renovate) for the pinned images and packages, so pins don't quietly go stale. The Starlette CVEs were exactly that.
