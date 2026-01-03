"""Protocol definitions for all external dependencies.

This module defines the interfaces (Protocols) that adapters must implement.
The core domain only depends on these protocols, never on concrete implementations.

This is the key to the Hexagonal Architecture - the core is completely
isolated from infrastructure concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .domain_types import (
        AnomalyAlert,
        Evidence,
        Finding,
        Hypothesis,
        InvestigationContext,
        QueryResult,
        SchemaContext,
    )


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Interface for database connections.

    Implementations must provide:
    - Query execution with timeout support
    - Schema discovery for available tables

    All queries should be read-only (SELECT only).
    """

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute (must be SELECT).
            timeout_seconds: Maximum time to wait for query completion.

        Returns:
            QueryResult with columns, rows, and row count.

        Raises:
            TimeoutError: If query exceeds timeout.
            Exception: For database-specific errors.
        """
        ...

    async def get_schema(self, table_pattern: str | None = None) -> SchemaContext:
        """Discover available tables and columns.

        Args:
            table_pattern: Optional pattern to filter tables.

        Returns:
            SchemaContext with all discovered tables.
        """
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Interface for LLM interactions.

    Implementations must provide methods for:
    - Hypothesis generation
    - Query generation
    - Evidence interpretation
    - Finding synthesis

    All methods should handle retries and rate limiting internally.
    """

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses to generate.

        Returns:
            List of generated hypotheses.

        Raises:
            LLMError: If LLM call fails.
        """
        ...

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: SchemaContext,
        previous_error: str | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous query attempt (for reflexion).

        Returns:
            SQL query string.

        Raises:
            LLMError: If LLM call fails.
        """
        ...

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: QueryResult,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            query: The query that was executed.
            results: The query results to interpret.

        Returns:
            Evidence with interpretation and confidence.

        Raises:
            LLMError: If LLM call fails.
        """
        ...

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.

        Returns:
            Finding with root cause and recommendations.

        Raises:
            LLMError: If LLM call fails.
        """
        ...


@runtime_checkable
class ContextEngine(Protocol):
    """Interface for gathering investigation context.

    Implementations should gather:
    - Database schema (REQUIRED - fail fast if empty)
    - Data lineage (OPTIONAL - graceful degradation)
    """

    async def gather(self, alert: AnomalyAlert, adapter: DatabaseAdapter) -> InvestigationContext:
        """Gather all context needed for investigation.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected database adapter.

        Returns:
            InvestigationContext with schema and optional lineage.

        Raises:
            SchemaDiscoveryError: If schema context is empty (FAIL FAST).
        """
        ...


@runtime_checkable
class LineageClient(Protocol):
    """Interface for fetching data lineage information.

    Implementations may connect to:
    - OpenLineage API
    - dbt metadata
    - Custom lineage stores
    """

    async def get_lineage(self, dataset_id: str) -> LineageContext:
        """Get lineage information for a dataset.

        Args:
            dataset_id: Fully qualified table name.

        Returns:
            LineageContext with upstream and downstream dependencies.
        """
        ...


# Re-export for convenience
if TYPE_CHECKING:
    from .domain_types import LineageContext
