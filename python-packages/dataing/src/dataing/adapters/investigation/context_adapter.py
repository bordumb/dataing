"""Context engine adapter for unified investigation steps.

This module provides an adapter that wraps the ContextEngine to implement
the protocol interface expected by GatherContextStep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataing.adapters.context.engine import ContextEngine
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.datasource.types import SchemaResponse
    from dataing.core.domain_types import AnomalyAlert


class SchemaWrapper:
    """Wrapper to make SchemaResponse compatible with GatherContextStep protocol."""

    def __init__(self, schema: SchemaResponse) -> None:
        """Initialize the wrapper.

        Args:
            schema: The underlying SchemaResponse.
        """
        self._schema = schema

    def is_empty(self) -> bool:
        """Return True if schema has no tables."""
        return self._schema.is_empty()

    def to_dict(self) -> dict[str, Any]:
        """Return schema as dictionary with JSON-serializable values."""
        return self._schema.model_dump(mode="json")


class LineageWrapper:
    """Wrapper to make LineageContext compatible with GatherContextStep protocol."""

    def __init__(self, lineage: Any) -> None:
        """Initialize the wrapper.

        Args:
            lineage: The underlying LineageContext.
        """
        self._lineage = lineage

    def to_dict(self) -> dict[str, Any]:
        """Return lineage as dictionary with JSON-serializable values."""
        if self._lineage is None:
            result: dict[str, Any] = {}
            return result
        if hasattr(self._lineage, "model_dump"):
            lineage_dict: dict[str, Any] = self._lineage.model_dump(mode="json")
            return lineage_dict
        # Handle LineageContext which is a dataclass
        return {
            "target": getattr(self._lineage, "target", ""),
            "upstream": list(getattr(self._lineage, "upstream", ())),
            "downstream": list(getattr(self._lineage, "downstream", ())),
        }


class GatheredContextWrapper:
    """Wrapper to make InvestigationContext compatible with GatherContextStep protocol."""

    def __init__(self, schema: SchemaResponse, lineage: Any) -> None:
        """Initialize the wrapper.

        Args:
            schema: The schema response.
            lineage: The lineage context (may be None).
        """
        self._schema_wrapper = SchemaWrapper(schema)
        self._lineage_wrapper = LineageWrapper(lineage) if lineage else None

    @property
    def schema(self) -> SchemaWrapper:
        """Return schema object."""
        return self._schema_wrapper

    @property
    def lineage(self) -> LineageWrapper | None:
        """Return lineage object or None."""
        return self._lineage_wrapper


class ContextEngineAdapter:
    """Adapter that wraps ContextEngine for GatherContextStep.

    Implements the ContextEngineProtocol expected by GatherContextStep.
    This adapter holds the alert and data adapter so that gather() can be
    called with just alert_summary (as required by the step protocol).
    """

    def __init__(
        self,
        context_engine: ContextEngine,
        alert: AnomalyAlert,
        data_adapter: BaseAdapter,
    ) -> None:
        """Initialize the adapter.

        Args:
            context_engine: The underlying ContextEngine.
            alert: The anomaly alert being investigated.
            data_adapter: Connected data source adapter.
        """
        self._engine = context_engine
        self._alert = alert
        self._data_adapter = data_adapter

    async def gather(self, *, alert_summary: str) -> GatheredContextWrapper:
        """Gather schema and lineage context.

        Args:
            alert_summary: Summary of the alert (ignored, uses stored alert).

        Returns:
            GatheredContext with schema and optional lineage.
        """
        # Use the real ContextEngine which needs alert and adapter
        ctx = await self._engine.gather(self._alert, self._data_adapter)

        # Wrap the result to match the step protocol
        return GatheredContextWrapper(
            schema=ctx.schema,
            lineage=ctx.lineage,
        )
