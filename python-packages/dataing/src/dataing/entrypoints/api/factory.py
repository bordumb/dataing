"""FastAPI application factory - Community Edition.

Importing this module builds nothing. ``app.py`` calls create_app() once to make the app
that servers load. Enterprise Edition calls create_app() and adds EE routes/middleware
(auth, etc.).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from dataing.telemetry import CorrelationMiddleware, configure_logging, init_telemetry

from .deps import lifespan
from .routes import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    # Initialize OpenTelemetry SDK (idempotent, safe to call multiple times)
    init_telemetry()

    # Configure structured logging with trace context injection
    log_level = os.getenv("LOG_LEVEL", "INFO")
    json_logs = os.getenv("LOG_FORMAT", "json").lower() == "json"
    configure_logging(log_level=log_level, json_output=json_logs)

    app = FastAPI(
        title="dataing",
        description="Autonomous Data Quality Investigation",
        version="2.0.0",
        lifespan=lifespan,
        redirect_slashes=False,  # Prevent 307 redirects that lose auth headers
    )

    # Auto-instrument FastAPI with OpenTelemetry (handles all HTTP tracing)
    FastAPIInstrumentor.instrument_app(app)

    # Thin correlation ID middleware (tracing handled by OTEL instrumentor)
    app.add_middleware(CorrelationMiddleware)

    # CORS middleware for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app
