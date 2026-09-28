"""Submission lint for the CivicPulse assignment (brief §5.8).

A mechanical check of deterministic requirements: required files, forbidden
patterns, Dockerfile presence, workflow names, Kustomize overlays, Kubernetes
resource shapes, production Compose constraints, and required documentation.

It is NOT a replacement for tests.  A clean run only means mechanical failures
are absent.

Usage (from repository root)::

    python scripts/check_submission.py

Exit codes: 0 = all checks passed, 1 = one or more FAILs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

_results: list[tuple[str, str, str]] = []  # (status, name, detail)


def _record(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))
    colour = {"PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m"}.get(status, "")
    reset = "\033[0m"
    line = f"  {colour}{status}{reset}  {name}"
    if detail:
        line += f"  — {detail}"
    print(line)


def ok(name: str, detail: str = "") -> None:
    _record("PASS", name, detail)


def fail(name: str, detail: str = "") -> None:
    _record("FAIL", name, detail)


def warn(name: str, detail: str = "") -> None:
    _record("WARN", name, detail)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def read(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def check_file(path: str, label: str | None = None) -> bool:
    label = label or path
    if exists(path):
        ok(f"{label} exists")
        return True
    fail(f"{label} missing")
    return False
