"""Request-ID middleware for CivicPulse.

Every HTTP request gets a unique request_id. The middleware:

1. Reads X-Request-ID from the incoming request (if present and non-empty).
2. Otherwise generates a new UUID4.
3. Stores the value in the request_id_var ContextVar so that all log records
   emitted during this request include it automatically.
4. Echoes the value back in the X-Request-ID response header.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign or propagate X-Request-ID for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Honour a supplied ID (useful for distributed tracing); fall back to UUID.
        request_id = request.headers.get("X-Request-ID", "").strip() or str(uuid.uuid4())

        # Make the ID available to all log calls within this request context.
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
