"""Tests for scripts/check_submission.py (brief §5.8 submission lint).

Validates individual rule checkers against positive fixtures (PASS) and
deliberate negative fixtures (FAIL/WARN) to ensure violations are caught.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore

# Ensure scripts directory is in sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_submission import (  # noqa: E402
    validate_autoscaling_and_resilience,
    validate_backend_probes,
    validate_compose_prod,
    validate_git_shortlog,
    validate_postgres_manifest,
    validate_workflow_security,
)

# ---------------------------------------------------------------------------
# Compose prod fixture tests
# ---------------------------------------------------------------------------

_GOOD_COMPOSE_PROD = """
name: civicpulse
services:
  postgres:
    image: postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
    networks: [internal]
  redis:
    image: redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499
    networks: [internal]
  backend:
    image: ghcr.io/includeduck/scd-civicpulse/backend:${IMAGE_TAG}
    networks: [edge, internal]
  frontend:
    image: ghcr.io/includeduck/scd-civicpulse/frontend:${IMAGE_TAG}
    ports:
      - "8080:8080"
    networks: [edge]
"""

_BAD_COMPOSE_PROD_PORTS = """
name: civicpulse
services:
  postgres:
    image: postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
    ports:
      - "5432:5432"
  backend:
    image: ghcr.io/includeduck/scd-civicpulse/backend:${IMAGE_TAG}
"""

_BAD_COMPOSE_PROD_BUILD = """
name: civicpulse
services:
  backend:
    build:
      context: ./backend
    image: ghcr.io/includeduck/scd-civicpulse/backend:${IMAGE_TAG}
"""

_BAD_COMPOSE_PROD_DEV_TAG = """
name: civicpulse
services:
  backend:
    image: ghcr.io/includeduck/scd-civicpulse/backend:dev
"""


def test_compose_prod_good_passes():
    results = validate_compose_prod(_GOOD_COMPOSE_PROD)
    statuses = [s for s, _, _ in results]
    assert "FAIL" not in statuses
    assert all(s == "PASS" for s in statuses)


def test_compose_prod_exposed_port_fails():
    results = validate_compose_prod(_BAD_COMPOSE_PROD_PORTS)
    failed = [name for s, name, _ in results if s == "FAIL"]
    assert any("DB/cache ports" in name for name in failed)


def test_compose_prod_build_key_fails():
    results = validate_compose_prod(_BAD_COMPOSE_PROD_BUILD)
    failed = [name for s, name, _ in results if s == "FAIL"]
    assert any("no build:" in name for name in failed)


def test_compose_prod_dev_tag_fails():
    results = validate_compose_prod(_BAD_COMPOSE_PROD_DEV_TAG)
    failed = [name for s, name, _ in results if s == "FAIL"]
    assert any("immutable tags" in name for name in failed)


# ---------------------------------------------------------------------------
# Backend probes fixture tests
# ---------------------------------------------------------------------------

_GOOD_PROBES = """
        startupProbe:
          httpGet: { path: /health, port: http }
          failureThreshold: 30
          periodSeconds: 2
        livenessProbe:
          httpGet: { path: /health, port: http }
          periodSeconds: 10
        readinessProbe:
          httpGet: { path: /ready, port: http }
          periodSeconds: 5
"""

_BAD_PROBES_LIVENESS_USES_READY = """
        startupProbe:
          httpGet: { path: /health, port: http }
        livenessProbe:
          httpGet: { path: /ready, port: http }
        readinessProbe:
          httpGet: { path: /ready, port: http }
"""

_BAD_PROBES_MISSING_STARTUP = """
        livenessProbe:
          httpGet: { path: /health, port: http }
        readinessProbe:
          httpGet: { path: /ready, port: http }
"""


def test_backend_probes_good_passes():
    results = validate_backend_probes(_GOOD_PROBES)
    assert all(s == "PASS" for s, _, _ in results)


def test_backend_probes_liveness_ready_fails():
    results = validate_backend_probes(_BAD_PROBES_LIVENESS_USES_READY)
    fails = [name for s, name, _ in results if s == "FAIL"]
    assert any("must NOT use /ready" in name for name in fails)


def test_backend_probes_missing_startup_fails():
    results = validate_backend_probes(_BAD_PROBES_MISSING_STARTUP)
    fails = [n for s, n, _ in results if s == "FAIL"]
    assert any("startupProbe" in n for n in fails)


# ---------------------------------------------------------------------------
# Postgres manifest fixture tests
# ---------------------------------------------------------------------------

_GOOD_POSTGRES = """
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  type: ClusterIP
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  volumeClaimTemplates:
    - metadata:
        name: data
"""

_BAD_POSTGRES_NODEPORT = """
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  type: NodePort
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  volumeClaimTemplates:
    - metadata:
        name: data
"""

_BAD_POSTGRES_DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
"""


def test_postgres_manifest_good_passes():
    results = validate_postgres_manifest(_GOOD_POSTGRES)
    assert all(s == "PASS" for s, _, _ in results)


def test_postgres_manifest_nodeport_fails():
    results = validate_postgres_manifest(_BAD_POSTGRES_NODEPORT)
    fails = [name for s, name, _ in results if s == "FAIL"]
    assert any("NodePort" in name for name in fails)


def test_postgres_manifest_deployment_fails():
    results = validate_postgres_manifest(_BAD_POSTGRES_DEPLOYMENT)
    fails = [n for s, n, _ in results if s == "FAIL"]
    assert any("StatefulSet" in n for n in fails)


# ---------------------------------------------------------------------------
# Git attribution fixture tests
# ---------------------------------------------------------------------------


def test_git_shortlog_good_balanced():
    entries = [(50, "Alice"), (50, "Bob")]
    results = validate_git_shortlog(entries, allow_skew=False)
    assert all(s == "PASS" for s, _, _ in results)


def test_git_shortlog_skewed_fails_by_default():
    entries = [(85, "Alice"), (15, "Bob")]
    results = validate_git_shortlog(entries, allow_skew=False)
    statuses = {name: s for s, name, _ in results}
    assert statuses["contributor commit balance"] == "FAIL"


def test_git_shortlog_skewed_warns_with_allow_skew():
    entries = [(85, "Alice"), (15, "Bob")]
    results = validate_git_shortlog(entries, allow_skew=True)
    statuses = {name: s for s, name, _ in results}
    assert statuses["contributor commit balance"] == "WARN"


def test_git_shortlog_under_35_commits_fails():
    entries = [(10, "Alice"), (10, "Bob")]
    results = validate_git_shortlog(entries, allow_skew=False)
    statuses = {name: s for s, name, _ in results}
    assert statuses["total commits (no-merges)"] == "FAIL"


# ---------------------------------------------------------------------------
# Workflow and resilience checks
# ---------------------------------------------------------------------------


def test_workflow_security_missing_permissions_fails():
    wfs = {
        "ci.yml": "name: CI\njobs:\n  test:\n    runs-on: ubuntu-24.04\n",
        "cd.yml": "permissions:\n  contents: read\njobs:\n  build-push:\n    needs: test\n",
        "release.yml": "permissions:\n  contents: read\njobs:\n  release:\n    needs: test\n",
    }
    results = validate_workflow_security(wfs)
    fails = [n for s, n, _ in results if s == "FAIL"]
    assert any("ci.yml missing top-level permissions:" in n for n in fails)


def test_vpa_off_mode_validation():
    good_vpa = "apiVersion: autoscaling.k8s.io/v1\nkind: VerticalPodAutoscaler\nspec:\n  updatePolicy:\n    updateMode: \"Off\"\n"
    bad_vpa = "apiVersion: autoscaling.k8s.io/v1\nkind: VerticalPodAutoscaler\nspec:\n  updatePolicy:\n    updateMode: \"Auto\"\n"
    pdb = "apiVersion: policy/v1\nkind: PodDisruptionBudget\n"
    hpa = "apiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\nspec:\n  scaleTargetRef:\n    name: backend\n"

    good_res = validate_autoscaling_and_resilience(good_vpa, pdb, hpa)
    assert all(s == "PASS" for s, _, _ in good_res)

    bad_res = validate_autoscaling_and_resilience(bad_vpa, pdb, hpa)
    fails = [n for s, n, _ in bad_res if s == "FAIL"]
    assert any("updateMode: \"Off\"" in n for n in fails)
