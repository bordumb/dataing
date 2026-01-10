"""GatherContext step implementation.

This step gathers schema and lineage context from the data source.
It's the first step in any investigation.
"""

from __future__ import annotations

from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import ExecutionSignal, StepType

from .protocol import Step, StepResult


class SchemaLike(Protocol):
    """Protocol for schema objects."""

    def is_empty(self) -> bool:
        """Return True if schema has no tables."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Return schema as dictionary."""
        ...


class LineageLike(Protocol):
    """Protocol for lineage objects."""

    def to_dict(self) -> dict[str, Any]:
        """Return lineage as dictionary."""
        ...


class GatheredContext(Protocol):
    """Protocol for gathered context from data source."""

    @property
    def schema(self) -> SchemaLike:
        """Return schema object."""
        ...

    @property
    def lineage(self) -> LineageLike | None:
        """Return lineage object or None."""
        ...


class ContextEngineProtocol(Protocol):
    """Protocol for context engine used by GatherContextStep.

    This defines the interface that the new investigation system expects.
    It differs from the legacy ContextEngine interface in core/interfaces.py.
    """

    async def gather(self, *, alert_summary: str) -> GatheredContext:
        """Gather schema and lineage context.

        Args:
            alert_summary: Summary of the alert to investigate.

        Returns:
            GatheredContext with schema and optional lineage.
        """
        ...


class ContextBundle:
    """Bundle of gathered context."""

    def __init__(
        self,
        schema_info: dict[str, Any],
        lineage_info: dict[str, Any] | None = None,
    ) -> None:
        """Initialize context bundle."""
        self.schema_info = schema_info
        self.lineage_info = lineage_info

    def __str__(self) -> str:
        """Return string representation."""
        if "error" in self.schema_info:
            return f"ContextBundle(error={self.schema_info['error']})"
        return f"ContextBundle(schema={self.schema_info}, lineage={self.lineage_info})"


class GatherContextStep(Step[None, ContextBundle]):
    """Gather schema, lineage, and recent changes.

    This is the first step in an investigation. It fails fast
    if no schema can be discovered (connectivity/permissions issue).
    """

    step_type = StepType.GATHER_CONTEXT

    def __init__(self, context_engine: ContextEngineProtocol) -> None:
        """Initialize the step.

        Args:
            context_engine: Engine for gathering context from data source.
        """
        self.context_engine = context_engine

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[ContextBundle]:
        """Gather context from data source.

        Args:
            context: Current investigation context.
            input_data: Not used for this step.

        Returns:
            StepResult with updated context containing schema/lineage.
        """
        try:
            gathered = await self.context_engine.gather(
                alert_summary=context.alert_summary,
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=ContextBundle(
                    schema_info={"error": f"Context gathering failed: {e}"}
                ),
            )

        # Fail fast on empty schema
        if gathered.schema.is_empty():
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=ContextBundle(
                    schema_info={"error": "Empty schema - check connectivity/permissions"}
                ),
            )

        # Build updated context
        schema_info = gathered.schema.to_dict()
        lineage_info = gathered.lineage.to_dict() if gathered.lineage else None

        # Create new context with gathered info
        new_context = InvestigationContext(
            alert_summary=context.alert_summary,
            schema_info=schema_info,
            lineage_info=lineage_info,
            recent_changes=context.recent_changes,
            matched_patterns=context.matched_patterns,
            hypotheses=context.hypotheses,
            evidence=context.evidence,
            current_synthesis=context.current_synthesis,
            counter_analysis=context.counter_analysis,
            chat_history=context.chat_history,
            pending_approval=context.pending_approval,
            total_tokens_used=context.total_tokens_used,
            total_queries_executed=context.total_queries_executed,
            execution_time_ms=context.execution_time_ms,
        )

        return StepResult(
            context=new_context,
            signal=ExecutionSignal.CONTINUE,
            output=ContextBundle(schema_info=schema_info, lineage_info=lineage_info),
            next_step=StepType.CHECK_PATTERNS,
        )
