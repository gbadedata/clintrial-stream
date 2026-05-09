"""Structured logging with correlation IDs.

Every log line emitted by ClinTrial-Stream is a single JSON object with:
    - timestamp (ISO 8601, UTC)
    - level (info, warning, etc.)
    - event (the log message)
    - correlation_id (traces a request through producer/consumer/API)
    - any other key-value context the caller bound

This format is what CloudWatch Logs Insights, Datadog, Honeycomb, and every
other modern logging stack expects. Free-text logs are dead.

Usage:

    from clintrial.observability import get_logger, bind_correlation_id

    logger = get_logger(__name__)

    bind_correlation_id("01HXYZABCDEF...")
    logger.info("event_processed", patient_id="P-12345", duration_ms=42)

    # Output:
    # {"timestamp": "2026-05-09T01:23:45.678Z", "level": "info",
    #  "event": "event_processed", "correlation_id": "01HXYZ...",
    #  "patient_id": "P-12345", "duration_ms": 42, "logger": "..."}
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any, cast

import structlog
from structlog.types import EventDict, Processor

from clintrial.config import settings

# -----------------------------------------------------------------------------
# Correlation ID context
# -----------------------------------------------------------------------------
# A ContextVar is the asyncio-safe way to attach state to a logical "request".
# Each Lambda invocation, each Flask request, each producer batch sets its own
# correlation_id and the value is automatically propagated through async tasks
# without explicit passing.

_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def bind_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current logical request.

    Called once at the start of a request/event/Lambda invocation. Every
    subsequent log line in this context will include the correlation_id field
    automatically.
    """
    _correlation_id_ctx.set(correlation_id)


def get_correlation_id() -> str | None:
    """Return the current correlation ID, or None if none set."""
    return _correlation_id_ctx.get()


def clear_correlation_id() -> None:
    """Reset the correlation ID. Call at the end of a request/event scope."""
    _correlation_id_ctx.set(None)


def _add_correlation_id_processor(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Structlog processor that injects correlation_id into every event."""
    cid = _correlation_id_ctx.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def _add_app_context_processor(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Structlog processor that injects environment metadata into every event."""
    event_dict["app_env"] = settings.app_env
    event_dict["aws_region"] = settings.aws_region
    return event_dict


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------


def configure_logging(*, json_output: bool = True) -> None:
    """Configure structlog and stdlib logging for the entire process.

    Call once at startup, before any module logs anything.

    Args:
        json_output: If True (default) emit JSON; if False, emit human-readable
            console output. Use False for local development if you find JSON
            hard to skim.
    """
    # Map our string level to logging's int level
    log_level = getattr(logging, settings.log_level)

    # Configure stdlib logging — structlog wraps this. Anything that uses the
    # stdlib logging API (boto3, requests, etc.) will be routed through here.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # The processor pipeline: each function transforms the event_dict in turn.
    # Level filtering is handled by make_filtering_bound_logger below, not here,
    # because filter_by_level requires stdlib logger internals and we use PrintLogger.
    shared_processors: list[Processor] = [
        # Add timestamp in ISO 8601 / UTC
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add the calling module/function for traceability
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        # Inject our correlation_id and app context
        _add_correlation_id_processor,
        _add_app_context_processor,
        # If you call log.exception(), expand the traceback
        structlog.processors.format_exc_info,
        # Decode bytes->str and other minor cleanups
        structlog.processors.UnicodeDecoder(),
    ]

    # Final renderer: JSON for production, human-readable for local dev
    final_processor: Processor
    if json_output:
        final_processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, final_processor],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger bound to the given name (typically ``__name__``)."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
