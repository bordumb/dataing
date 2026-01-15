"""End-to-end tests for investigation flow using maestro.

These tests use REAL implementations - no mocks, no stubs.
They verify the complete investigation workflow from start to finish.

Requirements:
- ANTHROPIC_API_KEY environment variable must be set for LLM tests
- DuckDB is used for in-memory database (no external DB needed)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest

from dataing.adapters.context.engine import ContextEngine
from dataing.adapters.datasource.sql.duckdb import DuckDBAdapter
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.core.domain_types import (
    AnomalyAlert,
    MetricSpec,
)
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.flow import (
    AwaitingUserInput,
    InvestigationCancelled,
    InvestigationError,
    WorkerShutdownError,
    build_investigation_workflow,
    run_investigation,
    run_with_checkpointing,
)
from dataing.core.investigation.values import StepType

LLM_SKIP_REASON = "ANTHROPIC_API_KEY not set - skipping LLM-dependent tests"


def get_api_key() -> str | None:
    """Get API key at runtime (not import time)."""
    return os.getenv("ANTHROPIC_API_KEY")


# =============================================================================
# Real Fixtures - No Mocks
# =============================================================================


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert for testing."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="NULL Rate",
            columns_referenced=["user_id"],
        ),
        anomaly_type="null_spike",
        anomaly_date="2024-01-15",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        severity="high",
    )


@pytest.fixture
def initial_context(sample_alert: AnomalyAlert) -> InvestigationContext:
    """Create initial investigation context."""
    return InvestigationContext(
        alert_summary=f"NULL spike in {sample_alert.dataset_id}: 15% vs 1% expected",
        alert=sample_alert.model_dump(mode="json"),
    )


@pytest.fixture
async def duckdb_adapter() -> AsyncGenerator[DuckDBAdapter, None]:
    """Create real DuckDB adapter with in-memory database and test data."""
    adapter = DuckDBAdapter({"path": ":memory:", "source_type": "database"})
    await adapter.connect()

    # Create test tables with realistic data
    await adapter.execute_query("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY,
            user_id VARCHAR,
            event_type VARCHAR,
            timestamp TIMESTAMP,
            properties JSON
        )
    """)

    # Insert test data - some with NULL user_id to simulate the anomaly
    await adapter.execute_query("""
        INSERT INTO events VALUES
        (1, 'user_123', 'page_view', '2024-01-15 10:00:00', '{}'),
        (2, NULL, 'page_view', '2024-01-15 10:01:00', '{}'),
        (3, 'user_456', 'click', '2024-01-15 10:02:00', '{}'),
        (4, NULL, 'page_view', '2024-01-15 10:03:00', '{}'),
        (5, NULL, 'purchase', '2024-01-15 10:04:00', '{}'),
        (6, 'user_789', 'page_view', '2024-01-15 10:05:00', '{}'),
        (7, NULL, 'click', '2024-01-15 10:06:00', '{}'),
        (8, 'user_123', 'purchase', '2024-01-15 10:07:00', '{}'),
        (9, NULL, 'page_view', '2024-01-15 10:08:00', '{}'),
        (10, NULL, 'page_view', '2024-01-15 10:09:00', '{}')
    """)

    # Create users table for context
    await adapter.execute_query("""
        CREATE TABLE users (
            id VARCHAR PRIMARY KEY,
            email VARCHAR,
            created_at TIMESTAMP,
            platform VARCHAR
        )
    """)

    await adapter.execute_query("""
        INSERT INTO users VALUES
        ('user_123', 'alice@example.com', '2024-01-01 00:00:00', 'web'),
        ('user_456', 'bob@example.com', '2024-01-02 00:00:00', 'mobile'),
        ('user_789', 'charlie@example.com', '2024-01-03 00:00:00', 'mobile')
    """)

    yield adapter

    await adapter.disconnect()


@pytest.fixture
def context_engine() -> ContextEngine:
    """Create real ContextEngine."""
    return ContextEngine()


@pytest.fixture
def pattern_repository() -> InMemoryPatternRepository:
    """Create real InMemoryPatternRepository."""
    return InMemoryPatternRepository()


@pytest.fixture
def agent_client():
    """Create real AgentClient if API key is available."""
    api_key = get_api_key()
    if not api_key:
        pytest.skip(LLM_SKIP_REASON)

    from dataing.agents.client import AgentClient

    return AgentClient(api_key=api_key)


# =============================================================================
# Test Cases - All use real implementations
# =============================================================================


class TestWorkflowConstruction:
    """Tests for workflow construction with real components."""

    async def test_workflow_builds_with_real_components(
        self,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test that workflow builds correctly with all real components."""
        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        # Verify all steps are registered
        assert len(workflow._steps) > 0
        step_names = list(workflow._steps.keys())
        assert StepType.GATHER_CONTEXT.value in step_names
        assert StepType.CHECK_PATTERNS.value in step_names
        assert StepType.GENERATE_HYPOTHESES.value in step_names
        assert StepType.GENERATE_QUERY.value in step_names
        assert StepType.EXECUTE_QUERY.value in step_names
        assert StepType.INTERPRET_EVIDENCE.value in step_names
        assert StepType.SYNTHESIZE.value in step_names

        # Verify signal handler is configured
        assert workflow._signal_handler is not None


class TestGatherContextStep:
    """Tests for GatherContextStep with real implementations."""

    async def test_gather_context_discovers_real_schema(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test that gather_context discovers the real DuckDB schema."""
        from maestro import Signal

        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        # Run just the gather_context step
        result = await workflow.tick(initial_context, StepType.GATHER_CONTEXT.value)

        # Should continue to next step
        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.CHECK_PATTERNS.value

        # Should have discovered schema
        assert result.context.schema_info is not None
        print(f"Discovered schema: {result.context.schema_info}")


class TestFullInvestigationFlow:
    """End-to-end tests for complete investigation flow."""

    async def test_investigation_runs_to_completion(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test that a full investigation runs to completion with real LLM."""
        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        print("\n=== Starting Investigation ===")
        print(f"Alert: {initial_context.alert_summary}")

        final_context = await run_investigation(
            workflow=workflow,
            initial_context=initial_context,
            max_iterations=50,
        )

        print("\n=== Investigation Complete ===")
        print(f"Evidence collected: {len(final_context.evidence)}")
        print(f"Queries executed: {final_context.total_queries_executed}")
        print(f"Synthesis: {final_context.current_synthesis}")

        # Verify investigation produced results
        assert final_context.current_synthesis is not None
        assert final_context.current_synthesis.get("confidence", 0) > 0

    async def test_investigation_with_checkpointing(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test investigation with checkpointing callbacks."""
        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        checkpoints: list[tuple[str, str]] = []

        async def on_checkpoint(ctx: InvestigationContext, next_step: str | None, step_cursor: dict[str, Any] | None = None) -> None:
            step_name = next_step or "COMPLETE"
            checkpoints.append((step_name, str(len(ctx.evidence))))
            print(f"  Checkpoint: step={step_name}, evidence_count={len(ctx.evidence)}")

        shutdown_signal = asyncio.Event()

        print("\n=== Starting Investigation with Checkpointing ===")

        await run_with_checkpointing(
            workflow=workflow,
            context=initial_context,
            start_step=StepType.GATHER_CONTEXT.value,
            on_step_complete=on_checkpoint,
            shutdown_signal=shutdown_signal,
            max_iterations=50,
        )

        print(f"\n=== Completed with {len(checkpoints)} checkpoints ===")
        for step, evidence_count in checkpoints:
            print(f"  - {step}: {evidence_count} evidence items")

        # Verify checkpoints were recorded
        assert len(checkpoints) > 0
        # First checkpoint should be check_patterns (after gather_context)
        assert checkpoints[0][0] == StepType.CHECK_PATTERNS.value

    async def test_sequential_branch_execution_ordering(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test that sequential branch execution follows the correct step sequence.

        Specifically, verify that it cycles through hypothesis steps for each branch
        and does NOT flash 'synthesize' between branches.
        """
        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        steps_sequence: list[str] = []

        async def on_checkpoint(ctx: InvestigationContext, next_step: str | None, step_cursor: dict[str, Any] | None = None) -> None:
            step_name = next_step or "complete"
            steps_sequence.append(step_name)

        shutdown_signal = asyncio.Event()

        await run_with_checkpointing(
            workflow=workflow,
            context=initial_context,
            start_step=StepType.GATHER_CONTEXT.value,
            on_step_complete=on_checkpoint,
            shutdown_signal=shutdown_signal,
            max_iterations=50,
        )

        print(f"\nStep sequence: {steps_sequence}")

        # Basic sequence check
        assert StepType.GATHER_CONTEXT.value not in steps_sequence # next_step is always AFTER
        assert StepType.CHECK_PATTERNS.value in steps_sequence
        assert StepType.GENERATE_HYPOTHESES.value in steps_sequence

        # Verify loop behavior: it should go to generate_query multiple times if there are multiple hypotheses
        gen_query_count = steps_sequence.count(StepType.GENERATE_QUERY.value)
        assert gen_query_count > 0

        # Critical check: synthesize should only appear once at the end (or near end)
        # It should NOT appear between hypothesis loops.
        synthesize_indices = [i for i, s in enumerate(steps_sequence) if s == StepType.SYNTHESIZE.value]
        assert len(synthesize_indices) == 1, f"Synthesize should only appear once, got: {steps_sequence}"

        # Ensure 'complete' is the last step
        assert steps_sequence[-1] == "complete"


class TestStepByStepExecution:
    """Tests that execute workflow step by step for debugging."""

    async def test_step_by_step_with_logging(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Execute workflow step by step with detailed logging."""
        from maestro import Signal

        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        context = initial_context
        current_step = StepType.GATHER_CONTEXT.value
        iteration = 0
        max_iterations = 30

        print("\n" + "=" * 60)
        print("STEP-BY-STEP INVESTIGATION EXECUTION")
        print("=" * 60)

        while current_step and iteration < max_iterations:
            iteration += 1
            print(f"\n--- Step {iteration}: {current_step} ---")

            result = await workflow.tick(context, current_step)

            print(f"  Signal: {result.signal}")
            print(f"  Next step: {result.next_step}")
            print(f"  Evidence count: {len(result.context.evidence)}")
            print(f"  Hypotheses: {len(result.context.hypotheses)}")

            if result.context.current_synthesis:
                print(
                    f"  Synthesis confidence: {result.context.current_synthesis.get('confidence')}"
                )

            if result.error:
                print(f"  ERROR: {result.error}")

            if result.signal == Signal.COMPLETE:
                print("\n=== WORKFLOW COMPLETE ===")
                break
            elif result.signal == Signal.FAIL:
                print(f"\n=== WORKFLOW FAILED: {result.error} ===")
                break

            context = result.context
            current_step = result.next_step

        print(f"\nTotal iterations: {iteration}")
        print(f"Final evidence count: {len(context.evidence)}")
        print(f"Final synthesis: {context.current_synthesis}")


class TestShutdownAndCancellation:
    """Tests for shutdown and cancellation handling."""

    async def test_shutdown_signal_triggers_checkpoint(
        self,
        initial_context: InvestigationContext,
        context_engine: ContextEngine,
        agent_client,
        duckdb_adapter: DuckDBAdapter,
        pattern_repository: InMemoryPatternRepository,
    ) -> None:
        """Test that shutdown signal causes graceful exit with checkpoint."""
        workflow = build_investigation_workflow(
            context_engine=context_engine,
            llm=agent_client,
            database=duckdb_adapter,
            pattern_repository=pattern_repository,
        )

        checkpoints: list[str] = []

        async def on_checkpoint(ctx: InvestigationContext, next_step: str | None, step_cursor: dict[str, Any] | None = None) -> None:
            checkpoints.append(next_step or "COMPLETE")

        # Set shutdown signal BEFORE starting
        shutdown_signal = asyncio.Event()
        shutdown_signal.set()

        with pytest.raises(WorkerShutdownError):
            await run_with_checkpointing(
                workflow=workflow,
                context=initial_context,
                start_step=StepType.GATHER_CONTEXT.value,
                on_step_complete=on_checkpoint,
                shutdown_signal=shutdown_signal,
            )

        # Should have checkpointed before shutdown
        assert len(checkpoints) == 1
        assert checkpoints[0] == StepType.GATHER_CONTEXT.value


class TestDatabaseIntegration:
    """Tests for database query execution."""

    async def test_duckdb_query_execution(
        self,
        duckdb_adapter: DuckDBAdapter,
    ) -> None:
        """Test that DuckDB executes queries correctly."""
        # Test NULL count query (what the investigation would run)
        result = await duckdb_adapter.execute_query(
            "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE user_id IS NULL) as null_count FROM events"
        )

        assert len(result.rows) == 1
        row = result.rows[0]
        print(f"Query result: total={row['total']}, null_count={row['null_count']}")

        assert row["total"] == 10
        assert row["null_count"] == 6  # 6 out of 10 have NULL user_id

    async def test_duckdb_schema_discovery(
        self,
        duckdb_adapter: DuckDBAdapter,
    ) -> None:
        """Test that DuckDB schema discovery works."""
        schema = await duckdb_adapter.get_schema()

        print(f"Schema: {schema}")

        # Should have discovered our test tables
        assert schema.catalogs is not None
        assert len(schema.catalogs) > 0


class TestExceptionTypes:
    """Tests for exception types used in the workflow."""

    def test_investigation_cancelled_exception(self) -> None:
        """Test InvestigationCancelled exception."""
        exc = InvestigationCancelled()
        assert isinstance(exc, Exception)

    def test_worker_shutdown_error(self) -> None:
        """Test WorkerShutdownError exception."""
        exc = WorkerShutdownError("test shutdown")
        assert isinstance(exc, Exception)
        assert "test shutdown" in str(exc)

    def test_awaiting_user_input(self) -> None:
        """Test AwaitingUserInput exception."""
        exc = AwaitingUserInput("generate_hypotheses")
        assert exc.next_step == "generate_hypotheses"

    def test_investigation_error(self) -> None:
        """Test InvestigationError exception."""
        exc = InvestigationError("something failed")
        assert exc.error == "something failed"
