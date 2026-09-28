"""Global exception handlers for CivicPulse API.

Maps domain exceptions and common HTTP error conditions to consistent
JSON error bodies. All error responses follow the shape:

  {"detail": "<message>", "code": "<machine_readable_code>"}

or for validation errors:

  {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}

Handlers are registered in app/main.py via app.add_exception_handler().
"""

from __future__ import annotations

import logging

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class CivicPulseError(Exception):
    """Base class for domain errors. Subclasses carry an HTTP status code."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(CivicPulseError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(CivicPulseError):
    """Raised when a state-machine transition is not allowed (→ 409)."""

    status_code = status.HTTP_409_CONFLICT
    code = "invalid_transition"


class RateLimitError(CivicPulseError):
    """Raised when a client exceeds the rate limit (→ 429)."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"

    def __init__(self, detail: str, retry_after: int = 60) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


class ValidationFailedError(CivicPulseError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "validation_failed"


# ── Handlers ────────────────────────────────────────────────────────────────


async def civicpulse_error_handler(request: Request, exc: CivicPulseError) -> JSONResponse:
    """Handle all CivicPulse domain errors."""
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitError):
        headers["Retry-After"] = str(exc.retry_after)
    else:
        logger.info("Domain error: %s — %s", exc.code, exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,  # noqa: ARG001
    exc: RequestValidationError,
) -> JSONResponse:
    """Return 400 with field-level validation errors.

    The assignment contract (plan §1.1) requires 400 for invalid input, so we
    override FastAPI's default 422.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
    )


async def pydantic_validation_handler(
    request: Request,  # noqa: ARG001
    exc: ValidationError,
) -> JSONResponse:
    """Handle Pydantic v2 ValidationError raised inside business logic (→ 400)."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all for unexpected errors. Log the full traceback."""
    logger.exception(
        "Unhandled exception: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred.", "code": "internal_error"},
    )
