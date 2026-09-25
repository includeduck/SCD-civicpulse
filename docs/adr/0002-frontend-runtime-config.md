# ADR 0002 — Frontend Runtime Configuration

**Status:** Accepted  
**Date:** 2026-09-14  
**Deciders:** CivicPulse team

---

## Context

The frontend must know the backend API URL at runtime, but this URL can differ between local dev, staging, and production. Baking it into the Vite build would require a separate image per environment.

## Options Considered

1. **`/config.js` generated at container startup** — Nginx entrypoint writes `window.__ENV__` with values from container environment variables.
2. **Nginx `/api` reverse proxy** — Nginx proxies `/api/*` to the backend, so the frontend always calls `/api` (same origin). No absolute URL needed.

## Decision

**Nginx reverse proxy** (Option 2). The frontend Nginx configuration proxies `/api` to `http://backend:8000`. The frontend code uses only relative `/api` paths. No runtime config file is needed.

## Consequences

- **Positive:** No absolute backend URL in the frontend build. Images are environment-agnostic.
- **Positive:** Eliminates CORS issues.
- **Negative:** Nginx config must be kept in sync with backend routing.
