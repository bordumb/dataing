"""Synthesize findings activity for investigation workflow."""

from typing import Any

from temporalio import activity


@activity.defn
async def synthesize(
    investigation_id: str,
    context: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Synthesize investigation findings into a final result.

    This POC implementation returns mock synthesis. The production version
    will use LLM to analyze all evidence and produce a coherent summary.

    Args:
        investigation_id: The investigation ID.
        context: The gathered context (schema, lineage, sample data).
        hypotheses: The generated and evaluated hypotheses.

    Returns:
        Dictionary containing synthesis summary and root cause analysis.
    """
    # POC: Return mock synthesis
    return {
        "investigation_id": investigation_id,
        "summary": "The investigation identified potential data quality issues "
        "in the orders table. The primary finding is NULL values in the total "
        "column, which suggests a data pipeline issue in the upstream source.",
        "root_cause": {
            "primary": "NULL values in orders.total column",
            "confidence": 0.8,
            "evidence": [
                "Sample data shows NULL values in total column",
                "Query found NULL values in recent orders",
            ],
        },
        "recommendations": [
            "Add NOT NULL constraint to orders.total column",
            "Investigate upstream data source for missing values",
            "Add data validation in the ETL pipeline",
        ],
        "hypotheses_evaluated": len(hypotheses),
        "status": "completed",
    }
