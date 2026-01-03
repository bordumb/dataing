"""Dependency injection and application lifespan management."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import Request

from dataing.adapters.context import ContextEngine, DatabaseContext
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.postgres import PostgresAdapter
from dataing.adapters.llm.client import AnthropicClient
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment."""

    def __init__(self) -> None:
        """Load settings from environment variables."""
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dataing")
        self.app_database_url = os.getenv("APP_DATABASE_URL", self.database_url)
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

        # Circuit breaker settings
        self.max_total_queries = int(os.getenv("MAX_TOTAL_QUERIES", "50"))
        self.max_queries_per_hypothesis = int(os.getenv("MAX_QUERIES_PER_HYPOTHESIS", "5"))
        self.max_retries_per_hypothesis = int(os.getenv("MAX_RETRIES_PER_HYPOTHESIS", "2"))


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan - setup and teardown.

    This context manager handles:
    - Database connection pool setup
    - LLM client initialization
    - Orchestrator configuration
    """
    # Setup data warehouse adapter
    db = PostgresAdapter(settings.database_url)
    await db.connect()

    # Setup application database
    app_db = AppDatabase(settings.app_database_url)
    await app_db.connect()

    llm = AnthropicClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
    )

    # Create database context for resolving tenant data sources
    database_context = DatabaseContext(app_db)

    # Create context engine (no longer needs db passed directly)
    context_engine = ContextEngine()

    circuit_breaker = CircuitBreaker(
        CircuitBreakerConfig(
            max_total_queries=settings.max_total_queries,
            max_queries_per_hypothesis=settings.max_queries_per_hypothesis,
            max_retries_per_hypothesis=settings.max_retries_per_hypothesis,
        )
    )

    orchestrator = InvestigationOrchestrator(
        db=db,  # Fallback adapter
        llm=llm,
        context_engine=context_engine,
        circuit_breaker=circuit_breaker,
        config=OrchestratorConfig(),
    )

    # Store in app state
    app.state.db = db
    app.state.app_db = app_db
    app.state.llm = llm
    app.state.database_context = database_context
    app.state.context_engine = context_engine
    app.state.circuit_breaker = circuit_breaker
    app.state.orchestrator = orchestrator
    investigations_store: dict[str, dict[str, Any]] = {}
    app.state.investigations = investigations_store

    # Demo mode: seed demo data
    if os.getenv("DATADR_DEMO_MODE", "").lower() == "true":
        logger.info("Running in DEMO MODE - seeding demo data")
        await _seed_demo_data(app_db)

    yield

    # Teardown
    await database_context.close_all()  # Close cached adapters
    await db.close()
    await app_db.close()


async def _seed_demo_data(app_db: AppDatabase) -> None:
    """Seed demo data into the application database.

    This is called when DATADR_DEMO_MODE=true.
    Creates a demo tenant, API key, and data source pointing to fixtures.
    """
    import hashlib
    import json
    from uuid import UUID

    from cryptography.fernet import Fernet

    # Demo IDs - stable UUIDs for idempotent seeding
    DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
    DEMO_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000002")
    DEMO_DATASOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")

    # Demo API key value
    DEMO_API_KEY_VALUE = "dd_demo_12345"
    DEMO_API_KEY_PREFIX = "dd_demo_"
    DEMO_API_KEY_HASH = hashlib.sha256(DEMO_API_KEY_VALUE.encode()).hexdigest()

    # Check if already seeded
    existing = await app_db.fetch_one(
        "SELECT id FROM tenants WHERE id = $1",
        DEMO_TENANT_ID,
    )

    if existing:
        logger.info("Demo data already seeded, skipping")
        return

    logger.info("Seeding demo data...")

    # Create demo tenant
    await app_db.execute(
        """INSERT INTO tenants (id, name, slug, settings)
           VALUES ($1, $2, $3, $4)""",
        DEMO_TENANT_ID,
        "Demo Account",
        "demo",
        json.dumps({"plan_tier": "enterprise"}),
    )

    # Create demo API key
    await app_db.execute(
        """INSERT INTO api_keys (id, tenant_id, key_hash, key_prefix, name, scopes, is_active)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        DEMO_API_KEY_ID,
        DEMO_TENANT_ID,
        DEMO_API_KEY_HASH,
        DEMO_API_KEY_PREFIX,
        "Demo API Key",
        json.dumps(["read", "write", "admin"]),
        True,
    )

    # Create demo data source (DuckDB pointing to fixtures)
    fixture_path = os.getenv("DATADR_FIXTURE_PATH", "./demo/fixtures/null_spike")
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if not encryption_key:
        encryption_key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = encryption_key

    connection_config = {
        "path": fixture_path,
        "read_only": True,
    }
    f = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
    encrypted_config = f.encrypt(json.dumps(connection_config).encode()).decode()

    await app_db.execute(
        """INSERT INTO data_sources
            (id, tenant_id, name, type, connection_config_encrypted,
            is_default, is_active, last_health_check_status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
        DEMO_DATASOURCE_ID,
        DEMO_TENANT_ID,
        "E-Commerce Demo",
        "duckdb",
        encrypted_config,
        True,
        True,
        "healthy",
    )

    logger.info("Demo data seeded successfully")
    logger.info(f"  API Key: {DEMO_API_KEY_VALUE}")
    logger.info(f"  Data Source: E-Commerce Demo (path: {fixture_path})")


def get_orchestrator(request: Request) -> InvestigationOrchestrator:
    """Get the orchestrator from app state.

    Args:
        request: The current request.

    Returns:
        The configured InvestigationOrchestrator.
    """
    return request.app.state.orchestrator


def get_db(request: Request) -> PostgresAdapter:
    """Get the database adapter from app state.

    Args:
        request: The current request.

    Returns:
        The configured PostgresAdapter.
    """
    return request.app.state.db


def get_investigations(request: Request) -> dict[str, dict[str, Any]]:
    """Get the investigations store from app state.

    Args:
        request: The current request.

    Returns:
        Dictionary of investigation states.
    """
    investigations: dict[str, dict[str, Any]] = request.app.state.investigations
    return investigations


def get_app_db(request: Request) -> AppDatabase:
    """Get the application database from app state.

    Args:
        request: The current request.

    Returns:
        The configured AppDatabase.
    """
    return request.app.state.app_db


def get_database_context(request: Request) -> DatabaseContext:
    """Get the database context from app state.

    The database context resolves tenant data source adapters
    for running investigations against tenant data.

    Args:
        request: The current request.

    Returns:
        The configured DatabaseContext.
    """
    return request.app.state.database_context
