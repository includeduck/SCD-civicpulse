# ─── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated virtual environment for build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package specification first to leverage Docker layer caching
COPY pyproject.toml .

# Install dependencies into virtualenv
RUN pip install --upgrade pip && \
    pip install .

# ─── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install minimal runtime libraries (libpq for asyncpg/psycopg2, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create unprivileged non-root user (UID 10001)
RUN groupadd -g 10001 civicpulse && \
    useradd -u 10001 -g civicpulse -s /bin/sh -m appuser

# Copy application source code
COPY --chown=appuser:civicpulse . .

# Switch to unprivileged non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Docker Healthcheck targeting liveness probe
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Exec-form CMD: uvicorn is PID 1 and receives SIGTERM directly, so it stops
# accepting connections, drains in-flight requests (at most 25 s, inside the
# Kubernetes default 30 s grace period), then runs the app's shutdown.
# Proxy headers and access logs are handled by the app itself (trusted proxies
# from FORWARDED_ALLOW_IPS; request_completed JSON events without client IPs).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "25", "--no-proxy-headers", "--no-access-log"]
