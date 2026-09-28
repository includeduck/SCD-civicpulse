"""The frontend's typed client is generated from frontend/openapi.json; it must match the API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.main import create_app
from scripts.export_openapi import OUTPUT, render


@pytest.fixture
def fresh_app() -> FastAPI:
    """Not the shared session app: other tests add throwaway routes to that one."""
    return create_app()


def test_committed_openapi_matches_the_app(fresh_app: FastAPI):
    assert OUTPUT.exists(), "run: python -m scripts.export_openapi"
    assert OUTPUT.read_text(encoding="utf-8") == render(fresh_app.openapi()), (
        "frontend/openapi.json is stale: run `python -m scripts.export_openapi` in backend/, "
        "then `npm run gen:api` in frontend/"
    )


def test_error_bodies_are_in_the_contract(fresh_app: FastAPI):
    """The frontend renders the server's 400/404/409 messages, so their shape must be typed."""
    patch = fresh_app.openapi()["paths"]["/api/complaints/{complaint_id}/status"]["patch"]
    assert {"400", "404", "409"} <= set(patch["responses"])
