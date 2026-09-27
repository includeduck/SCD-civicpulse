# ADR 0002 — Frontend Runtime Configuration

**Status:** Accepted (implemented in Phase 8)  
**Date:** 2026-09-14, updated 2026-09-27  
**Deciders:** CivicPulse team

---

## Context

A Vite build bakes every `import.meta.env` value into the static JavaScript at build time. If the backend's URL were baked in, each environment (local, CI, the cluster) would need its own frontend image, which defeats build-once-deploy-many (assignment §2.1).

## Options considered

1. **`/config.js` generated at container start.** An entrypoint script writes `window.__ENV__ = {API_URL: ...}` from environment variables, and the app reads it at runtime. The browser then calls the backend directly, so the backend needs CORS and its own public address.
2. **nginx reverse proxy for `/api`.** The browser only ever calls relative `/api/...` paths on the origin that served the page; nginx forwards them to the backend. The frontend code needs no backend URL at all.

## Decision

**Option 2, the nginx `/api` proxy**, with the upstream address itself also set at runtime:

- The app calls relative paths only (`frontend/src/api/client.ts`). There is no `import.meta.env` anywhere in `src/`.
- `frontend/nginx/default.conf.template` contains `proxy_pass ${BACKEND_URL};`. The official nginx image renders templates with `envsubst` when the container starts, substituting only variables that are set, so nginx's own `$host`, `$uri`, etc. are untouched.
- The Dockerfile sets `BACKEND_URL=http://backend:8000` as a default for Compose. Kubernetes (or anything else) overrides it without a rebuild.
- In development, Vite's dev-server proxy plays nginx's role (`vite.config.ts`, `DEV_BACKEND_URL`). It affects `npm run dev` only, not the build.

**Verified on 2026-09-27:** one image (`civicpulse-frontend:dev`) was started twice with different `BACKEND_URL` values (`http://cp-backend:8000` and a second network alias, `http://api-staging:8000`). Both served the app and proxied `/api/stats`, and the rendered configs differed only in the `proxy_pass` line.

## Consequences

- **Positive:** the same image runs in every environment; nothing environment-specific is in the bundle.
- **Positive:** same origin, so the backend needs no CORS for the app and no public address of its own. In Compose and Kubernetes, only the frontend has to be reachable from outside.
- **Positive:** one place for edge concerns: security headers (CSP, `X-Frame-Options`, `nosniff`), gzip, long caching of hashed assets, `no-cache` on `index.html`, and an `X-Request-ID` that is passed through or minted so nginx and backend logs line up.
- **Negative:** nginx's routing must stay in step with the backend's. Only `/api/` is proxied, so `/health`, `/ready`, `/metrics` and `/docs` are deliberately **not** reachable through the frontend; probes and scraping go to the backend directly.
- **Negative:** the backend now sees nginx's address as the TCP peer. The per-client rate limiter keys on the client IP, so the backend must trust `X-Forwarded-For` **from the proxy only** (`FORWARDED_ALLOW_IPS`), or every user shares one rate-limit bucket. Compose and Kubernetes (Phases 9 and 11) must set this to the proxy's network, not `*`, unless the backend is unreachable except through the proxy.
- **Negative:** `proxy_read_timeout` (60 s) must stay above the backend's worst-case triage time (timeout + one retry + fallback, about 21 s with the defaults), or slow triage would surface as a 504 even though the complaint was stored.
