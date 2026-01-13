"""GatherContext step implementation.

This step gathers schema and lineage context from the data source.
It's the first step in any investigation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from dataing.core.domain_types import AnomalyAlert
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter


class ContextEngineProtocol(Protocol):
    """Protocol for context engine used by GatherContextStep.

    This matches the real ContextEngine.gather() signature.
    """

    async def gather(
        self,
        alert: AnomalyAlert,
        adapter: BaseAdapter,
    ) -> Any:
        """Gather schema and lineage context.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected data source adapter.

        Returns:
            InvestigationContext with schema and optional lineage.
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

    def __init__(
        self,
        context_engine: ContextEngineProtocol,
        adapter: BaseAdapter,
    ) -> None:
        """Initialize the step.

        Args:
            context_engine: Engine for gathering context from data source.
            adapter: Connected data source adapter.
        """
        self.context_engine = context_engine
        self.adapter = adapter

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[InvestigationContext, ContextBundle]:
        """Gather context from data source.

        Args:
            context: Current investigation context.
            input_data: Not used for this step.

        Returns:
            StepResult with updated context containing schema/lineage.
        """
        # Convert alert dict back to AnomalyAlert
        if context.alert is None:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error="No alert data in context",
            )

        try:
            alert = AnomalyAlert.model_validate(context.alert)
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Invalid alert data: {e}",
            )

        # Call context engine with alert and adapter
        try:
            gathered = await self.context_engine.gather(alert, self.adapter)
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Context gathering failed: {e}",
            )

        # The real ContextEngine returns domain_types.InvestigationContext
        # with schema: SchemaResponse and lineage: LineageContext
        # Convert to dict format for our workflow context

        # Convert schema to dict
        schema_info: dict[str, Any] = {}
        if gathered.schema:
            try:
                # SchemaResponse has a model_dump method (Pydantic model)
                schema_info = gathered.schema.model_dump(mode="json")
            except AttributeError:
                # Fallback for non-Pydantic schemas
                schema_info = {"raw": str(gathered.schema)}

        # Check for empty schema
        if not schema_info or (
            "catalogs" in schema_info
            and not any(
                schema.get("tables")
                for catalog in schema_info.get("catalogs", [])
                for schema in catalog.get("schemas", [])
            )
        ):
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error="Empty schema - check connectivity/permissions",
            )

        # Convert lineage to dict
        lineage_info: dict[str, Any] | None = None
        if gathered.lineage:
            try:
                lineage_info = {
                    "target": gathered.lineage.target,
                    "upstream": list(gathered.lineage.upstream),
                    "downstream": list(gathered.lineage.downstream),
                }
            except AttributeError:
                lineage_info = None

        # Create new context with gathered info
        new_context = context.model_copy(
            update={
                "schema_info": schema_info,
                "lineage_info": lineage_info,
            }
        )

        return StepResult(
            context=new_context,
            signal=Signal.CONTINUE,
            output=ContextBundle(schema_info=schema_info, lineage_info=lineage_info),
            next_step=StepType.CHECK_PATTERNS.value,
        )
