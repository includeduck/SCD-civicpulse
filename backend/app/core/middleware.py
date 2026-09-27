"""Request-ID middleware for CivicPulse.

Every HTTP request gets a unique request_id. The middleware:

1. Reads X-Request-ID from the incoming request if it is a safe, bounded token.
2. Otherwise generates a new UUID4.
3. Stores the value in the request_id_var ContextVar so that all log records
   emitted during this request include it automatically.
4. Echoes the value back in the X-Request-ID response header — including on
   unhandled 500s, which would otherwise be rendered by Starlette's outermost
   error middleware after this context has been reset.
"""

from __future__ import annotations

import json
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import generic_exception_handler
from app.core.logging import get_logger, request_id_var
from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY

# Client-supplied IDs end up in logs and headers; reject anything that could
# forge log fields or bloat log lines.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign or propagate X-Request-ID for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Honour a supplied ID (useful for distributed tracing); fall back to UUID.
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied if _VALID_REQUEST_ID.match(supplied) else str(uuid.uuid4())

        # Make the ID available to all log calls within this request context.
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 — log and render inside the request context
            response = await generic_exception_handler(request, exc)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


logger = get_logger(__name__)


def route_template(scope: Scope) -> str:
    """The matched route's full template, e.g. "/api/complaints/{complaint_id}".

    FastAPI (0.14x) wraps included routers, so the matched route's ``path`` is
    relative to its router ("/complaints/{complaint_id}") and the outer
    prefixes are missing. Fill the template with this request's path
    parameters, and whatever comes before that in the real path is the prefix.
    Nothing is hard-coded, and a route that already carries its full path
    comes back unchanged.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not template:
        return "unmatched"
    path = scope.get("path", "")
    try:
        concrete = getattr(route, "path_format", template).format(**scope.get("path_params", {}))
    except (KeyError, IndexError, ValueError):
        return template
    if concrete and path.endswith(concrete):
        return path[: len(path) - len(concrete)] + template
    return template


class RequestMetricsMiddleware:
    """Count, time and log every HTTP request (pure ASGI, so it sees the final status).

    Labels use the route *template* ("/api/complaints/{complaint_id}"), never the
    concrete path: one series per endpoint, not one per complaint id.
    Runs inside RequestIDMiddleware, so the log line carries the request_id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500  # if the app raises before responding

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            endpoint = route_template(scope)
            method = scope["method"]
            REQUEST_COUNT.labels(
                method=method, endpoint=endpoint, status_code=str(status_code)
            ).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
            logger.info(
                "request_completed",
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                duration_ms=round(elapsed * 1000, 1),
            )


class BodySizeLimitMiddleware:
    """Refuse request bodies over ``max_bytes`` with 413, before anything reads them.

    FastAPI reads a body into memory before validating it, and the Ingress
    sends /api/ straight to the backend (nginx's 64 KB cap only covers the
    frontend path). One huge POST could push a pod past its memory limit.
    A declared Content-Length is checked up front; a streamed (chunked) body
    is counted as it arrives and cut off at the limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        too_large = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    return {"type": "http.disconnect"}  # the app stops reading
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if too_large and not response_started:
                return  # we answer with 413 instead
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not too_large:
                raise
        if too_large and not response_started:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "detail": f"Request body too large (limit {self.max_bytes} bytes).",
                "code": "payload_too_large",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
