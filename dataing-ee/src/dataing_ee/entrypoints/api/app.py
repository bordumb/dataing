"""FastAPI application - Enterprise Edition.

This module creates the EE app by extending the CE app with EE routes and middleware.
The key difference from CE is using the real AuditRepository instead of the stub.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dataing.adapters.auth.recovery_admin import AdminContactRecoveryAdapter
from dataing.adapters.auth.recovery_console import ConsoleRecoveryAdapter
from dataing.adapters.auth.recovery_email import EmailPasswordRecoveryAdapter
from dataing.adapters.context import ContextEngine
from dataing.adapters.datasource import BaseAdapter
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.entitlements import DatabaseEntitlementsAdapter
from dataing.adapters.investigation_feedback import InvestigationFeedbackAdapter
from dataing.agents import AgentClient
from dataing.adapters.notifications.email import EmailConfig, EmailNotifier
from dataing.core.auth.recovery import PasswordRecoveryAdapter
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.entrypoints.api.deps import _seed_demo_data, settings
from dataing.entrypoints.api.routes import api_router as ce_api_router
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from dataing_ee.adapters.audit import AuditRepository
from dataing_ee.entrypoints.api.routes.audit import router as audit_router
from dataing_ee.entrypoints.api.routes.scim import router as scim_router
from dataing_ee.entrypoints.api.routes.settings import router as settings_router
from dataing_ee.entrypoints.api.routes.sso import router as sso_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for EE.

    This is a copy of the CE lifespan with the real AuditRepository instead of the stub.
    """
    # Setup application database
    app_db = AppDatabase(settings.app_database_url)
    await app_db.connect()

    # Create EE audit repository (real implementation, not stub)
    audit_repo = AuditRepository(pool=app_db.pool)
    app.state.audit_repo = audit_repo

    # Create entitlements adapter for plan-based feature gating
    entitlements_adapter = DatabaseEntitlementsAdapter(pool=app_db.pool)
    app.state.entitlements_adapter = entitlements_adapter

    llm = AgentClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
    )

    # Create context engine
    context_engine = ContextEngine()

    circuit_breaker = CircuitBreaker(
        CircuitBreakerConfig(
            max_total_queries=settings.max_total_queries,
            max_queries_per_hypothesis=settings.max_queries_per_hypothesis,
            max_retries_per_hypothesis=settings.max_retries_per_hypothesis,
        )
    )

    # Note: Orchestrator now receives adapters per-request instead of at startup
    # The db parameter is now optional and will be resolved per-tenant
    orchestrator = InvestigationOrchestrator(
        db=None,  # Will be set per-request based on tenant's data source
        llm=llm,
        context_engine=context_engine,
        circuit_breaker=circuit_breaker,
        config=OrchestratorConfig(),
    )

    # Initialize investigation feedback adapter
    feedback_adapter = InvestigationFeedbackAdapter(db=app_db)

    # Initialize email notifier (optional, needed for email recovery)
    email_notifier: EmailNotifier | None = None
    if settings.smtp_host:
        email_config = EmailConfig(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user or None,
            smtp_password=settings.smtp_password or None,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name,
            use_tls=settings.smtp_use_tls,
        )
        email_notifier = EmailNotifier(email_config)
        logger.info("Email notifier initialized")

    # Initialize password recovery adapter based on configuration
    recovery_adapter: PasswordRecoveryAdapter
    recovery_type = settings.password_recovery_type.lower()

    if recovery_type == "auto":
        # Auto-select: email if SMTP configured, else console
        if settings.smtp_host and email_notifier:
            recovery_adapter = EmailPasswordRecoveryAdapter(
                email_notifier=email_notifier,
                frontend_url=settings.frontend_url,
            )
            logger.info("Using email recovery adapter (SMTP configured)")
        else:
            recovery_adapter = ConsoleRecoveryAdapter(
                frontend_url=settings.frontend_url,
            )
            logger.info("Using console recovery adapter (no SMTP, demo mode)")

    elif recovery_type == "email":
        # Force email - fail if no SMTP
        if not settings.smtp_host or not email_notifier:
            raise RuntimeError("PASSWORD_RECOVERY_TYPE=email but SMTP_HOST not configured")
        recovery_adapter = EmailPasswordRecoveryAdapter(
            email_notifier=email_notifier,
            frontend_url=settings.frontend_url,
        )
        logger.info("Using email recovery adapter (forced)")

    elif recovery_type == "console":
        # Force console
        recovery_adapter = ConsoleRecoveryAdapter(
            frontend_url=settings.frontend_url,
        )
        logger.info("Using console recovery adapter (forced)")

    elif recovery_type == "admin_contact":
        # Admin contact for SSO orgs
        recovery_adapter = AdminContactRecoveryAdapter(
            admin_email=settings.admin_email or None,
        )
        logger.info("Using admin contact recovery adapter")

    else:
        raise RuntimeError(
            f"Invalid PASSWORD_RECOVERY_TYPE: {recovery_type}. "
            "Must be one of: auto, email, console, admin_contact"
        )

    # Store in app state
    app.state.app_db = app_db
    app.state.llm = llm
    app.state.context_engine = context_engine
    app.state.circuit_breaker = circuit_breaker
    app.state.orchestrator = orchestrator
    app.state.feedback_adapter = feedback_adapter
    app.state.email_notifier = email_notifier
    app.state.recovery_adapter = recovery_adapter
    app.state.frontend_url = settings.frontend_url
    # Check DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY
    app.state.encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    # Cache for active adapters (tenant_id:datasource_id -> adapter)
    adapter_cache: dict[str, BaseAdapter] = {}
    app.state.adapter_cache = adapter_cache

    investigations_store: dict[str, dict[str, Any]] = {}
    app.state.investigations = investigations_store

    # Demo mode: seed demo data
    demo_mode = os.getenv("DATADR_DEMO_MODE", "").lower()
    print(f"[DEBUG] DATADR_DEMO_MODE={demo_mode}", flush=True)
    enc_key = app.state.encryption_key
    enc_preview = enc_key[:15] if enc_key else "None"
    print(f"[DEBUG] Initial encryption_key: {enc_preview}...", flush=True)
    if demo_mode == "true":
        print("[DEBUG] Running in DEMO MODE - seeding demo data", flush=True)
        await _seed_demo_data(app_db)
        # Re-read encryption key in case _seed_demo_data generated one
        app.state.encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    enc_key = app.state.encryption_key
    enc_preview = enc_key[:15] if enc_key else "None"
    print(f"[DEBUG] Final encryption_key prefix: {enc_preview}...", flush=True)

    yield

    # Teardown - close all cached adapters
    for cache_key, adapter in app.state.adapter_cache.items():
        try:
            await adapter.disconnect()
            logger.debug(f"adapter_closed: {cache_key}")
        except Exception as e:
            logger.warning(f"adapter_close_failed: {cache_key}, error={e}")

    await app_db.close()


def create_ee_app() -> FastAPI:
    """Create and configure the Enterprise Edition FastAPI application.

    Returns:
        Configured FastAPI application instance with EE features.
    """
    app = FastAPI(
        title="dataing Enterprise Edition",
        description="Autonomous Data Quality Investigation - Enterprise Edition",
        version="2.0.0",
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # CORS middleware for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include CE API routes
    app.include_router(ce_api_router, prefix="/api/v1")

    # Include EE routes
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(sso_router, prefix="/api/v1")
    app.include_router(scim_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "edition": "enterprise"}

    return app


# EE app instance
app = create_ee_app()
