"""Deterministic fake provider for CI (assignment §2.5: "seeded, no network,
configurable failure injection").

Outcomes
--------
Category and priority come from the rule engine, so tests and the Compose
integration job can assert a meaningful category for a given text. Confidence is
derived from a seeded SHA-256 of the input, so it varies across inputs but is
identical on every run. The summary is prefixed ``[simulated]`` so a simulated
result can never be mistaken for a real model's output.

Failure injection
-----------------
``failure_mode`` picks what goes wrong; ``failure_rate`` (0.0–1.0) picks how
often. Whether a given input fails is decided by the same seeded hash, so the
same complaint always fails or always succeeds, with no randomness and no sleeps.

    none          never fails
    timeout       raises TriageTimeoutError        (retryable)
    rate_limited  raises TriageRateLimitedError    (retryable, like HTTP 429)
    server_error  raises TriageServerError         (retryable, like HTTP 5xx)
    bad_request   raises TriageBadRequestError     (never retried, like HTTP 400)
    error         raises TriageError               (generic, not retryable)
    invalid       returns output that fails TriageResult validation
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Literal

from app.providers.triage.base import (
    TriageBadRequestError,
    TriageError,
    TriageRateLimitedError,
    TriageResult,
    TriageServerError,
    TriageTimeoutError,
)
from app.providers.triage.rules import RuleBasedTriage

FailureMode = Literal[
    "none", "timeout", "rate_limited", "server_error", "bad_request", "error", "invalid"
]

_ERRORS: dict[str, type[TriageError]] = {
    "timeout": TriageTimeoutError,
    "rate_limited": TriageRateLimitedError,
    "server_error": TriageServerError,
    "bad_request": TriageBadRequestError,
    "error": TriageError,
}

_SUMMARY_PREFIX = "[simulated] "


class SimulatedTriage:
    name = "simulated"

    def __init__(
        self,
        *,
        seed: int = 42,
        failure_mode: FailureMode = "none",
        failure_rate: float = 1.0,
        latency_ms: int = 0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0.0 and 1.0")
        if failure_mode not in (*_ERRORS, "none", "invalid"):
            raise ValueError(f"unknown failure_mode {failure_mode!r}")
        self.seed = seed
        self.failure_mode = failure_mode
        self.failure_rate = failure_rate
        # Demo-only delay, like a real model's inference time. Runs in the
        # provider's worker thread, so it never blocks the event loop.
        self.latency_ms = latency_ms
        self._sleep = sleep  # injectable, so tests check the delay without waiting for it
        self._rules = RuleBasedTriage()

    def _fraction(self, text: str, location: str, salt: str) -> float:
        """Deterministic value in [0, 1) from the seed and input."""
        digest = hashlib.sha256(f"{self.seed}\x00{salt}\x00{text}\x00{location}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def should_fail(self, text: str, location: str) -> bool:
        if self.failure_mode == "none":
            return False
        return self._fraction(text, location, "fail") < self.failure_rate

    def triage(self, text: str, location: str) -> TriageResult:
        if self.latency_ms:
            self._sleep(self.latency_ms / 1000)
        if self.should_fail(text, location):
            if self.failure_mode == "invalid":
                # What a misbehaving model looks like: out-of-enum category,
                # over-long summary, confidence out of range. Built without
                # validation, exactly as untrusted provider output would arrive.
                return TriageResult.model_construct(
                    category="urgent-maybe",  # type: ignore[arg-type]  # invalid on purpose
                    priority="very high",  # type: ignore[arg-type]  # invalid on purpose
                    summary="x" * 400,
                    confidence=7.0,
                )
            raise _ERRORS[self.failure_mode](f"simulated {self.failure_mode} (seed={self.seed})")

        ruled = self._rules.triage(text, location)
        summary = (_SUMMARY_PREFIX + ruled.summary)[:140]
        confidence = round(0.5 + 0.5 * self._fraction(text, location, "confidence"), 3)
        return TriageResult(
            category=ruled.category,
            priority=ruled.priority,
            summary=summary,
            confidence=min(confidence, 1.0),
        )
