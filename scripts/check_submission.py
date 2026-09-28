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


# ---------------------------------------------------------------------------
# Check: required top-level and docs files
# ---------------------------------------------------------------------------

_REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    ".env.example",
    ".gitignore",
    ".mailmap",
    "compose.yaml",
    "compose.prod.yaml",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "backend/pyproject.toml",
    "frontend/package.json",
    "docs/TRIAGE.md",
    "docs/RUNBOOK.md",
    "docs/ENGINEERING-NOTES.md",
    "docs/TESTING.md",
    "docs/AI-USAGE.md",
    "docs/SECURITY-AUDIT.md",
    "docs/adr/0001-provider-interface.md",
    "docs/adr/0002-frontend-runtime-config.md",
    "docs/adr/0003-deploy-by-sha.md",
    "docs/adr/0004-pii-and-data-governance.md",
]


def check_required_files() -> None:
    print("\n── Required files ──")
    for path in _REQUIRED_FILES:
        check_file(path)


# ---------------------------------------------------------------------------
# Check: .env not tracked; no obvious secrets in source
# ---------------------------------------------------------------------------

_SECRET_PATTERN = re.compile(
    r"""(
        (?i:password|secret|api[_-]?key|private[_-]?key|token)\s*=\s*['"]?[A-Za-z0-9+/]{16,}
        | sk-[A-Za-z0-9]{20,}          # OpenAI / Groq style keys
        | gsk_[A-Za-z0-9]{20,}         # Groq
        | -----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY
    )""",
    re.VERBOSE,
)

# Files that legitimately document secret *names* (not values).
_SECRET_ALLOWLIST = {
    ".env.example",
    "docs/AI-USAGE.md",
    "docs/TRIAGE.md",
    "scripts/check_submission.py",
}

# Extensions to scan.
_TEXT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sh", ".md",
}

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".ruff_cache", ".venv"}


def _tracked_files() -> list[Path]:
    """All text files under ROOT, skipping binary and ignored dirs."""
    results: list[Path] = []
    for p in ROOT.rglob("*"):
        if any(d in p.parts for d in _SKIP_DIRS):
            continue
        if p.is_file() and p.suffix in _TEXT_EXTS:
            results.append(p)
    return results


def check_env_and_secrets() -> None:
    print("\n── .env and secrets ──")
    # .env must not be a tracked file
    if exists(".env"):
        fail(".env is present — must not be committed")
    else:
        ok(".env absent from repository")

    # Scan for accidental secret values
    found_secrets = False
    for p in _tracked_files():
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel in _SECRET_ALLOWLIST:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _SECRET_PATTERN.search(content):
            fail(f"possible secret in {rel}")
            found_secrets = True
    if not found_secrets:
        ok("no obvious secret values in source files")
