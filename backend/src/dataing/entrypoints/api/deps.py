"""Dependency injection and application lifespan management."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from fastapi import Depends, Request

from dataing.adapters.context.engine import DefaultContextEngine
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.postgres import PostgresAdapter
from dataing.adapters.llm.client import AnthropicClient
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

if TYPE_CHECKING:
    from fastapi import FastAPI


class Settings:
    """Application settings loaded from environment."""

    def __init__(self) -> None:
        """Load settings from environment variables."""
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://localhost:5432/dataing"
        )
        self.app_database_url = os.getenv(
            "APP_DATABASE_URL", self.database_url
        )
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

    context_engine = DefaultContextEngine(db=db)

    circuit_breaker = CircuitBreaker(
        CircuitBreakerConfig(
            max_total_queries=settings.max_total_queries,
            max_queries_per_hypothesis=settings.max_queries_per_hypothesis,
            max_retries_per_hypothesis=settings.max_retries_per_hypothesis,
        )
    )

    orchestrator = InvestigationOrchestrator(
        db=db,
        llm=llm,
        context_engine=context_engine,
        circuit_breaker=circuit_breaker,
        config=OrchestratorConfig(),
    )

    # Store in app state
    app.state.db = db
    app.state.app_db = app_db
    app.state.llm = llm
    app.state.context_engine = context_engine
    app.state.circuit_breaker = circuit_breaker
    app.state.orchestrator = orchestrator
    app.state.investigations: dict[str, dict] = {}

    yield

    # Teardown
    await db.close()
    await app_db.close()


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


def get_investigations(request: Request) -> dict[str, dict]:
    """Get the investigations store from app state.

    Args:
        request: The current request.

    Returns:
        Dictionary of investigation states.
    """
    return request.app.state.investigations


def get_app_db(request: Request) -> AppDatabase:
    """Get the application database from app state.

    Args:
        request: The current request.

    Returns:
        The configured AppDatabase.
    """
    return request.app.state.app_db
