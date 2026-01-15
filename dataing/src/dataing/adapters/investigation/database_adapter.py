"""Database adapter for unified investigation steps.

This module provides an adapter that wraps SQL adapters to implement
the protocol interface expected by ExecuteQueryStep.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.services.usage import UsageTracker


def _serialize_value(value: Any) -> Any:
    """Serialize a value to be JSON-compatible.

    Args:
        value: Any value that might need serialization.

    Returns:
        JSON-serializable value.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize_value(v) for v in value]
    return value


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize all values in query result rows.

    Args:
        rows: List of row dictionaries.

    Returns:
        Rows with all values JSON-serializable.
    """
    return [{k: _serialize_value(v) for k, v in row.items()} for row in rows]


class DatabaseAdapter:
    """Adapter that wraps SQL-capable adapters for ExecuteQueryStep.

    Implements the DatabaseProtocol expected by ExecuteQueryStep.
    Works with any adapter that has execute_query method (SQLAdapter, etc.).
    """

    def __init__(
        self,
        data_adapter: BaseAdapter,
        usage_tracker: UsageTracker | None = None,
        tenant_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            data_adapter: The underlying data source adapter (must support SQL).
            usage_tracker: Optional usage tracker for recording query executions.
            tenant_id: Tenant ID for usage tracking.
            investigation_id: Investigation ID for usage tracking.
        """
        self._adapter = data_adapter
        self._usage_tracker = usage_tracker
        self._tenant_id = tenant_id
        self._investigation_id = investigation_id

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute SQL query and return results.

        Args:
            sql: SQL query to execute.

        Returns:
            Query result containing columns, rows, and row_count.

        Raises:
            AttributeError: If adapter doesn't support execute_query.
        """
        # Check if adapter supports query execution
        if not hasattr(self._adapter, "execute_query"):
            raise AttributeError(
                f"Adapter {type(self._adapter).__name__} does not support execute_query"
            )

        # SQLAdapter.execute_query returns QueryResult
        result = await self._adapter.execute_query(sql)

        # Record usage if tracker is available
        if self._usage_tracker and self._tenant_id:
            data_source_type = getattr(self._adapter, "source_type", "unknown")
            await self._usage_tracker.record_query_execution(
                tenant_id=self._tenant_id,
                data_source_type=str(data_source_type),
                rows_scanned=result.row_count,
                investigation_id=self._investigation_id,
            )

        # Serialize rows to ensure all values are JSON-compatible
        serialized_rows = _serialize_rows(result.rows)

        return {
            "columns": result.columns,
            "rows": serialized_rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "execution_time_ms": result.execution_time_ms,
        }
