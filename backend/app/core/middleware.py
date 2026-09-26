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

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.exceptions import generic_exception_handler
from app.core.logging import request_id_var

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
