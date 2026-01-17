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
import json
import logging
import os
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from temporalio.client import Client
from temporalio.worker import Worker

from dataing.adapters.context import ContextEngine
from dataing.adapters.datasource import get_registry
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
from dataing.temporal.adapters import TemporalAgentAdapter
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

    # LLM client with adapter
    agent_client = AgentClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
    )
    agent_adapter = TemporalAgentAdapter(agent_client)
    logger.info(f"Agent client initialized with model: {settings.llm_model}")

    # Context engine
    context_engine = ContextEngine()
    logger.info("Context engine initialized")

    # Pattern repository
    pattern_repository = InMemoryPatternRepository()
    logger.info("Pattern repository initialized")

    return {
        "app_db": app_db,
        "agent_adapter": agent_adapter,
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
    agent_adapter = deps["agent_adapter"]
    context_engine = deps["context_engine"]
    pattern_repository = deps["pattern_repository"]
    app_db = deps["app_db"]

    # Cache for adapters to avoid recreating them
    adapter_cache: dict[str, BaseAdapter] = {}

    # Get encryption key from environment
    encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")

    async def get_adapter(datasource_id: str) -> BaseAdapter:
        """Get adapter for a datasource ID from database config.

        Looks up the datasource configuration, decrypts connection details,
        and creates the appropriate adapter.
        """
        # Check cache first
        if datasource_id in adapter_cache:
            return adapter_cache[datasource_id]

        # Look up datasource config from database
        ds = await app_db.fetch_one(
            """
            SELECT id, type, connection_config_encrypted, name
            FROM data_sources
            WHERE id = $1 AND is_active = true
            """,
            UUID(datasource_id),
        )

        if not ds:
            raise ValueError(f"Datasource {datasource_id} not found or inactive")

        # Decrypt connection config
        if not encryption_key:
            raise RuntimeError(
                "ENCRYPTION_KEY not set - check DATADR_ENCRYPTION_KEY or ENCRYPTION_KEY env vars"
            )

        encrypted_config = ds.get("connection_config_encrypted", "")
        try:
            f = Fernet(encryption_key.encode())
            decrypted = f.decrypt(encrypted_config.encode()).decode()
            config: dict[str, Any] = json.loads(decrypted)
        except Exception as e:
            raise RuntimeError(f"Failed to decrypt connection config: {e}") from e

        # Create adapter using registry
        registry = get_registry()
        ds_type = ds["type"]

        try:
            adapter = registry.create(ds_type, config)
            await adapter.connect()
        except Exception as e:
            raise RuntimeError(f"Failed to create/connect adapter for {ds_type}: {e}") from e

        # Cache for reuse
        adapter_cache[datasource_id] = adapter
        logger.info(f"Created adapter: type={ds_type}, name={ds.get('name')}, id={datasource_id}")

        return adapter

    # Create a database wrapper that uses the adapter for query execution
    class AdapterDatabase:
        """Database wrapper that resolves adapter per-datasource for query execution."""

        def __init__(self, get_adapter_fn: Any) -> None:
            """Initialize with adapter resolver."""
            self._get_adapter = get_adapter_fn

        async def execute_query(
            self, sql: str, datasource_id: str | None = None
        ) -> dict[str, Any]:
            """Execute a SQL query using the specified datasource adapter."""
            from dataing.core.json_utils import to_json_safe

            if not datasource_id:
                raise RuntimeError("No datasource_id provided to execute_query")

            adapter = await self._get_adapter(datasource_id)

            # Execute query through adapter
            try:
                result = await adapter.execute_query(sql)
                rows = result.rows if hasattr(result, "rows") else []
                columns = result.columns if hasattr(result, "columns") else []

                # Convert rows to JSON-safe types (handles date, datetime, UUID, etc.)
                safe_rows = to_json_safe(rows)

                return {
                    "columns": columns,
                    "rows": safe_rows,
                    "row_count": len(rows),
                }
            except Exception as e:
                return {"error": str(e), "columns": [], "rows": [], "row_count": 0}

    adapter_database = AdapterDatabase(get_adapter)

    activities = [
        # Context and pattern activities
        make_gather_context_activity(
            context_engine=context_engine,
            get_adapter=get_adapter,
        ),
        make_check_patterns_activity(pattern_repository=pattern_repository),
        # Hypothesis generation (uses adapter for dict↔domain conversion)
        make_generate_hypotheses_activity(adapter=agent_adapter),
        # Query generation and execution
        make_generate_query_activity(adapter=agent_adapter),
        make_execute_query_activity(database=adapter_database),
        # Evidence interpretation
        make_interpret_evidence_activity(adapter=agent_adapter),
        # Synthesis and analysis
        make_synthesize_activity(adapter=agent_adapter),
        make_counter_analyze_activity(adapter=agent_adapter),
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
