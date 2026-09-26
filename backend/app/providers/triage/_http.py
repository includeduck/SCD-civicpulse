"""Shared HTTP call for LLM providers: one POST, errors mapped to TriageError types.

Provider-specific response shapes stay in llm.py / ollama.py; only transport
failures and status codes are handled here.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.providers.triage.base import (
    TriageBadRequestError,
    TriageError,
    TriageRateLimitedError,
    TriageServerError,
    TriageTimeoutError,
    TriageUnavailableError,
)


def post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    *,
    provider: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST and return the decoded JSON body, or raise a typed TriageError.

    Error messages carry the status code and provider name only, never request
    headers, so the API key cannot end up in an exception or a log line.
    """
    try:
        response = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise TriageTimeoutError(f"{provider}: timed out") from exc
    except httpx.TransportError as exc:
        raise TriageUnavailableError(f"{provider}: {type(exc).__name__}") from exc

    status = response.status_code
    if status == 429:
        raise TriageRateLimitedError(f"{provider}: HTTP 429")
    if status >= 500:
        raise TriageServerError(f"{provider}: HTTP {status}")
    if status >= 400:
        # 400, and also 401/403/404/422: the request itself is wrong; retrying
        # cannot fix it.
        raise TriageBadRequestError(f"{provider}: HTTP {status}")

    try:
        body = response.json()
    except ValueError as exc:
        raise TriageError(f"{provider}: HTTP {status} with a non-JSON body") from exc
    if not isinstance(body, dict):
        raise TriageError(f"{provider}: unexpected response shape")
    return body
