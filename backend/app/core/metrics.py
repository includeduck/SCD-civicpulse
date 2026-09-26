"""Prometheus metrics, defined once and exported at GET /metrics.

Labels are bounded sets (provider labels, error class names, route templates);
never complaint ids or request ids, which would make every series unique.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# HTTP (recorded by middleware in Phase 7).
REQUEST_COUNT = Counter(
    "civicpulse_requests_total",
    "Total HTTP requests handled",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "civicpulse_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

# Triage (assignment §2.2: triage latency and a fallback counter).
TRIAGE_LATENCY = Histogram(
    "civicpulse_triage_duration_seconds",
    "Time to obtain a triage result, including retry, fallback or cache lookup",
    ["triaged_by"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30),
)
TRIAGE_FALLBACKS = Counter(
    "civicpulse_triage_fallbacks_total",
    "Triage requests answered by the rules fallback",
    ["provider", "error_class"],
)
TRIAGE_RETRIES = Counter(
    "civicpulse_triage_retries_total",
    "Provider calls retried after a retryable error",
    ["provider", "error_class"],
)
TRIAGE_CACHE = Counter(
    "civicpulse_triage_cache_total",
    "AI triage cache lookups by result",
    ["result"],
)
