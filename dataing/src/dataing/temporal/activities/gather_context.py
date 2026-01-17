"""Gather context activity for investigation workflow."""

from typing import Any

from temporalio import activity


@activity.defn
async def gather_context(investigation_id: str, datasource_id: str) -> dict[str, Any]:
    """Gather context information for an investigation.

    This POC implementation returns mock data. The production version will
    query the datasource for schema, lineage, and sample data.

    Args:
        investigation_id: The investigation ID.
        datasource_id: The datasource to gather context from.

    Returns:
        Dictionary containing schema, lineage, and sample data.
    """
    # POC: Return mock context data
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
