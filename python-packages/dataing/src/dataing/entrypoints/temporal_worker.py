"""Temporal worker entrypoint with full dependency injection.

This module creates a production-ready Temporal worker that:
- Configures logging from LOG_LEVEL and LOG_FORMAT, like the API
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
import sys
from datetime import timedelta
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from temporalio.client import Client
from temporalio.worker import Worker

from dataing.adapters.context import ContextEngine
from dataing.adapters.datasource import get_registry
from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.agents import AgentClient
from dataing.agents.chat import build_brief_agent, build_chat_agent, build_chat_model
from dataing.config import settings
from dataing.core.issue_chat import InvestigationStatusReader
from dataing.core.snapshot_store import LocalSnapshotStore
from dataing.telemetry import configure_logging
from dataing.temporal.activities import (
    make_capture_snapshot_activity,
    make_check_patterns_activity,
    make_counter_analyze_activity,
    make_execute_query_activity,
    make_finalize_evidence_chain_activity,
    make_gather_context_activity,
    make_generate_hypotheses_activity,
    make_generate_query_activity,
    make_interpret_evidence_activity,
    make_synthesize_activity,
)
from dataing.temporal.activities.agent_turn import (
    make_mark_turn_failed_activity,
    make_run_agent_turn_activity,
    make_run_brief_draft_activity,
)
from dataing.temporal.activities.publish_outcome import make_publish_investigation_outcome_activity
from dataing.temporal.activities.steering import (
    formulate_hypothesis,
    make_record_steer_outcome_activity,
)
from dataing.temporal.adapters import TemporalAgentAdapter
from dataing.temporal.sandbox import workflow_runner
from dataing.temporal.workflows import (
    EvaluateHypothesisWorkflow,
    InvestigationWorkflow,
    IssueThreadWorkflow,
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

    # Snapshot store for investigation checkpoints
    snapshot_store = LocalSnapshotStore("/tmp/dataing/snapshots")
    logger.info("Snapshot store initialized")

    return {
        "app_db": app_db,
        "agent_adapter": agent_adapter,
        "context_engine": context_engine,
        "pattern_repository": pattern_repository,
        "snapshot_store": snapshot_store,
    }


class TenantAdapterCache:
    """Datasource adapters for worker activities, scoped and cached per tenant.

    Datasources are looked up by (tenant_id, datasource_id) and adapters are
    cached under the same key, so an investigation can only reach datasources
    owned by its tenant, and one tenant's cached adapter is never served to
    another tenant that names the same datasource ID.
    """

    def __init__(self, app_db: AppDatabase, encryption_key: str | None) -> None:
        """Initialize the cache.

        Args:
            app_db: Application database holding datasource configs.
            encryption_key: Fernet key for decrypting connection configs.
        """
        self._app_db = app_db
        self._encryption_key = encryption_key
        self._adapters: dict[tuple[UUID, UUID], BaseAdapter] = {}

    async def get_adapter(self, *, tenant_id: str, datasource_id: str) -> BaseAdapter:
        """Get a connected adapter for a datasource owned by the tenant.

        Looks up the datasource configuration, decrypts connection details,
        and creates the appropriate adapter.

        Args:
            tenant_id: Tenant the investigation runs for.
            datasource_id: Datasource to connect to.

        Returns:
            A connected adapter for the datasource.

        Raises:
            ValueError: If the tenant has no active datasource with this ID.
            RuntimeError: If decryption or connection fails.
        """
        key = (UUID(tenant_id), UUID(datasource_id))
        if key in self._adapters:
            return self._adapters[key]

        tenant_uuid, datasource_uuid = key
        ds = await self._app_db.get_data_source(
            data_source_id=datasource_uuid, tenant_id=tenant_uuid
        )
        if not ds or not ds.get("is_active"):
            raise ValueError(
                f"Datasource {datasource_id} not found or inactive for tenant {tenant_id}"
            )

        # Decrypt connection config
        if not self._encryption_key:
            raise RuntimeError(
                "ENCRYPTION_KEY not set - check DATADR_ENCRYPTION_KEY or ENCRYPTION_KEY env vars"
            )

        encrypted_config = ds.get("connection_config_encrypted", "")
        try:
            f = Fernet(self._encryption_key.encode())
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
        self._adapters[key] = adapter
        logger.info(
            f"Created adapter: type={ds_type}, name={ds.get('name')}, "
            f"tenant={tenant_id}, id={datasource_id}"
        )

        return adapter


def _chat_agent_factory() -> Any:
    """Return a factory for the issue chat agent (one model, a fresh agent per turn)."""
    model = build_chat_model(
        settings.chat_agent_model, settings.anthropic_api_key, settings.chat_agent_effort
    )
    logger.info(f"Chat agent model: {settings.chat_agent_model}")
    return lambda: build_chat_agent(model)


def _brief_agent_factory() -> Any:
    """Return a factory for the brief-drafting agent (medium effort by default)."""
    model = build_chat_model(
        settings.chat_agent_model, settings.anthropic_api_key, settings.chat_brief_effort
    )
    return lambda: build_brief_agent(model)


# A turn's attempts (2 x TURN_TIMEOUT plus backoff) end well within this
STALE_TURN_AFTER = timedelta(minutes=15)


async def _fail_stale_turns(app_db: AppDatabase) -> None:
    """Mark replies a crashed worker left streaming as failed. Non-fatal."""
    try:
        failed = await IssueThreadRepository(app_db).fail_stale_turns(STALE_TURN_AFTER)
    except Exception as e:
        logger.warning(f"Could not sweep stale agent turns: {e}")
        return
    if failed:
        logger.info(f"Marked {failed} stale agent replies as failed")


def _investigation_status_reader(client: Client) -> InvestigationStatusReader:
    """Return a reader of a running investigation's live hypotheses and steers."""

    async def read(investigation_id: str) -> dict[str, Any] | None:
        try:
            handle = client.get_workflow_handle(investigation_id)
            status = await handle.query(InvestigationWorkflow.get_status)
        except Exception as e:  # Finished, not found, or Temporal unreachable
            logger.debug(f"No live status for investigation {investigation_id}: {e}")
            return None
        return {
            "current_step": status.current_step,
            "hypotheses": status.hypotheses,
            "pending_steers": status.pending_steers,
        }

    return read


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
    snapshot_store = deps["snapshot_store"]

    # Get encryption key from environment
    encryption_key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    datasources = TenantAdapterCache(app_db, encryption_key)

    activities = [
        # Snapshot capture (fire-and-forget)
        make_capture_snapshot_activity(snapshot_store=snapshot_store),
        # Context and pattern activities
        make_gather_context_activity(
            context_engine=context_engine,
            get_adapter=datasources.get_adapter,
        ),
        make_check_patterns_activity(pattern_repository=pattern_repository),
        # Hypothesis generation (uses adapter for dict↔domain conversion)
        make_generate_hypotheses_activity(adapter=agent_adapter),
        # Query generation and execution
        make_generate_query_activity(adapter=agent_adapter),
        make_execute_query_activity(get_adapter=datasources.get_adapter),
        # Evidence interpretation
        make_interpret_evidence_activity(adapter=agent_adapter),
        # Synthesis and analysis
        make_synthesize_activity(adapter=agent_adapter),
        make_counter_analyze_activity(adapter=agent_adapter),
        # Evidence chain finalization
        make_finalize_evidence_chain_activity(app_db=app_db),
        # Outcome write-back to the investigation, its issue run and thread
        make_publish_investigation_outcome_activity(app_db=app_db),
        # Steering a running investigation
        formulate_hypothesis,
        make_record_steer_outcome_activity(app_db=app_db),
        # Issue chat agent turns
        make_run_agent_turn_activity(
            app_db=app_db,
            agent_factory=_chat_agent_factory(),
            investigation_status=deps.get("investigation_status"),
        ),
        make_run_brief_draft_activity(app_db=app_db, agent_factory=_brief_agent_factory()),
        make_mark_turn_failed_activity(app_db=app_db),
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
    await _fail_stale_turns(deps["app_db"])
    deps["investigation_status"] = _investigation_status_reader(client)

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
        workflows=[InvestigationWorkflow, EvaluateHypothesisWorkflow, IssueThreadWorkflow],
        activities=activities,
        workflow_runner=workflow_runner(),
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
            await app_db.close()
        logger.info("Cleanup complete")


def main() -> None:
    """Main entry point for the Temporal worker."""
    # Nothing else configures logging in the worker process. Unconfigured, structlog's
    # default renderer prints traceback frame locals, such as the encryption key and
    # decrypted connection configs in get_adapter().
    configure_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        json_output=os.getenv("LOG_FORMAT", "json").lower() == "json",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.exception(f"Worker failed: {e}")
        # The log entry has the traceback. Re-raising would make the interpreter print it
        # again, unformatted, on stderr.
        sys.exit(1)


if __name__ == "__main__":
    main()
