"""FastAPI application - Enterprise Edition.

This module creates the EE app by extending the CE app with EE routes and middleware.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from dataing.entrypoints.api.app import create_app as create_ce_app
from dataing_ee.adapters.audit import AuditRepository
from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware
from dataing_ee.entrypoints.api.routes.audit import router as audit_router
from dataing_ee.entrypoints.api.routes.automation import router as automation_router
from dataing_ee.entrypoints.api.routes.integrations import router as integrations_router
from dataing_ee.entrypoints.api.routes.runbooks import router as runbooks_router
from dataing_ee.entrypoints.api.routes.scim import router as scim_router
from dataing_ee.entrypoints.api.routes.settings import router as settings_router
from dataing_ee.entrypoints.api.routes.sso import router as sso_router

logger = logging.getLogger(__name__)


def create_ee_app() -> FastAPI:
    """Create Enterprise Edition app by extending CE.

    Returns:
        Configured FastAPI application with EE features.
    """
    # Start with CE app (includes lifespan, routes, middleware)
    app = create_ce_app()

    # Update metadata for EE
    app.title = "dataing Enterprise Edition"
    app.description = "Autonomous Data Quality Investigation - Enterprise Edition"

    # Swap CE audit repo stub for real EE implementation in lifespan
    # This is done via middleware that checks app.state
    original_lifespan = app.router.lifespan_context

    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ee_lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Wrap CE lifespan to add EE audit repository."""
        async with original_lifespan(app):
            # Replace stub audit repo with real EE implementation
            app.state.audit_repo = AuditRepository(pool=app.state.app_db.pool)
            yield

    app.router.lifespan_context = ee_lifespan

    # Add EE audit middleware
    app.add_middleware(AuditMiddleware)

    # Include EE routes
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(sso_router, prefix="/api/v1")
    app.include_router(scim_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(automation_router, prefix="/api/v1")
    app.include_router(runbooks_router, prefix="/api/v1")

    # Override health check to indicate EE
    @app.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "edition": "enterprise"}

    return app


# EE app instance
app = create_ee_app()
