"""Generate hypotheses activity for investigation workflow."""

from typing import Any

from temporalio import activity


@activity.defn
async def generate_hypotheses(
    investigation_id: str,
    alert_data: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate hypotheses for an investigation based on alert and context.

    This POC implementation returns hardcoded hypotheses. The production version
    will use LLM to generate hypotheses based on the alert and context.

    Args:
        investigation_id: The investigation ID.
        alert_data: The alert data that triggered the investigation.
        context: The gathered context (schema, lineage, sample data).

    Returns:
        List of hypothesis dictionaries with query and explanation.
    """
    # POC: Return mock hypotheses
    return [
        {
            "id": f"{investigation_id}-h1",
            "title": "Null values in orders.total column",
            "explanation": "The alert may be caused by unexpected NULL values "
            "in the total column, which could indicate data pipeline issues.",
            "query": "SELECT COUNT(*) FROM orders WHERE total IS NULL",
            "confidence": 0.8,
        },
        {
            "id": f"{investigation_id}-h2",
            "title": "Missing foreign key references",
            "explanation": "Orders may reference customers that don't exist, "
            "indicating a data integrity issue.",
            "query": "SELECT COUNT(*) FROM orders o "
            "LEFT JOIN customers c ON o.customer_id = c.id "
            "WHERE c.id IS NULL",
            "confidence": 0.6,
        },
        {
            "id": f"{investigation_id}-h3",
            "title": "Recent volume spike",
            "explanation": "There may be an unusual increase in order volume "
            "that triggered the anomaly detection.",
            "query": "SELECT DATE(created_at), COUNT(*) FROM orders "
            "GROUP BY DATE(created_at) ORDER BY 1 DESC LIMIT 7",
            "confidence": 0.5,
        },
    ]
