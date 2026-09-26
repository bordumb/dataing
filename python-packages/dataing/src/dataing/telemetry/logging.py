"""Logging configuration with OpenTelemetry trace context integration."""

import logging
import sys
from typing import Any, TextIO

import structlog

from dataing.telemetry.structlog_processor import add_trace_context


def quiet_http_client_loggers() -> None:
    """Keep httpx and httpcore at WARNING, whatever the app log level.

    httpx logs every request's full URL at INFO, and incoming-webhook URLs (Slack,
    Microsoft Teams, Discord) carry a bearer secret in the path.
    """
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


class _RootHandler(logging.StreamHandler[TextIO]):
    """Stdout handler that configure_logging() owns on the root logger."""


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure structlog and stdlib logging with trace context injection.

    A stdout handler on the root logger renders structlog events and the stdlib
    records that reach it (temporalio's Python loggers, httpx, ``logging.getLogger``
    callers) through a ``ProcessorFormatter``, so both share one processor chain and
    renderer. Every entry gets a timestamp, level, logger name and bound contextvars,
    plus trace_id and span_id when an OpenTelemetry span is active.

    Safe to call more than once: each call replaces the handler from the previous
    call and leaves other root handlers, such as pytest's, in place.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON; otherwise use console-friendly format.
    """
    # structlog runs these before handing an event to logging; the formatter runs them
    # on stdlib records.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_trace_context,  # Inject trace_id, span_id from OTEL
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        # Also skip logging's own frames, so a stdlib record's stack starts at its caller.
        structlog.processors.StackInfoRenderer(additional_ignores=["logging"]),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    render_processors: list[Any]
    if json_output:
        # Plain traceback text. Not dict_tracebacks: by default it renders frame locals,
        # which include the encryption key and decrypted datasource configs.
        render_processors = [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Rich renders every frame's locals by default, which would print decrypted
        # datasource credentials and the encryption key held at the decrypt call sites.
        render_processors = [
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False)
            )
        ]

    # The formatter renders the traceback itself and clears it from the record, so
    # logging does not append a second, plain copy.
    handler = _RootHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                *render_processors,
            ],
        )
    )

    root = logging.getLogger()
    for previous in [h for h in root.handlers if isinstance(h, _RootHandler)]:
        root.removeHandler(previous)
    root.addHandler(handler)
    root.setLevel(log_level.upper())
    quiet_http_client_loggers()
