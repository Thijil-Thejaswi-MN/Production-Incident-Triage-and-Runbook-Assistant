"""Structured JSON logging with a correlation ID bound per run (requirements F8, D5).

Every log line carries `timestamp` (ISO 8601, UTC), `level`, `event` and, when a
correlation scope is active, `correlation_id`. Values under sensitive keys are
redacted before rendering.
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, TextIO

import structlog

CORRELATION_ID_KEY = "correlation_id"
REDACTED = "[REDACTED]"
# Matches e.g. `api_key`, `llm_api_key`, `password`, `access_token`, `authorization`,
# but not token counters such as `prompt_tokens`.
_SENSITIVE_KEY = re.compile(r"(^|_)(api_?key|password|secret|token|authorization)$", re.IGNORECASE)


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: replace values of top-level keys that look sensitive."""
    for key in list(event_dict):
        if _SENSITIVE_KEY.search(key):
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True, stream: TextIO | None = None) -> None:
    """Configure structlog for the process. Safe to call more than once."""
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.format_exc_info,
            redact_sensitive,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger


def new_correlation_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Bind a correlation ID to every log line emitted inside the block."""
    cid = correlation_id or new_correlation_id()
    with structlog.contextvars.bound_contextvars(**{CORRELATION_ID_KEY: cid}):
        yield cid
