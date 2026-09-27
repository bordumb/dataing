"""Logging configuration with OpenTelemetry trace context integration."""

import logging
import sys
from typing import Any

import structlog

from dataing.telemetry.structlog_processor import add_trace_context


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure structlog with trace context injection.

    This sets up structured logging with automatic injection of trace_id and span_id
    from the current OpenTelemetry span context.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON; otherwise use console-friendly format.
    """
    # Set up standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Build processor chain
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_trace_context,  # Inject trace_id, span_id from OTEL
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Rich renders every frame's locals by default, which would print decrypted
        # datasource credentials and the encryption key held at the decrypt call sites.
        processors.append(
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False)
            )
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
