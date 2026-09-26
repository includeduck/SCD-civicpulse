"""Rate limiter interface (assignment §2.4, Job 2).

Phase 3 ships ``AllowAllRateLimiter``; Phase 6 adds the distributed Redis
limiter behind the same interface. It must never be an in-process counter:
with N replicas that would allow N times the traffic.
"""

from __future__ import annotations

from typing import Protocol


class RateLimiter(Protocol):
    async def check(self, client_ip: str) -> None:
        """Return if the request is allowed; raise ``RateLimitError`` otherwise."""
        ...


class AllowAllRateLimiter:
    """Permits every request."""

    async def check(self, client_ip: str) -> None:  # noqa: ARG002
        return None
