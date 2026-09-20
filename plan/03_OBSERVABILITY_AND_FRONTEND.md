# 12. Phase 7 — Observability and Graceful Shutdown

## Logging

JSON stdout.

Example conceptual structure:

```json
{
  "timestamp": "...",
  "level": "INFO",
  "message": "complaint_created",
  "request_id": "...",
  "complaint_id": "..."
}
```

Fallback warning:

```json
{
  "level": "WARNING",
  "message": "triage_fallback",
  "request_id": "...",
  "complaint_id": "...",
  "provider": "...",
  "error_class": "..."
}
```

Never include:

- API key
- authorization token
- unnecessary personal contact information

## Metrics

Expose Prometheus text at `/metrics`.

Minimum metrics:

- request count
- request latency histogram
- triage latency
- fallback counter

Use stable metric names and labels.

Avoid unbounded labels such as complaint ID or request ID.

## Request ID

Middleware:

1. read `X-Request-ID`
2. if absent generate UUID
3. attach to request context
4. include in response header if desired
5. include in every relevant log

## SIGTERM

On shutdown:

1. stop accepting new work
2. allow in-flight requests to finish
3. close DB pool
4. close Redis clients
5. close outbound provider resources if applicable
6. exit cleanly

Test with a running request and termination signal where practical.

---

# 13. Phase 8 — Frontend

## Goal

Build the minimal UI that exercises the backend honestly.

## API client

Prefer generated OpenAPI client or a typed client checked against OpenAPI.

Create:

```text
frontend/src/api/
```

Centralize:

- HTTP calls
- response types
- error parsing

Do not scatter `fetch()` throughout components.

## Submit page

Fields:

```text
Complaint
Location
Contact (optional)
```

Client constraints mirror server constraints:

```text
text: 10–2000
location: 3–200
```

But server remains authoritative.

Flow:

```text
idle
  -> submitting
  -> success
  -> error
```

During AI processing show honest loading:

```text
Analyzing complaint...
```

Success must display:

- category
- priority
- summary
- provider

## Dashboard

Fetch paginated complaints.

Filters:

- category
- priority
- status

Status control must offer actions based on server-supported information or simply allow attempts and correctly display 409 responses. Do not copy the state machine into frontend code.

When backend responds 409:

> Render the server's message rather than replacing it with "Something went wrong."

## Stats

Display:

- category aggregates
- priority aggregates
- `X-Cache`

## Runtime configuration

Preferred approach:

### nginx reverse proxy

Frontend calls:

```text
/api/...
```

nginx proxies `/api` to backend.

Benefits:

- no absolute backend URL
- build-once-deploy-many
- no Vite runtime environment baking
- same frontend image can run in different environments

Document this in ADR 0002.

## Error boundary

Wrap application root.

Display a useful recovery UI.

## Tests

At least 5 meaningful tests:

1. submit form validation
2. loading state
3. successful triage display
4. dashboard 409 rendering
5. stats cache state display

Add more where practical.

---
