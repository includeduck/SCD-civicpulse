"""Stats cache interface (assignment §2.4, Job 1).

Phase 3 ships ``NoOpStatsCache`` (always a MISS) so services and routes are
wired for caching now; Phase 6 adds the Redis implementation behind the same
interface.
"""

from __future__ import annotations

from typing import Any, Protocol


class StatsCache(Protocol):
    async def get(self) -> dict[str, Any] | None:
        """Return the cached stats payload, or None on a miss."""
        ...

    async def set(self, value: dict[str, Any]) -> None:
        """Store the stats payload with the configured TTL."""
        ...

    async def invalidate(self) -> None:
        """Drop the cached payload after a write."""
        ...


class NoOpStatsCache:
    """Caches nothing: every read is a MISS."""

    async def get(self) -> dict[str, Any] | None:
        return None

    async def set(self, value: dict[str, Any]) -> None:
        return None

    async def invalidate(self) -> None:
        return None
