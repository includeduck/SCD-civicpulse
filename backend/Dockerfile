# syntax=docker/dockerfile:1

# ─── Stage 1: dependencies ─────────────────────────────────────────
# Base image pinned by version *and* digest: the tag says what it is, the
# digest guarantees every build gets the same bytes.
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Only the dependency list first: this layer is rebuilt when a pinned
# dependency changes, not on every source edit. Every runtime dependency ships
# as a binary wheel, so no compiler is needed.
WORKDIR /build
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > requirements.txt \
    && pip install --only-binary=:all: -r requirements.txt

# ─── Stage 2: runtime ──────────────────────────────────────────────
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd -g 10001 civicpulse \
    && useradd -u 10001 -g civicpulse -s /usr/sbin/nologin -M appuser

COPY --from=builder /opt/venv /opt/venv

# Source last, owned by root: the app user can read it but not modify it.
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app

USER appuser
EXPOSE 8000

# Liveness only (never touches the DB), with the Python already in the image:
# no curl, so one less package to patch.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request, sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status != 200)"]

# Exec-form CMD: uvicorn is PID 1 and receives SIGTERM directly, so it stops
# accepting connections, drains in-flight requests (at most 25 s, inside the
# Kubernetes default 30 s grace period), then runs the app's shutdown.
# Proxy headers and access logs are handled by the app itself (trusted proxies
# from FORWARDED_ALLOW_IPS; request_completed JSON events without client IPs).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "25", "--no-proxy-headers", "--no-access-log"]
