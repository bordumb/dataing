"""Thin middleware for correlation ID only - tracing handled by OTEL."""

import uuid

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Lightweight middleware for correlation ID management.

    Tracing is handled by FastAPIInstrumentor - this only manages correlation IDs.
    Correlation IDs can be passed via X-Correlation-ID or X-Request-ID headers,
    or will be auto-generated if not provided.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and add correlation ID."""
        # Extract or generate correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )

        # Store in request state for downstream use
        request.state.correlation_id = correlation_id

        # Add to current span as attribute
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("correlation_id", correlation_id)

        response = await call_next(request)

        # Echo back in response
        response.headers["X-Correlation-ID"] = correlation_id

        return response
