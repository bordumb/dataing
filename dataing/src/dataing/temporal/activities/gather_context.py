"""Gather context activity for investigation workflow.

Extracts business logic from GatherContextStep into a Temporal activity factory.

Note: This activity returns minimal initial context (target table schema only).
Agents fetch related tables and additional schema details on demand via tools
(see bond.tools.schema for get_upstream_tables, get_downstream_tables, etc).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from temporalio import activity

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.core.domain_types import AnomalyAlert


class ContextEngineProtocol(Protocol):
    """Protocol for context engine used by gather_context activity."""

    async def gather(
        self,
        alert: AnomalyAlert,
        adapter: BaseAdapter,
    ) -> Any:
        """Gather schema and lineage context."""
        ...


@dataclass
class GatherContextInput:
    """Input for gather_context activity."""

    investigation_id: str
    datasource_id: str
    alert: dict[str, Any]


@dataclass
class GatherContextResult:
    """Result from gather_context activity."""

    schema_info: dict[str, Any]
    lineage_info: dict[str, Any] | None  # Deprecated: agents use tools for lineage
    error: str | None = None


def make_gather_context_activity(
    context_engine: ContextEngineProtocol,
    get_adapter: Any,  # Callable[[str], Awaitable[BaseAdapter]]
) -> Any:
    """Factory that creates gather_context activity with injected dependencies.

    Args:
        context_engine: Engine for gathering context from data source.
        get_adapter: Async function to get adapter for a datasource ID.

    Returns:
        The gather_context activity function.
    """

    @activity.defn
    async def gather_context(input: GatherContextInput) -> GatherContextResult:
        """Gather schema context from the data source.

        Returns initial context for all user-provided datasets:
        - target_table: Full schema for the primary anomaly table (first dataset)
        - reference_tables: Full schema for additional datasets provided by user

        Agents use tools for everything else:
        - get_table_schema: Fetch schema for any table
        - get_upstream_tables: Discover upstream dependencies
        - get_downstream_tables: Discover downstream dependencies
        - list_tables: List all available tables
        """
        from dataing.adapters.context.schema_lookup import SchemaLookupAdapter
        from dataing.core.domain_types import AnomalyAlert

        # Validate alert data
        try:
            alert = AnomalyAlert.model_validate(input.alert)
        except Exception as e:
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
                error=f"Invalid alert data: {e}",
            )

        # Get adapter for datasource
        try:
            adapter = await get_adapter(input.datasource_id)
        except Exception as e:
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
                error=f"Failed to get adapter: {e}",
            )

        # Create schema lookup adapter (no lineage - agent uses tools)
        schema_lookup = SchemaLookupAdapter(adapter)

        try:
            # Build context for primary table (first in list)
            primary_dataset = alert.dataset_id  # Uses property that returns dataset_ids[0]
            schema_info = await schema_lookup.build_initial_context(primary_dataset)

            # Add reference tables if user provided multiple datasets
            if len(alert.dataset_ids) > 1:
                reference_tables = []
                for dataset_id in alert.dataset_ids[1:]:
                    ref_schema = await schema_lookup.get_table_schema(dataset_id)
                    if ref_schema:
                        reference_tables.append(ref_schema)
                if reference_tables:
                    schema_info["reference_tables"] = reference_tables
        except Exception as e:
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
                error=f"Context gathering failed: {e}",
            )

        # Check for empty schema
        if not schema_info.get("target_table"):
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
                error=f"Table not found: {primary_dataset} - check connectivity/permissions",
            )

        return GatherContextResult(
            schema_info=schema_info,
            lineage_info=None,  # Deprecated: agents use tools for lineage
        )

    return gather_context
