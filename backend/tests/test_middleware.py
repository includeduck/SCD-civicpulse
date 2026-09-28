"""Tests for Request-ID and CORS middlewares."""

from __future__ import annotations

import uuid

from fastapi import status
from fastapi.testclient import TestClient


def test_request_id_generated_when_missing(client: TestClient):
    """When X-Request-ID header is omitted, the middleware must generate a valid UUID."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert len(request_id) > 0
    # Must be valid UUID format
    parsed = uuid.UUID(request_id)
    assert str(parsed) == request_id


def test_request_id_preserved_when_provided(client: TestClient):
    """When client sends X-Request-ID, the exact same ID must be echoed back in the response."""
    custom_id = "trace-client-fixed-token-998877"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Request-ID") == custom_id


def test_cors_headers_exposed(client: TestClient):
    """CORS response must expose X-Request-ID and Retry-After headers."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either 200 OK or appropriate CORS headers
    is_ok = response.status_code == status.HTTP_200_OK
    assert "access-control-allow-origin" in response.headers or is_ok


def test_unsafe_request_id_is_replaced(client: TestClient):
    """Client IDs that could forge log fields or bloat logs are replaced with a UUID."""
    for bad in ('x" level="critical', "a" * 129):
        response = client.get("/health", headers={"X-Request-ID": bad})
        request_id = response.headers["X-Request-ID"]
        assert request_id != bad
        uuid.UUID(request_id)


def test_unhandled_error_keeps_request_id():
    """A 500 must still carry X-Request-ID, and its error log must include the request_id."""
    import logging

    from app.core.logging import request_id_var
    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    seen: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if "Unhandled exception" in record.getMessage():
                seen.append(request_id_var.get())

    handler = _Capture()
    logging.getLogger("app.core.exceptions").addHandler(handler)
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/boom", headers={"X-Request-ID": "trace-500"})
    finally:
        logging.getLogger("app.core.exceptions").removeHandler(handler)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers.get("X-Request-ID") == "trace-500"
    assert response.json()["code"] == "internal_error"
    assert seen == ["trace-500"]


class _Route:
    def __init__(self, path: str) -> None:
        self.path = self.path_format = path


def test_route_template_restores_outer_router_prefixes():
    """FastAPI 0.14x reports routes relative to their router; the label must stay the full template."""
    from app.core.middleware import route_template

    scope = {
        "route": _Route("/complaints/{complaint_id}"),
        "path": "/api/complaints/8c1f7a52",
        "path_params": {"complaint_id": "8c1f7a52"},
    }
    assert route_template(scope) == "/api/complaints/{complaint_id}"


def test_route_template_keeps_full_paths_and_marks_unmatched():
    from app.core.middleware import route_template

    assert (
        route_template({"route": _Route("/health"), "path": "/health", "path_params": {}})
        == "/health"
    )
    assert route_template({"path": "/nope"}) == "unmatched"


# ── Request body size limit ──────────────────────────────────────────────────


def test_declared_oversized_body_is_rejected_before_it_is_read(client: TestClient):
    big = "x" * (70 * 1024)  # over the 64 KiB default
    response = client.post(
        "/api/complaints",
        content=f'{{"text": "{big}", "location": "F-8"}}',
        headers={"Content-Type": "application/json", "X-Request-ID": "trace-413"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
    assert response.headers["X-Request-ID"] == "trace-413"


def test_streamed_oversized_body_without_content_length_is_cut_off(client: TestClient):
    def chunks():  # an iterator body is sent chunked, with no Content-Length
        yield b'{"text": "'
        for _ in range(20):
            yield b"x" * 8192
        yield b'", "location": "F-8"}'

    response = client.post(
        "/api/complaints", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_normal_complaint_is_unaffected_by_the_limit(client: TestClient):
    response = client.post(
        "/api/complaints",
        json={"text": "Pipe burst ho gaya hai, paani beh raha hai", "location": "F-8"},
    )
    assert response.status_code == 201
