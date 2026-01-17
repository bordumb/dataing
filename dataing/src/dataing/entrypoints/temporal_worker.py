"""Temporal worker entrypoint with full dependency injection.

This module creates a production-ready Temporal worker that:
- Connects to Temporal using settings from environment
- Wires all 8 activities with factory closures capturing dependencies
- Registers both InvestigationWorkflow and EvaluateHypothesisWorkflow
- Sets appropriate concurrency limits

Usage:
    python -m dataing.entrypoints.temporal_worker

    Or via just:
    just dev-temporal-worker
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from dataing.adapters.context import ContextEngine
from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.agents import AgentClient
from dataing.entrypoints.api.deps import settings
from dataing.temporal.activities import (
    make_check_patterns_activity,
    make_counter_analyze_activity,
    make_execute_query_activity,
    make_gather_context_activity,
    make_generate_hypotheses_activity,
    make_generate_query_activity,
    make_interpret_evidence_activity,
    make_synthesize_activity,
)
from dataing.temporal.workflows import EvaluateHypothesisWorkflow, InvestigationWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Worker configuration
MAX_CONCURRENT_ACTIVITIES = 10
MAX_CONCURRENT_WORKFLOW_TASKS = 5


async def create_dependencies() -> dict[str, Any]:
    """Create and initialize all dependencies for activities.

    Returns:
        Dictionary containing initialized dependency instances.
    """
    logger.info("Initializing dependencies...")

    # Database connection
    app_db = AppDatabase(settings.app_database_url)
    await app_db.connect()
    logger.info("Database connected")

    # LLM client
    llm = AgentClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
    )
    logger.info(f"Agent client initialized with model: {settings.llm_model}")

    # Context engine
    context_engine = ContextEngine()
    logger.info("Context engine initialized")

    # Pattern repository
    pattern_repository = InMemoryPatternRepository()
    logger.info("Pattern repository initialized")

    return {
        "app_db": app_db,
        "llm": llm,
        "context_engine": context_engine,
        "pattern_repository": pattern_repository,
    }


def create_activities(deps: dict[str, Any]) -> list[Any]:
    """Create all activity functions with injected dependencies.

    Args:
        deps: Dictionary of initialized dependencies.

    Returns:
        List of activity functions ready for registration.
    """
    llm = deps["llm"]
    context_engine = deps["context_engine"]
    pattern_repository = deps["pattern_repository"]

    # Create a get_adapter function that will resolve adapters
    # In production, this would look up adapters from a registry
    # For now, we return a placeholder that logs a warning
    async def get_adapter(datasource_id: str) -> BaseAdapter:
        """Get adapter for a datasource ID.

        Note: This is a placeholder implementation. In production,
        this should look up the adapter from a registry based on
        tenant and datasource configuration.
        """
        logger.warning(
            f"get_adapter called for {datasource_id} - using placeholder. "
            "Production should use adapter registry."
        )
        # Return a mock adapter - in production this would be from registry
        raise NotImplementedError(
            f"Adapter resolution for {datasource_id} not yet implemented. "
            "Configure datasource adapters in production."
        )

    # Create a placeholder database adapter for execute_query
    # In production, this would be resolved per-datasource
    class PlaceholderDatabase:
        """Placeholder database for POC - raises error if used."""

        async def execute_query(self, sql: str) -> dict[str, Any]:
            """Execute query placeholder."""
            raise NotImplementedError(
                "PlaceholderDatabase.execute_query called. "
                "Configure per-datasource adapters in production."
            )

    activities = [
        # Context and pattern activities
        make_gather_context_activity(
            context_engine=context_engine,
            get_adapter=get_adapter,
        ),
        make_check_patterns_activity(pattern_repository=pattern_repository),
        # Hypothesis generation
        make_generate_hypotheses_activity(llm=llm),
        # Query generation and execution
        make_generate_query_activity(llm=llm),
        # Note: execute_query requires per-datasource database adapter
        # This placeholder will error if actually invoked
        make_execute_query_activity(database=PlaceholderDatabase()),
        # Evidence interpretation
        make_interpret_evidence_activity(llm=llm),
        # Synthesis and analysis
        make_synthesize_activity(llm=llm),
        make_counter_analyze_activity(llm=llm),
    ]

    logger.info(f"Created {len(activities)} activities with dependencies")
    return activities


async def run_worker() -> None:
    """Start the Temporal worker with all dependencies wired."""
    logger.info(
        f"Connecting to Temporal at {settings.TEMPORAL_HOST}, "
        f"namespace={settings.TEMPORAL_NAMESPACE}"
    )

    # Connect to Temporal server
    client = await Client.connect(
        target_host=settings.TEMPORAL_HOST,
        namespace=settings.TEMPORAL_NAMESPACE,
    )
    logger.info("Connected to Temporal server")

    # Initialize dependencies
    deps = await create_dependencies()

    # Create activities with dependencies
    activities = create_activities(deps)

    logger.info(
        f"Starting worker on task queue: {settings.TEMPORAL_TASK_QUEUE}, "
        f"max_concurrent_activities={MAX_CONCURRENT_ACTIVITIES}, "
        f"max_concurrent_workflow_tasks={MAX_CONCURRENT_WORKFLOW_TASKS}"
    )

    # Create and run worker
    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow],
        activities=activities,
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
        max_concurrent_workflow_tasks=MAX_CONCURRENT_WORKFLOW_TASKS,
    )

    try:
        await worker.run()
    finally:
        # Cleanup
        logger.info("Worker shutting down, cleaning up resources...")
        app_db = deps.get("app_db")
        if app_db:
            await app_db.disconnect()
        logger.info("Cleanup complete")


def main() -> None:
    """Main entry point for the Temporal worker."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.exception(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    main()
