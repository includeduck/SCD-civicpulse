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


# ---------------------------------------------------------------------------
# Check: required GitHub Actions workflows
# ---------------------------------------------------------------------------

_REQUIRED_WORKFLOWS = {
    "ci.yml": "CI (lint, test, build, scan, manifests, integration)",
    "cd.yml": "CD (test → build-push → deploy on main)",
    "release.yml": "Release (semver tags → publish images + GitHub Release)",
}


def check_workflows() -> None:
    print("\n── GitHub Actions workflows ──")
    wf_dir = ROOT / ".github" / "workflows"
    if not wf_dir.is_dir():
        fail(".github/workflows/ directory missing")
        return
    for fname, label in _REQUIRED_WORKFLOWS.items():
        path = wf_dir / fname
        if path.exists():
            ok(f"{fname} present ({label})")
        else:
            fail(f"{fname} missing — {label}")

    # All action pins should use a SHA digest (@abc1234…), not a mutable tag.
    unpinned: list[str] = []
    for path in wf_dir.glob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            # Match "uses: owner/repo@REF" where REF is NOT a 40-hex SHA
            m = re.search(r"uses:\s+\S+@([A-Za-z0-9._-]+)", line)
            if m:
                ref = m.group(1)
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    unpinned.append(f"{path.name}: {line.strip()}")
    if unpinned:
        for u in unpinned:
            warn(f"action not pinned by SHA — {u}")
    else:
        ok("all actions pinned by 40-hex SHA digest")


# ---------------------------------------------------------------------------
# Check: Kustomize overlays exist; no `latest` tag in K8s manifests
# ---------------------------------------------------------------------------

_REQUIRED_OVERLAYS = ["k8s/overlays/dev/kustomization.yaml", "k8s/overlays/prod/kustomization.yaml"]
_REQUIRED_K8S_BASE = [
    "k8s/base/kustomization.yaml",
    "k8s/base/backend.yaml",
    "k8s/base/frontend.yaml",
    "k8s/base/postgres.yaml",
    "k8s/base/redis.yaml",
    "k8s/base/ingress.yaml",
    "k8s/base/hpa.yaml",
    "k8s/base/vpa.yaml",
    "k8s/base/network-policy.yaml",
    "k8s/base/pdb.yaml",
]


def check_kubernetes() -> None:
    print("\n── Kubernetes manifests ──")
    for path in _REQUIRED_OVERLAYS:
        check_file(path)
    for path in _REQUIRED_K8S_BASE:
        check_file(path)

    # No `:latest` tag in any K8s YAML (deployment images should be SHA-pinned).
    latest_hits: list[str] = []
    k8s_dir = ROOT / "k8s"
    for p in k8s_dir.rglob("*.yaml"):
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"image:\s+\S+:latest", line):
                latest_hits.append(f"{p.relative_to(ROOT)}:{lineno}: {line.strip()}")
    if latest_hits:
        for h in latest_hits:
            fail(f"`:latest` tag in K8s manifest — {h}")
    else:
        ok("no :latest tags in Kubernetes manifests")

    # Postgres must be a StatefulSet (not a Deployment).
    postgres_yaml = read("k8s/base/postgres.yaml")
    if "kind: StatefulSet" in postgres_yaml:
        ok("postgres.yaml uses StatefulSet")
    else:
        fail("postgres.yaml must use StatefulSet, not Deployment")

    # HPA must reference the backend.
    hpa_yaml = read("k8s/base/hpa.yaml")
    if "backend" in hpa_yaml.lower():
        ok("hpa.yaml references backend")
    else:
        warn("hpa.yaml does not appear to reference backend deployment")

    # VPA must exist (recommender mode).
    vpa_yaml = read("k8s/base/vpa.yaml")
    if "VerticalPodAutoscaler" in vpa_yaml:
        ok("vpa.yaml contains VerticalPodAutoscaler resource")
    else:
        fail("vpa.yaml missing or does not contain VerticalPodAutoscaler")


# ---------------------------------------------------------------------------
# Check: production Compose (compose.prod.yaml) constraints
# ---------------------------------------------------------------------------


def check_compose_prod() -> None:
    print("\n── Production Compose (compose.prod.yaml) ──")
    prod_text = read("compose.prod.yaml")
    if not prod_text:
        fail("compose.prod.yaml not found or empty")
        return

    # Postgres and Redis must NOT expose ports to the host in prod.
    in_dangerous_service = False
    dangerous_ports = False
    for line in prod_text.splitlines():
        stripped = line.lstrip()
        if re.match(r"^  [a-z]", line) and stripped.endswith(":") and not stripped.startswith("#"):
            svc = stripped.rstrip(":")
            in_dangerous_service = svc in ("postgres", "redis", "migrate", "ollama", "ollama-pull")
        if in_dangerous_service and stripped.startswith("ports:"):
            dangerous_ports = True
    if dangerous_ports:
        fail("compose.prod.yaml exposes ports on postgres/redis/migrate — must be internal only")
    else:
        ok("compose.prod.yaml: DB and cache have no published host ports")

    # Prod compose must not have a `build:` key (should use pre-built images).
    if re.search(r"^\s{2,4}build:", prod_text, re.MULTILINE):
        warn("compose.prod.yaml contains a `build:` key — prod should use pre-built images")
    else:
        ok("compose.prod.yaml: no `build:` key, uses pre-built images")

    # Images should not use :dev or :latest.
    if re.search(r"image:.*:dev\b", prod_text):
        fail("compose.prod.yaml contains :dev image tag — prod must use a SHA-tagged image")
    else:
        ok("compose.prod.yaml: no :dev image tags")
