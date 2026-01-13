"""ExecuteQuery step implementation.

This step executes SQL queries against the data source to test hypotheses.
It runs after GenerateQueryStep and before InterpretEvidenceStep.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult


class DatabaseProtocol(Protocol):
    """Protocol for database adapter used by ExecuteQueryStep."""

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute SQL query and return results.

        Args:
            sql: SQL query to execute.

        Returns:
            Query result containing columns, rows, and row_count.
        """
        ...


class ExecuteQueryStep(Step[dict[str, Any], dict[str, Any]]):
    """Execute SQL query against the data source.

    This step:
    1. Reads current_query from context (set by GenerateQueryStep)
    2. Executes the query via database adapter
    3. Returns CONTINUE signal with next_step=INTERPRET_EVIDENCE
    """

    step_type = StepType.EXECUTE_QUERY

    def __init__(self, database: DatabaseProtocol) -> None:
        """Initialize the step.

        Args:
            database: Database adapter for executing queries.
        """
        self.database = database

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if current_query is available in context.

        Args:
            context: Current investigation context.

        Returns:
            True if current_query is available, False otherwise.
        """
        return context.current_query is not None

    async def execute(
        self,
        context: InvestigationContext,
        input_data: dict[str, Any] | None = None,
    ) -> StepResult[InvestigationContext, dict[str, Any]]:
        """Execute SQL query via database adapter.

        Args:
            context: Current investigation context with current_query.
            input_data: Optional input data (not used by this step).

        Returns:
            StepResult with CONTINUE signal and query result.
        """
        # Validate context has current_query
        if context.current_query is None:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                output={"error": "No query available to execute"},
            )

        # Execute query via database adapter
        try:
            query_result: dict[str, Any] = await self.database.execute_query(
                context.current_query
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                output={"error": f"Query execution failed: {e}"},
            )

        # Update context with query result and incremented query count
        updated_context = context.model_copy(
            update={
                "current_query_result": query_result,
                "total_queries_executed": context.total_queries_executed + 1,
            }
        )

        return StepResult(
            context=updated_context,
            signal=Signal.CONTINUE,
            output=query_result,
            next_step=StepType.INTERPRET_EVIDENCE.value,
        )
