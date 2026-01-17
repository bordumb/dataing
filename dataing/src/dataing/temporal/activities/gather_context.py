"""Gather context activity for investigation workflow.

Extracts business logic from GatherContextStep into a Temporal activity factory.
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
        """Gather schema and lineage context from the data source.

        This activity:
        1. Validates the alert data
        2. Gets the data source adapter
        3. Calls context engine to gather schema and lineage
        4. Returns structured context result
        """
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

        # Gather context
        try:
            gathered = await context_engine.gather(alert, adapter)
        except Exception as e:
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
                error=f"Context gathering failed: {e}",
            )

        # Convert schema to dict
        schema_info: dict[str, Any] = {}
        if gathered.schema:
            try:
                schema_info = gathered.schema.model_dump(mode="json")
            except AttributeError:
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
            return GatherContextResult(
                schema_info={},
                lineage_info=None,
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

        return GatherContextResult(
            schema_info=schema_info,
            lineage_info=lineage_info,
        )

    return gather_context


# Standalone activity for POC/testing (uses mock data)
@activity.defn
async def gather_context(investigation_id: str, datasource_id: str) -> dict[str, Any]:
    """POC gather_context activity with mock data.

    Used for testing without real dependencies. Production code should use
    make_gather_context_activity() factory instead.
    """
    return {
        "investigation_id": investigation_id,
        "datasource_id": datasource_id,
        "schema": {
            "tables": [
                {
                    "name": "orders",
                    "columns": ["id", "customer_id", "total", "created_at", "status"],
                },
                {
                    "name": "customers",
                    "columns": ["id", "name", "email", "created_at"],
                },
            ],
        },
        "lineage": {
            "upstream": ["raw_orders", "raw_customers"],
            "downstream": ["analytics.order_summary"],
        },
        "sample_data": {
            "orders": [
                {"id": 1, "customer_id": 100, "total": 99.99, "status": "completed"},
                {"id": 2, "customer_id": 101, "total": None, "status": "pending"},
            ],
        },
    }
