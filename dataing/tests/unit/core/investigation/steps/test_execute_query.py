"""Tests for ExecuteQueryStep."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.execute_query import ExecuteQueryStep
from dataing.core.investigation.values import ExecutionSignal, StepType


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create context with schema info and current query."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
        current_query="SELECT COUNT(*) FROM events WHERE user_id IS NULL",
    )


@pytest.fixture
def sample_hypothesis() -> dict[str, Any]:
    """Create sample hypothesis dict (as stored in step_cursor)."""
    return {
        "id": "h1",
        "title": "Upstream ETL failure",
        "category": "upstream_dependency",
        "reasoning": "ETL job may have failed causing NULL values",
    }


@pytest.fixture
def sample_query_result() -> dict[str, Any]:
    """Create sample query result from database."""
    return {
        "columns": ("count",),
        "rows": ({"count": 1234},),
        "row_count": 1,
    }


@pytest.fixture
def mock_database(sample_query_result: dict[str, Any]) -> AsyncMock:
    """Create mock database adapter."""
    db = AsyncMock()
    db.execute_query.return_value = sample_query_result
    return db


class TestExecuteQueryStep:
    """Tests for ExecuteQueryStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = ExecuteQueryStep(database=AsyncMock())
        assert step.step_type == StepType.EXECUTE_QUERY

    def test_can_execute_requires_query(self) -> None:
        """can_execute returns False if no current_query in context."""
        step = ExecuteQueryStep(database=AsyncMock())
        context_no_query = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
        )
        context_with_query = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
            current_query="SELECT 1",
        )

        assert step.can_execute(context_no_query) is False
        assert step.can_execute(context_with_query) is True

    @pytest.mark.asyncio
    async def test_execute_runs_query(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
    ) -> None:
        """Execute runs the current_query via database adapter."""
        step = ExecuteQueryStep(database=mock_database)

        await step.execute(sample_context)

        mock_database.execute_query.assert_called_once_with(
            sample_context.current_query
        )

    @pytest.mark.asyncio
    async def test_execute_returns_query_result(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
        sample_query_result: dict[str, Any],
    ) -> None:
        """Execute returns the query result as output."""
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(sample_context)

        assert result.output == sample_query_result

    @pytest.mark.asyncio
    async def test_execute_returns_continue_signal(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
    ) -> None:
        """Execute returns CONTINUE signal."""
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_execute_sets_next_step_interpret_evidence(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
    ) -> None:
        """Execute sets next_step to INTERPRET_EVIDENCE."""
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(sample_context)

        assert result.next_step == StepType.INTERPRET_EVIDENCE

    @pytest.mark.asyncio
    async def test_execute_increments_query_count(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
    ) -> None:
        """Execute increments total_queries_executed in context."""
        step = ExecuteQueryStep(database=mock_database)
        initial_count = sample_context.total_queries_executed

        result = await step.execute(sample_context)

        assert result.context.total_queries_executed == initial_count + 1

    @pytest.mark.asyncio
    async def test_execute_preserves_context_fields(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
    ) -> None:
        """Execute preserves other context fields."""
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(sample_context)

        assert result.context.alert_summary == sample_context.alert_summary
        assert result.context.schema_info == sample_context.schema_info
        assert result.context.current_query == sample_context.current_query

    @pytest.mark.asyncio
    async def test_execute_sets_current_query_result_in_context(
        self,
        sample_context: InvestigationContext,
        mock_database: AsyncMock,
        sample_query_result: dict[str, Any],
    ) -> None:
        """Execute sets current_query_result in context for InterpretEvidenceStep."""
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(sample_context)

        assert result.context.current_query_result == sample_query_result

    @pytest.mark.asyncio
    async def test_execute_handles_db_error(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when database raises an error."""
        mock_db = AsyncMock()
        mock_db.execute_query.side_effect = Exception("Database connection error")
        step = ExecuteQueryStep(database=mock_db)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.FAIL

    @pytest.mark.asyncio
    async def test_execute_fails_without_current_query(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Execute returns FAIL signal when no current_query in context."""
        context_no_query = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
        )
        step = ExecuteQueryStep(database=mock_database)

        result = await step.execute(context_no_query)

        assert result.signal == ExecutionSignal.FAIL
        mock_database.execute_query.assert_not_called()
