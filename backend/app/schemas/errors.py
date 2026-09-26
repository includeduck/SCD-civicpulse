"""Error bodies, declared so OpenAPI (and the typed frontend client) knows them."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: str


class ValidationErrorResponse(BaseModel):
    detail: list[dict[str, Any]]
    code: str


ResponseSpec = dict[int | str, dict[str, Any]]

VALIDATION_ERROR: ResponseSpec = {400: {"model": ValidationErrorResponse, "description": "Invalid input"}}
NOT_FOUND: ResponseSpec = {404: {"model": ErrorResponse, "description": "Complaint not found"}}
INVALID_TRANSITION: ResponseSpec = {409: {"model": ErrorResponse, "description": "Transition not allowed"}}
RATE_LIMITED: ResponseSpec = {429: {"model": ErrorResponse, "description": "Rate limit exceeded"}}
