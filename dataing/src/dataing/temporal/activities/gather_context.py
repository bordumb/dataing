"""Gather context activity for investigation workflow.

Extracts business logic from GatherContextStep into a Temporal activity factory.

Note: This activity now returns minimal initial context (target table + related names)
instead of the full schema. Agents can fetch additional schema details on demand
via schema tools (see bond.tools.schema).
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
    lineage_info: dict[str, Any] | None
    error: str | None = None


def make_gather_context_activity(
    context_engine: ContextEngineProtocol,
    get_adapter: Any,  # Callable[[str], Awaitable[BaseAdapter]]
    get_lineage_adapter: Any | None = None,  # Callable[[str], Awaitable[LineageAdapter | None]]
) -> Any:
    """Factory that creates gather_context activity with injected dependencies.

    Args:
        context_engine: Engine for gathering context from data source.
        get_adapter: Async function to get adapter for a datasource ID.
        get_lineage_adapter: Optional async function to get lineage adapter.

    Returns:
        The gather_context activity function.
    """

    @activity.defn
    async def gather_context(input: GatherContextInput) -> GatherContextResult:
        """Gather schema and lineage context from the data source.

        This activity now returns MINIMAL initial context:
        - target_table: Full schema for the anomaly table
        - related_tables: List of upstream/downstream table names

        Agents can fetch additional schema details on demand via schema tools.
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

        # Get lineage adapter (optional)
        lineage_adapter = None
        if get_lineage_adapter:
            try:
                lineage_adapter = await get_lineage_adapter(input.datasource_id)
            except Exception:
                # Lineage is optional, continue without it
                pass

        # Create schema lookup adapter and build initial context
        schema_lookup = SchemaLookupAdapter(adapter, lineage_adapter)

        try:
            # Build minimal context: target table schema + related table names
            schema_info = await schema_lookup.build_initial_context(alert.dataset_id)
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
                error=f"Table not found: {alert.dataset_id} - check connectivity/permissions",
            )

        # Lineage is now embedded in schema_info.related_tables
        # Keep lineage_info for backward compatibility but it's derived from schema_info
        lineage_info: dict[str, Any] | None = None
        related = schema_info.get("related_tables", [])
        if related:
            lineage_info = {
                "target": alert.dataset_id,
                "upstream": related,  # SchemaLookupAdapter combines upstream+downstream
                "downstream": [],
            }

        return GatherContextResult(
            schema_info=schema_info,
            lineage_info=lineage_info,
        )

    return gather_context
