"""Structured JSON logging for CivicPulse.

Every log line is a JSON object written to stdout. Fields always include:
  - timestamp (ISO-8601 UTC)
  - level
  - logger name
  - message
  - request_id (when available via contextvars)

API keys and secrets must never appear in log messages. The logging config
strips nothing automatically — callers are responsible for not logging secrets.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# Context variable so request_id is available everywhere within a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def _add_request_id(
    logger: Any,  # noqa: ARG001
    method: Any,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Inject the current request_id into every log record."""
    rid = request_id_var.get("")
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Wire up structlog with JSON output.

    Called from ``create_app`` so it runs when uvicorn imports the app, before
    uvicorn logs "Started server process"; from then on every line is JSON.
    JSON is the default in every environment so Compose/K8s logs are machine-readable;
    set LOG_FORMAT=console for human-friendly local output.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "console":
        renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # uvicorn installs its own plain-text handlers; route its lifecycle and
    # error logs through our JSON handler instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # uvicorn's access log is replaced by our request_completed event, which
    # carries request_id and the route template but not the client IP (ADR 0004).
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*."""
    return structlog.get_logger(name)
