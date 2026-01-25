"""Protocol definitions for all external dependencies.

This module defines the interfaces (Protocols) that adapters must implement.
The core domain only depends on these protocols, never on concrete implementations.

This is the key to the Hexagonal Architecture - the core is completely
isolated from infrastructure concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from bond import StreamHandlers

    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.datasource.types import QueryResult, SchemaFilter, SchemaResponse

    from .domain_types import (
        AnomalyAlert,
        Evidence,
        Finding,
        Hypothesis,
        InvestigationContext,
    )


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Interface for SQL database connections.

    Implementations must provide:
    - Query execution with timeout support
    - Schema discovery for available tables

    All queries should be read-only (SELECT only).
    This protocol is implemented by SQLAdapter subclasses.
    """

    async def execute_query(
        self,
        sql: str,
        params: dict[str, object] | None = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute (must be SELECT).
            params: Optional query parameters.
            timeout_seconds: Maximum time to wait for query completion.
            limit: Optional row limit.

        Returns:
            QueryResult with columns, rows, and row count.

        Raises:
            TimeoutError: If query exceeds timeout.
            Exception: For database-specific errors.
        """
        ...

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        """Discover available tables and columns.

        Args:
            filter: Optional filter to narrow down schema discovery.

        Returns:
            SchemaResponse with all discovered tables.
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
        handlers: StreamHandlers | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses to generate.
            handlers: Optional streaming handlers for real-time updates.

        Returns:
            List of generated hypotheses.

        Raises:
            LLMError: If LLM call fails.
        """
        ...

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: SchemaResponse,
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous query attempt (for reflexion).
            handlers: Optional streaming handlers for real-time updates.

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
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            query: The query that was executed.
            results: The query results to interpret.
            handlers: Optional streaming handlers for real-time updates.

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
        handlers: StreamHandlers | None = None,
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.
            handlers: Optional streaming handlers for real-time updates.

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

    async def gather(self, alert: AnomalyAlert, adapter: BaseAdapter) -> InvestigationContext:
        """Gather all context needed for investigation.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected data source adapter.

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


@runtime_checkable
class InvestigationFeedbackEmitter(Protocol):
    """Interface for emitting investigation feedback events.

    Implementations store events in an append-only log for:
    - Investigation trace recording
    - User feedback collection
    - ML training data generation
    """

    async def emit(
        self,
        tenant_id: UUID,
        event_type: Any,  # EventType enum
        event_data: dict[str, Any],
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "system",
    ) -> Any:
        """Emit an event to the feedback log.

        Args:
            tenant_id: Tenant this event belongs to.
            event_type: Type of event being emitted.
            event_data: Event-specific data payload.
            investigation_id: Optional investigation this relates to.
            dataset_id: Optional dataset this relates to.
            actor_id: Optional user or system that caused the event.
            actor_type: Type of actor (user or system).

        Returns:
            The created event object.
        """
        ...


# Re-export for convenience
if TYPE_CHECKING:
    from .domain_types import LineageContext
